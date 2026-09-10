"""Device-bound authenticator APIs. Local polling is the only push provider here."""
from base64 import b64decode, b64encode
from io import BytesIO
from datetime import datetime, timedelta
import hashlib, hmac, json, secrets

import pyotp
import qrcode
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User, TotpEnrollment, AuthenticatorDevice, AuthChallenge, AuthEvent, RecoveryCode, AuthPolicy
from .mfa import lock_user, pending, verify_totp

class DeviceCreate(BaseModel):
    model_config={'extra':'forbid','hide_input_in_errors':True}
    device_id:str=Field(pattern=r'^[A-Za-z0-9_-]{20,64}$')
    public_key:str=Field(min_length=40,max_length=64)
    platform:str=Field(pattern=r'^(android|ios|windows|macos|linux)$')
    app_version:str=Field(min_length=1,max_length=32)
    @field_validator('public_key')
    @classmethod
    def valid_key(cls,value):
        try: raw=b64decode(value,validate=True)
        except Exception: raise ValueError('Invalid device public key') from None
        if len(raw)!=32:raise ValueError('Invalid device public key')
        return value

class ChallengeCreate(BaseModel):
    model_config={'extra':'forbid'}
    device_id:str
    application:str=Field(default='XAI',min_length=1,max_length=120)
    context:dict=Field(default_factory=dict)

class ChallengeDecision(BaseModel):
    model_config={'extra':'forbid','hide_input_in_errors':True}
    device_id:str
    number:str=Field(pattern=r'^\d{2}$')
    signature:str=Field(min_length=80,max_length=128)

class EnrollmentConfirm(BaseModel):
    model_config={'extra':'forbid','hide_input_in_errors':True}
    enrollment_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    code:str=Field(pattern=r'^\d{6}$')

def event(db,user_id,event_type,result='success',device_id=None,application='XAI',details=None):
    db.add(AuthEvent(user_id=user_id,device_id=device_id,event_type=event_type,result=result,
                     application=application,details=json.dumps(details or {},separators=(',',':'))))

def public_device(row):
    return {'device_id':row.device_id,'platform':row.platform,'app_version':row.app_version,
            'status':row.status,'registered_at':row.registered_at,'last_activity':row.last_activity_at}

