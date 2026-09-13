"""Professional account lifecycle tests. Delivery is captured only in memory."""
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app import main, account
from app.db import Base, get_db
from app.models import User, AccountVerificationChallenge, RefreshToken
from app.email_service import VerificationEmailError

@pytest.fixture
def accounts(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool,hide_parameters=True)
    Base.metadata.create_all(engine)
    def db():
        with Session(engine) as session:yield session
    sent=[];main.app.dependency_overrides[get_db]=db
    monkeypatch.setattr(account,'send_account_email',lambda recipient,code,purpose:sent.append((recipient,code,purpose)))
    with TestClient(main.app) as client:yield client,engine,sent
    main.app.dependency_overrides.clear();engine.dispose()

def register(client,email='person@example.com',phone='+33612345678'):
    return client.post('/auth/register',json={'full_name':'  Test   Person ','email':email,'phone_number':phone,'password':'correct-password'})

def activate(client,sent,email='person@example.com'):
    return client.post('/auth/verification/email/confirm',json={'identifier':email,'code':sent[-1][1]})

def test_registration_pending_duplicate_normalization_and_activation(accounts):
    client,engine,sent=accounts;response=register(client);assert response.status_code==201
    assert 'access_token' not in response.text and sent[-1][2]=='ACCOUNT_EMAIL_VERIFY'
    with Session(engine) as db:
        user=db.scalar(select(User));challenge=db.scalar(select(AccountVerificationChallenge))
        assert user.full_name=='Test Person' and user.phone_number=='+33612345678'
        assert user.account_status=='PENDING_VERIFICATION' and not user.email_verified
        assert challenge.code_hash!=sent[-1][1]
        assert sent[-1][1] not in repr(challenge.__dict__)
    assert sent[-1][1] not in response.text
    assert client.post('/auth/login',json={'email':'person@example.com','password':'correct-password'}).status_code==403
    assert register(client,'PERSON@example.com','+33600000000').status_code==409
    assert register(client,'other@example.com','+33 6 12 34 56 78').status_code==409
    assert activate(client,sent).json()['account_status']=='ACTIVE'
    assert client.post('/auth/login',json={'email':'person@example.com','password':'correct-password'}).status_code==200
    assert activate(client,sent).status_code==400

def test_code_attempt_expiry_resend_and_disabled_login(accounts):
    client,engine,sent=accounts;register(client)
    for _ in range(5):assert client.post('/auth/verification/email/confirm',json={'identifier':'person@example.com','code':'000000'}).status_code==400
    assert client.post('/auth/verification/email/confirm',json={'identifier':'person@example.com','code':sent[-1][1]}).status_code==400
    assert client.post('/auth/verification/email/send',json={'identifier':'person@example.com'}).status_code==200
    with Session(engine) as db:
        row=db.scalar(select(AccountVerificationChallenge).order_by(AccountVerificationChallenge.id.desc()));row.last_sent_at=datetime.utcnow()-timedelta(seconds=61);row.expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    client.post('/auth/verification/email/send',json={'identifier':'person@example.com'})
    assert client.post('/auth/verification/email/confirm',json={'identifier':'person@example.com','code':'000000'}).status_code==400

def test_expired_verification_code_and_resend_replaces_old_challenge(accounts):
    client,engine,sent=accounts;register(client);old_code=sent[-1][1]
    with Session(engine) as db:
        row=db.scalar(select(AccountVerificationChallenge));row.expires_at=datetime.utcnow()-timedelta(seconds=1);row.last_sent_at=datetime.utcnow()-timedelta(seconds=61);db.commit()
    assert client.post('/auth/verification/email/confirm',json={'identifier':'person@example.com','code':old_code}).status_code==400
    assert client.post('/auth/verification/email/send',json={'identifier':'person@example.com'}).status_code==200
    new_code=sent[-1][1];assert new_code!=old_code
    assert client.post('/auth/verification/email/confirm',json={'identifier':'person@example.com','code':old_code}).status_code==400
    assert client.post('/auth/verification/email/confirm',json={'identifier':'person@example.com','code':new_code}).status_code==200

def test_registration_provider_rejection_is_sanitized_and_pending(accounts,monkeypatch,caplog):
    client,engine,_=accounts
    monkeypatch.setattr(account,'send_account_email',lambda *args:(_ for _ in ()).throw(VerificationEmailError('safe provider failure')))
    response=register(client)
    assert response.status_code==503 and response.json()['detail']=='Account created; verification email is temporarily unavailable'
    assert 'safe provider failure' not in response.text+caplog.text
    with Session(engine) as db:
        user=db.scalar(select(User));challenge=db.scalar(select(AccountVerificationChallenge))
        assert user.account_status=='PENDING_VERIFICATION' and not user.email_verified and challenge.used_at is not None

def test_forgot_password_is_generic_when_missing_or_provider_rejects(accounts,monkeypatch,caplog):
    client,_,sent=accounts;register(client);activate(client,sent)
    missing=client.post('/auth/password/forgot',json={'identifier':'missing@example.com'})
    monkeypatch.setattr(account,'send_account_email',lambda *args:(_ for _ in ()).throw(VerificationEmailError('private provider detail')))
    existing=client.post('/auth/password/forgot',json={'identifier':'person@example.com'})
    assert missing.status_code==existing.status_code==200 and missing.json()==existing.json()
    assert 'private provider detail' not in missing.text+existing.text+caplog.text

