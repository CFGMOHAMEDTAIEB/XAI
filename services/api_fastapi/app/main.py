from datetime import datetime, timedelta
import base64, io, pyotp, qrcode
from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from .models import User, FileRecord, ShareCode, AuditEvent
from .schemas import RegisterRequest, LoginRequest, TokenResponse, FileCreate, ShareCreate, ShareRedeem
from .security import hash_password, verify_password, create_token, decode_token, generate_share_code, hash_share_code

Base.metadata.create_all(engine)
app=FastAPI(title='XAI-Compress Platform API',version='0.1.0')

def current_user(authorization:str=Header(default=''),db:Session=Depends(get_db)):
    if not authorization.startswith('Bearer '): raise HTTPException(401,'Bearer token required')
    uid=decode_token(authorization[7:]); user=db.get(User,uid)
    if not user: raise HTTPException(401,'User not found')
    return user

def audit(db,user_id,action,resource='',result='success',details=''):
    db.add(AuditEvent(user_id=user_id,action=action,resource=resource,result=result,details=details)); db.commit()

@app.get('/health')
def health(): return {'status':'ok','service':'xai-platform-api'}

@app.post('/auth/register',response_model=TokenResponse)
def register(body:RegisterRequest,db:Session=Depends(get_db)):
    if db.scalar(select(User).where(User.email==body.email.lower())): raise HTTPException(409,'Email already registered')
    user=User(email=body.email.lower(),password_hash=hash_password(body.password),display_name=body.display_name)
    db.add(user); db.commit(); db.refresh(user); audit(db,user.id,'user.register')
    return TokenResponse(access_token=create_token(user.id))

@app.post('/auth/login',response_model=TokenResponse)
def login(body:LoginRequest,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==body.email.lower()))
    if not user or not verify_password(body.password,user.password_hash): raise HTTPException(401,'Invalid credentials')
    if user.totp_enabled and (not body.totp_code or not pyotp.TOTP(user.totp_secret).verify(body.totp_code,valid_window=1)):
        raise HTTPException(401,'Valid TOTP code required')
    audit(db,user.id,'user.login'); return TokenResponse(access_token=create_token(user.id))

@app.post('/auth/totp/enroll')
def totp_enroll(user:User=Depends(current_user),db:Session=Depends(get_db)):
    secret=pyotp.random_base32(); user.totp_secret=secret; user.totp_enabled=False; db.commit()
    uri=pyotp.TOTP(secret).provisioning_uri(name=user.email,issuer_name='XAI-Compress')
    img=qrcode.make(uri); buf=io.BytesIO(); img.save(buf,format='PNG')
    return {'secret':secret,'otpauth_uri':uri,'qr_png_base64':base64.b64encode(buf.getvalue()).decode()}

@app.post('/auth/totp/confirm')
def totp_confirm(code:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    if not user.totp_secret or not pyotp.TOTP(user.totp_secret).verify(code,valid_window=1): raise HTTPException(400,'Invalid TOTP code')
    user.totp_enabled=True; db.commit(); audit(db,user.id,'totp.enabled'); return {'enabled':True}

@app.post('/files')
def create_file(body:FileCreate,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=FileRecord(owner_id=user.id,**body.model_dump()); db.add(row); db.commit(); db.refresh(row); audit(db,user.id,'file.recorded',str(row.id))
    return {'id':row.id,**body.model_dump()}

@app.get('/history')
def history(user:User=Depends(current_user),db:Session=Depends(get_db)):
    files=db.scalars(select(FileRecord).where(FileRecord.owner_id==user.id).order_by(FileRecord.created_at.desc())).all()
    return [{'id':f.id,'name':f.name,'codec':f.codec,'original_size':f.original_size,'compressed_size':f.compressed_size,'sha256':f.sha256,'created_at':f.created_at} for f in files]

@app.post('/shares')
def create_share(body:ShareCreate,user:User=Depends(current_user),db:Session=Depends(get_db)):
    file=db.get(FileRecord,body.file_id)
    if not file or file.owner_id!=user.id: raise HTTPException(404,'File not found')
    code,digest=generate_share_code(); row=ShareCode(file_id=file.id,sender_id=user.id,recipient_email=body.recipient_email.lower(),code_hash=digest,
        expires_at=datetime.utcnow()+timedelta(minutes=body.expires_minutes),max_downloads=body.max_downloads,anonymous_sender=body.anonymous_sender)
    db.add(row); db.commit(); audit(db,user.id,'share.created',str(file.id))
    return {'share_code':code,'expires_at':row.expires_at,'recipient_email':row.recipient_email,'email_delivery':'not_configured_in_mvp'}

@app.post('/shares/redeem')
def redeem(body:ShareRedeem,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=db.scalar(select(ShareCode).where(ShareCode.code_hash==hash_share_code(body.code)))
    if not row or row.revoked or row.expires_at<datetime.utcnow() or row.download_count>=row.max_downloads: raise HTTPException(404,'Invalid or expired code')
    if row.recipient_email!=user.email: raise HTTPException(403,'Code is not assigned to this account')
    file=db.get(FileRecord,row.file_id); row.download_count+=1; db.commit(); audit(db,user.id,'share.redeemed',str(row.id))
    return {'file':{'id':file.id,'name':file.name,'sha256':file.sha256,'original_size':file.original_size,'compressed_size':file.compressed_size,'codec':file.codec},
            'sender':None if row.anonymous_sender else row.sender_id,'remaining_downloads':row.max_downloads-row.download_count}
