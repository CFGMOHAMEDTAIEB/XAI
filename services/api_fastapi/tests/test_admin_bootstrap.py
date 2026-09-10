from types import SimpleNamespace
import secrets
import json
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import main
from app.config import Settings
from app.models import User, TotpEnrollment
from app.security import verify_password
from app.scripts.create_admin import create_admin
from test_mfa_enrollment import flow

def config(**kwargs):
    return SimpleNamespace(**dict(dict(xai_seed_admin=True,app_env='development',xai_seed_admin_email='seed@example.com',xai_seed_admin_password=secrets.token_urlsafe(32)),**kwargs))

def test_seed_lifecycle(flow):
    _,engine,_=flow
    c=config()
    with Session(engine) as db:
        assert create_admin(db,config(xai_seed_admin=False))=='DISABLED'
        assert create_admin(db,c)=='CREATED'
        user=db.scalar(select(User).where(User.email==c.xai_seed_admin_email))
        assert user.role=='admin' and verify_password(c.xai_seed_admin_password,user.password_hash)
        old_hash=user.password_hash
        assert create_admin(db,c)=='ALREADY_EXISTS'
        assert user.password_hash==old_hash
        with pytest.raises(ValueError):create_admin(db,config(app_env='production'))
        with pytest.raises(ValueError):create_admin(db,config(xai_seed_admin_email='invalid'))
        normal=db.scalar(select(User).where(User.email=='person@example.com'))
        normal_hash=normal.password_hash
        with pytest.raises(ValueError):create_admin(db,config(xai_seed_admin_email=normal.email))
        assert normal.role=='user'
        assert create_admin(db,config(xai_seed_admin_email=normal.email),promote_existing=True)=='PROMOTED'
        assert normal.password_hash==normal_hash

def test_admin_authorization_and_secret_free_details(flow,monkeypatch):
    client,engine,_=flow
    monkeypatch.setattr(main.settings,'admin_emails','person@example.com')
    monkeypatch.setattr(main,'scanner_health',lambda:{'status':'unavailable','clamav':'unavailable','yara':'operational','required':True})
    token=client.headers.pop('Authorization')
    paths=['/admin/stats','/admin/users','/admin/users/1','/admin/jobs','/admin/audit','/admin/email/configuration','/admin/security/scanner']
    for path in paths:assert client.get(path).status_code==401
    client.headers['Authorization']=token
    for path in paths:assert client.get(path).status_code==403
    with Session(engine) as db:
        user=db.scalar(select(User));user.role='admin';db.commit()
    for path in paths:
        response=client.get(path);assert response.status_code==200
        data=response.json()
        assert not any(key in json.dumps(data) for key in ['password_hash','totp_secret','code_hash','refresh_token'])
    assert client.get('/admin/users/999999').status_code==404

def test_mailpit_and_plain_smtp_rejected_in_production():
    for provider in ['mailpit','smtp']:
        with pytest.raises(ValueError, match='Mailpit|TLS'):
            Settings(_env_file=None,app_env='production',email_provider=provider,smtp_security='none',
                     jwt_secret=secrets.token_urlsafe(48),database_url='postgresql+psycopg://localhost/test',cors_origins='https://example.com')


def test_admin_mfa_has_no_role_bypass(flow):
    import pyotp
    client,engine,_=flow
    secret=pyotp.random_base32()
    password=secrets.token_urlsafe(32)
    with Session(engine) as db:
        from app.security import hash_password
        user=db.scalar(select(User));user.role='admin';user.totp_enabled=True
        user.totp_secret=secret;user.password_hash=hash_password(password);db.commit()
    payload={'email':'person@example.com','password':password}
    assert client.post('/auth/login',json=payload).status_code==401
    payload['totp_code']=pyotp.TOTP(secret).now()
    assert client.post('/auth/login',json=payload).status_code==200