def test_password_reset_wrong_expired_and_exhausted_codes(accounts):
    client,engine,sent=accounts;register(client);activate(client,sent);client.post('/auth/password/forgot',json={'identifier':'person@example.com'})
    raw_code=sent[-1][1]
    assert client.post('/auth/password/verify-code',json={'identifier':'person@example.com','code':'000000'}).status_code==400
    with Session(engine) as db:
        row=db.scalar(select(AccountVerificationChallenge).where(AccountVerificationChallenge.purpose=='PASSWORD_RESET'))
        assert raw_code not in repr(row.__dict__);row.expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    assert client.post('/auth/password/verify-code',json={'identifier':'person@example.com','code':raw_code}).status_code==400
    with Session(engine) as db:
        row=db.scalar(select(AccountVerificationChallenge).where(AccountVerificationChallenge.purpose=='PASSWORD_RESET'))
        row.expires_at=datetime.utcnow()+timedelta(minutes=1);row.attempt_count=row.max_attempts;db.commit()
    assert client.post('/auth/password/verify-code',json={'identifier':'person@example.com','code':raw_code}).status_code==400

def test_password_reset_generic_one_time_and_preserves_mfa(accounts):
    client,engine,sent=accounts;register(client);activate(client,sent)
    assert client.post('/auth/password/forgot',json={'identifier':'missing@example.com'}).status_code==200
    assert client.post('/auth/password/forgot',json={'identifier':'person@example.com'}).status_code==200
    code=sent[-1][1];verified=client.post('/auth/password/verify-code',json={'identifier':'person@example.com','code':code})
    assert verified.status_code==200 and 'reset_token' in verified.json()
    assert client.post('/auth/password/verify-code',json={'identifier':'person@example.com','code':code}).status_code==400
    token=verified.json()['reset_token'];assert client.post('/auth/password/reset',json={'reset_token':token,'new_password':'new-correct-password'}).status_code==200
    assert sent[-1][2]=='PASSWORD_RESET_SUCCESS' and sent[-1][1] is None
    assert client.post('/auth/password/reset',json={'reset_token':token,'new_password':'another-password'}).status_code==400
    assert client.post('/auth/login',json={'email':'person@example.com','password':'correct-password'}).status_code==401
    assert client.post('/auth/login',json={'email':'person@example.com','password':'new-correct-password'}).status_code==200
    with Session(engine) as db:assert db.scalar(select(User)).totp_enabled is False

def test_password_reset_expiry_revokes_refresh_and_preserves_mfa(accounts):
    client,engine,sent=accounts;register(client);activate(client,sent)
    login=client.post('/auth/login',json={'email':'person@example.com','password':'correct-password'}).json()
    client.post('/auth/password/forgot',json={'identifier':'person@example.com'})
    verified=client.post('/auth/password/verify-code',json={'identifier':'person@example.com','code':sent[-1][1]})
    expired_token=verified.json()['reset_token']
    with Session(engine) as db:
        row=db.scalar(select(AccountVerificationChallenge).where(AccountVerificationChallenge.purpose=='PASSWORD_RESET'))
        row.reset_token_expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    assert client.post('/auth/password/reset',json={'reset_token':expired_token,'new_password':'new-correct-password'}).status_code==400
    client.post('/auth/password/forgot',json={'identifier':'person@example.com'})
    with Session(engine) as db:
        row=db.scalar(select(AccountVerificationChallenge).where(AccountVerificationChallenge.purpose=='PASSWORD_RESET').order_by(AccountVerificationChallenge.id.desc()))
        row.last_sent_at=datetime.utcnow()-timedelta(seconds=61);db.commit()
    client.post('/auth/password/forgot',json={'identifier':'person@example.com'})
    token=client.post('/auth/password/verify-code',json={'identifier':'person@example.com','code':sent[-1][1]}).json()['reset_token']
    with Session(engine) as db:
        user=db.scalar(select(User));user.totp_enabled=True;user.totp_secret='preserved-secret';db.commit()
    assert client.post('/auth/password/reset',json={'reset_token':token,'new_password':'new-correct-password'}).status_code==200
    assert client.post('/auth/refresh',json={'refresh_token':login['refresh_token']}).status_code==401
    with Session(engine) as db:
        user=db.scalar(select(User));assert user.totp_enabled and user.totp_secret=='preserved-secret'
        assert all(row.revoked for row in db.scalars(select(RefreshToken)).all())

def test_reset_success_notification_failure_does_not_rollback(accounts,monkeypatch,caplog):
    client,_,sent=accounts;register(client);activate(client,sent);client.post('/auth/password/forgot',json={'identifier':'person@example.com'})
    token=client.post('/auth/password/verify-code',json={'identifier':'person@example.com','code':sent[-1][1]}).json()['reset_token']
    monkeypatch.setattr(account,'send_account_email',lambda *args:(_ for _ in ()).throw(VerificationEmailError('private provider detail')))
    assert client.post('/auth/password/reset',json={'reset_token':token,'new_password':'new-correct-password'}).status_code==200
    assert client.post('/auth/login',json={'email':'person@example.com','password':'new-correct-password'}).status_code==200
    assert 'password_reset_notification_failed' in caplog.text and 'private provider detail' not in caplog.text

def test_phone_delivery_is_explicitly_unavailable(accounts):
    client,_,sent=accounts;register(client);activate(client,sent)
    token=client.post('/auth/login',json={'email':'person@example.com','password':'correct-password'}).json()['access_token']
    response=client.post('/auth/verification/phone/send',headers={'Authorization':'Bearer '+token})
    assert response.status_code==503 and 'code' not in response.text.lower()
