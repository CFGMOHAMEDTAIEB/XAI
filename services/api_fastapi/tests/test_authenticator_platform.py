import base64
from datetime import datetime, timedelta
import pyotp
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import AuthChallenge, AuthenticatorDevice
from test_mfa_enrollment import flow

def keys():
    private=Ed25519PrivateKey.generate()
    raw=private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    return private,base64.b64encode(raw).decode()

def test_qr_enrollment_is_short_lived_and_requires_first_totp(flow):
    client,engine,_=flow
    started=client.post('/auth/authenticator/enroll/start');assert started.status_code==200
    data=started.json();uri=pyotp.parse_uri(data['otpauth_uri'])
    assert data['expires_in_seconds']==600 and uri.issuer=='XAI'
    assert client.post('/auth/authenticator/enroll/confirm',json={'enrollment_id':data['enrollment_id'],'code':'000000'}).status_code==400
    assert client.post('/auth/authenticator/enroll/confirm',json={'enrollment_id':data['enrollment_id'],'code':uri.now()}).json()=={'enabled':True}
    assert client.post('/auth/authenticator/enroll/confirm',json={'enrollment_id':data['enrollment_id'],'code':uri.now()}).status_code==409

def test_expired_enrollment_rejected(flow):
    client,engine,_=flow;data=client.post('/auth/authenticator/enroll/start').json()
    with Session(engine) as db:
        from app.models import TotpEnrollment
        row=db.scalar(select(TotpEnrollment));row.expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    assert client.post('/auth/authenticator/enroll/confirm',json={'enrollment_id':data['enrollment_id'],'code':'123456'}).status_code==410

def test_qr_totp_logout_and_relogin_end_to_end(flow):
    client,_,_=flow
    credentials={'email':'person@example.com','password':'correct-password'}
    enrolled=client.post('/auth/authenticator/enroll/start').json()
    code=pyotp.parse_uri(enrolled['otpauth_uri']).now()
    assert client.post('/auth/authenticator/enroll/confirm',json={'enrollment_id':enrolled['enrollment_id'],'code':code}).json()=={'enabled':True}
    assert client.post('/auth/login',json=credentials).status_code==401
    first=client.post('/auth/login',json={**credentials,'totp_code':code})
    assert first.status_code==200
    refresh=first.json()['refresh_token']
    assert client.post('/auth/logout',json={'refresh_token':refresh}).json()=={'logged_out':True}
    assert client.post('/auth/refresh',json={'refresh_token':refresh}).status_code==401
    assert client.post('/auth/login',json={**credentials,'totp_code':pyotp.parse_uri(enrolled['otpauth_uri']).now()}).status_code==200

def test_device_challenge_signature_number_replay_revoke_and_history(flow):
    client,engine,_=flow;private,public=keys();device_id='device_abcdefghijklmnopqrst'
    payload={'device_id':device_id,'public_key':public,'platform':'android','app_version':'1.0.0'}
    assert client.post('/auth/devices',json=payload).status_code==200
    assert client.post('/auth/devices',json=payload).status_code==409
    created=client.post('/auth/challenges',json={'device_id':device_id,'application':'XAI Portal','context':{'browser':'test','location':'discard'}}).json()
    pending=client.get('/auth/challenges',params={'device_id':device_id}).json()[0]
    bad={"device_id":device_id,"number":"99","signature":base64.b64encode(b'x'*64).decode()}
    assert client.post(f"/auth/challenges/{created['challenge_id']}/approve",json=bad).status_code==400
    message=f"{created['challenge_id']}.{pending['nonce']}.{created['number']}.approved".encode()
    decision={'device_id':device_id,'number':created['number'],'signature':base64.b64encode(private.sign(message)).decode()}
    assert client.post(f"/auth/challenges/{created['challenge_id']}/approve",json=decision).json()=={'status':'approved'}
    assert client.post(f"/auth/challenges/{created['challenge_id']}/approve",json=decision).status_code==409
    history=client.get('/auth/history').json();assert any(x['type']=='push_approved' for x in history)
    codes=client.post('/auth/recovery-codes').json();assert len(codes['codes'])==8 and codes['shown_once']
    assert client.post(f'/auth/devices/{device_id}/revoke').json()=={'status':'revoked'}
    assert client.post('/auth/challenges',json={'device_id':device_id}).status_code==404

def test_expired_challenge_and_wrong_device_rejected(flow):
    client,engine,_=flow;_,public=keys();device_id='device_zabcdefghijklmnopqrs'
    client.post('/auth/devices',json={'device_id':device_id,'public_key':public,'platform':'ios','app_version':'1'})
    created=client.post('/auth/challenges',json={'device_id':device_id}).json()
    with Session(engine) as db:
        row=db.scalar(select(AuthChallenge));row.expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    body={'device_id':'device_wrongabcdefghijklmn','number':created['number'],'signature':base64.b64encode(b'x'*64).decode()}
    assert client.post(f"/auth/challenges/{created['challenge_id']}/reject",json=body).status_code==403

def test_admin_authenticator_views_never_return_sensitive_material(flow):
    client,engine,_=flow;_,public=keys();device_id='device_adminabcdefghijklmnop'
    assert client.post('/auth/devices',json={'device_id':device_id,'public_key':public,'platform':'android','app_version':'1'}).status_code==200
    client.post('/auth/recovery-codes')
    with Session(engine) as db:
        user=db.scalar(select(AuthenticatorDevice).where(AuthenticatorDevice.device_id==device_id)).user_id
        db.get(__import__('app.models',fromlist=['User']).User,user).role='admin';db.commit()
    devices=client.get('/admin/authenticator/devices');history=client.get('/admin/authenticator/history');recovery=client.get('/admin/authenticator/recovery')
    assert devices.status_code==history.status_code==recovery.status_code==200
    assert 'public_key' not in devices.text and 'codes' not in recovery.text and 'code_hash' not in recovery.text
