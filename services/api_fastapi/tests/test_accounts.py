"""Professional account lifecycle tests. Delivery is captured only in memory."""
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app import main, account
from app.db import Base, get_db
from app.models import User, AccountVerificationChallenge

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

def test_password_reset_generic_one_time_and_preserves_mfa(accounts):
    client,engine,sent=accounts;register(client);activate(client,sent)
    assert client.post('/auth/password/forgot',json={'identifier':'missing@example.com'}).status_code==200
    assert client.post('/auth/password/forgot',json={'identifier':'person@example.com'}).status_code==200
    code=sent[-1][1];verified=client.post('/auth/password/verify-code',json={'identifier':'person@example.com','code':code})
    assert verified.status_code==200 and 'reset_token' in verified.json()
    assert client.post('/auth/password/verify-code',json={'identifier':'person@example.com','code':code}).status_code==400
    token=verified.json()['reset_token'];assert client.post('/auth/password/reset',json={'reset_token':token,'new_password':'new-correct-password'}).status_code==200
    assert client.post('/auth/password/reset',json={'reset_token':token,'new_password':'another-password'}).status_code==400
    assert client.post('/auth/login',json={'email':'person@example.com','password':'correct-password'}).status_code==401
    assert client.post('/auth/login',json={'email':'person@example.com','password':'new-correct-password'}).status_code==200
    with Session(engine) as db:assert db.scalar(select(User)).totp_enabled is False

def test_phone_delivery_is_explicitly_unavailable(accounts):
    client,_,sent=accounts;register(client);activate(client,sent)
    token=client.post('/auth/login',json={'email':'person@example.com','password':'correct-password'}).json()['access_token']
    response=client.post('/auth/verification/phone/send',headers={'Authorization':'Bearer '+token})
    assert response.status_code==503 and 'code' not in response.text.lower()