def register_authenticator_routes(app,current_user,require_admin):
    @app.post('/auth/authenticator/enroll/start')
    def start_enrollment(response:Response,user:User=Depends(current_user),db:Session=Depends(get_db)):
        response.headers['Cache-Control']='no-store';lock_user(db,user);now=datetime.utcnow()
        row=db.get(TotpEnrollment,user.id)
        if row is None:
            row=TotpEnrollment(user_id=user.id,send_count=0,send_window_at=now,last_sent_at=now)
            db.add(row)
        row.enrollment_id=secrets.token_hex(16);row.secret=pyotp.random_base32();row.expires_at=now+timedelta(minutes=10)
        row.code_hash=None;row.code_expires_at=row.expires_at;row.disclosed=True;row.attempts=row.totp_attempts=0
        user.totp_secret=None;db.commit()
        uri=pyotp.TOTP(row.secret).provisioning_uri(name=user.email,issuer_name='XAI')
        image=BytesIO();qrcode.make(uri).save(image,format='PNG')
        return {'enrollment_id':row.enrollment_id,'otpauth_uri':uri,
                'qr_data_uri':'data:image/png;base64,'+b64encode(image.getvalue()).decode(),'expires_in_seconds':600}

    @app.post('/auth/authenticator/enroll/confirm')
    def confirm_enrollment(body:EnrollmentConfirm,user:User=Depends(current_user),db:Session=Depends(get_db)):
        row=pending(db,user,body.enrollment_id)
        if not row.disclosed:raise HTTPException(409,'Enrollment is not ready')
        if row.totp_attempts>=5:raise HTTPException(429,'Too many incorrect codes; restart setup')
        if not verify_totp(row.secret,body.code):
            row.totp_attempts+=1;db.commit();raise HTTPException(400,'Invalid or expired TOTP code')
        user.totp_secret=row.secret;user.totp_enabled=True;row.secret=row.code_hash=None
        event(db,user.id,'mfa_enabled');db.commit();return {'enabled':True}

    @app.post('/auth/devices')
    def register_device(body:DeviceCreate,user:User=Depends(current_user),db:Session=Depends(get_db)):
        existing=db.scalar(select(AuthenticatorDevice).where(AuthenticatorDevice.device_id==body.device_id))
        if existing:raise HTTPException(409,'Device is already registered')
        row=AuthenticatorDevice(user_id=user.id,**body.model_dump());db.add(row);db.flush()
        event(db,user.id,'device_registered',device_id=row.id);db.commit();db.refresh(row);return public_device(row)

    @app.get('/auth/devices')
    def devices(user:User=Depends(current_user),db:Session=Depends(get_db)):
        return [public_device(x) for x in db.scalars(select(AuthenticatorDevice).where(AuthenticatorDevice.user_id==user.id).order_by(AuthenticatorDevice.registered_at.desc()))]

    @app.post('/auth/devices/{device_id}/revoke')
    def revoke(device_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
        row=db.scalar(select(AuthenticatorDevice).where(AuthenticatorDevice.device_id==device_id,AuthenticatorDevice.user_id==user.id))
        if not row:raise HTTPException(404,'Device not found')
        row.status='revoked';event(db,user.id,'device_revoked',device_id=row.id);db.commit();return {'status':'revoked'}

    @app.post('/auth/challenges')
    def create_challenge(body:ChallengeCreate,user:User=Depends(current_user),db:Session=Depends(get_db)):
        device=db.scalar(select(AuthenticatorDevice).where(AuthenticatorDevice.device_id==body.device_id,AuthenticatorDevice.user_id==user.id,AuthenticatorDevice.status=='active'))
        if not device:raise HTTPException(404,'Active device not found')
        policy=db.scalar(select(AuthPolicy).where(AuthPolicy.scope=='global'));ttl=min(policy.challenge_seconds if policy else 120,300)
        challenge_id=secrets.token_urlsafe(24);nonce=secrets.token_urlsafe(32);number=f'{secrets.randbelow(100):02d}'
        digest=hmac.new(settings.jwt_secret.encode(),f'{challenge_id}:{nonce}:{number}'.encode(),hashlib.sha256).hexdigest()
        safe_context={k:v for k,v in body.context.items() if k in {'browser','service','domain'} and isinstance(v,str) and len(v)<=160}
        row=AuthChallenge(challenge_id=challenge_id,user_id=user.id,device_id=device.id,nonce=nonce,number_hash=digest,
                          application=body.application,request_context=json.dumps(safe_context),expires_at=datetime.utcnow()+timedelta(seconds=ttl))
        db.add(row);db.commit();return {'challenge_id':challenge_id,'status':'pending','expires_in_seconds':ttl,'number':number}

    @app.get('/auth/challenges')
    def pending_challenges(device_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
        device=db.scalar(select(AuthenticatorDevice).where(AuthenticatorDevice.device_id==device_id,AuthenticatorDevice.user_id==user.id,AuthenticatorDevice.status=='active'))
        if not device:raise HTTPException(404,'Active device not found')
        now=datetime.utcnow();rows=db.scalars(select(AuthChallenge).where(AuthChallenge.device_id==device.id,AuthChallenge.status=='pending').order_by(AuthChallenge.created_at.desc())).all()
        result=[]
        for row in rows:
            if row.expires_at<=now:row.status='expired';event(db,user.id,'push_expired','expired',device.id,row.application)
            else:result.append({'challenge_id':row.challenge_id,'nonce':row.nonce,'application':row.application,'context':json.loads(row.request_context),'created_at':row.created_at,'expires_at':row.expires_at})
        db.commit();return result

    def decide(challenge_id,body,user,db,status):
        row=db.scalar(select(AuthChallenge).where(AuthChallenge.challenge_id==challenge_id,AuthChallenge.user_id==user.id))
        if not row:raise HTTPException(404,'Challenge not found')
        device=db.scalar(select(AuthenticatorDevice).where(AuthenticatorDevice.id==row.device_id,AuthenticatorDevice.device_id==body.device_id,AuthenticatorDevice.user_id==user.id))
        if not device or device.status!='active':raise HTTPException(403,'Device is not authorized')
        if row.status!='pending':raise HTTPException(409,'Challenge is already completed')
        if row.expires_at<=datetime.utcnow():row.status='expired';db.commit();raise HTTPException(410,'Challenge expired')
        expected=hmac.new(settings.jwt_secret.encode(),f'{row.challenge_id}:{row.nonce}:{body.number}'.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,row.number_hash):raise HTTPException(400,'Number matching failed')
        message=f'{row.challenge_id}.{row.nonce}.{body.number}.{status}'.encode()
        try:Ed25519PublicKey.from_public_bytes(b64decode(device.public_key)).verify(b64decode(body.signature,validate=True),message)
        except Exception:raise HTTPException(403,'Invalid device signature') from None
        row.status=status;row.completed_at=datetime.utcnow();device.last_activity_at=datetime.utcnow()
        event(db,user.id,'push_approved' if status=='approved' else 'push_rejected',status,device.id,row.application);db.commit()
        return {'status':status}

    @app.post('/auth/challenges/{challenge_id}/approve')
    def approve(challenge_id:str,body:ChallengeDecision,user:User=Depends(current_user),db:Session=Depends(get_db)):return decide(challenge_id,body,user,db,'approved')
    @app.post('/auth/challenges/{challenge_id}/reject')
    def reject(challenge_id:str,body:ChallengeDecision,user:User=Depends(current_user),db:Session=Depends(get_db)):return decide(challenge_id,body,user,db,'rejected')

    @app.get('/auth/history')
    def history(user:User=Depends(current_user),db:Session=Depends(get_db)):
        rows=db.scalars(select(AuthEvent).where(AuthEvent.user_id==user.id).order_by(AuthEvent.created_at.desc()).limit(100)).all()
        return [{'type':x.event_type,'result':x.result,'application':x.application,'created_at':x.created_at,'details':json.loads(x.details)} for x in rows]

    @app.post('/auth/recovery-codes')
    def recovery_codes(response:Response,user:User=Depends(current_user),db:Session=Depends(get_db)):
        response.headers['Cache-Control']='no-store';db.execute(delete(RecoveryCode).where(RecoveryCode.user_id==user.id));codes=[]
        for _ in range(8):
            code='-'.join((secrets.token_hex(3),secrets.token_hex(3))).upper();codes.append(code)
            digest=hmac.new(settings.jwt_secret.encode(),f'recovery:{user.id}:{code}'.encode(),hashlib.sha256).hexdigest()
            db.add(RecoveryCode(user_id=user.id,code_hash=digest))
        event(db,user.id,'recovery_codes_regenerated');db.commit();return {'codes':codes,'shown_once':True}

    @app.get('/admin/authenticator/devices')
    def admin_devices(admin:User=Depends(require_admin),db:Session=Depends(get_db)):
        return [{'user_id':x.user_id,**public_device(x)} for x in db.scalars(select(AuthenticatorDevice).order_by(AuthenticatorDevice.registered_at.desc()).limit(500))]
