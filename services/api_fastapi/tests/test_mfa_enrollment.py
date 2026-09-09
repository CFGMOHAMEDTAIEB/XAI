"""All email transport is mocked; no secrets are printed in test diagnostics."""
from datetime import datetime, timedelta
import io
import json
import re
import urllib.error

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main, mfa, email_service
from app.config import settings
from app.db import Base, get_db
from app.models import User, TotpEnrollment


@pytest.fixture
def flow(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool, hide_parameters=True)
    Base.metadata.create_all(engine)
    def db():
        with Session(engine) as session:
            yield session
    main.app.dependency_overrides[get_db] = db
    sent = []
    monkeypatch.setattr(mfa, 'send_verification_code', lambda recipient, code: sent.append((recipient, code)))
    with TestClient(main.app) as client:
        result = client.post('/auth/register', json={'email': 'person@example.com', 'password': 'correct-password'})
        assert result.status_code == 200
        client.headers['Authorization'] = 'Bearer ' + result.json()['access_token']
        yield client, engine, sent
    main.app.dependency_overrides.clear()
    engine.dispose()


def start(client):
    response = client.post('/auth/totp/enroll', json={})
    assert response.status_code == 200
    assert 'secret' not in response.json()
    return response.json()['enrollment_id']


def disclose(client, sent, enrollment_id):
    response = client.post('/auth/totp/email/confirm', json={
        'enrollment_id': enrollment_id, 'code': sent[-1][1]})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    return response.json()['secret']


def age_send(engine):
    with Session(engine) as db:
        row = db.scalar(select(TotpEnrollment))
        row.last_sent_at = datetime.utcnow() - timedelta(seconds=61)
        db.commit()


def test_full_flow_and_login_policy(flow, caplog):
    client, engine, sent = flow
    credentials = {'email': 'person@example.com', 'password': 'correct-password'}
    assert client.post('/auth/login', json=credentials).status_code == 200
    eid = start(client)
    assert sent[-1][0] == credentials['email']
    assert client.post('/auth/login', json=credentials).status_code == 200
    assert client.get('/auth/totp/status').json()['state'] == 'awaiting_email'
    secret = disclose(client, sent, eid)
    assert bool(re.fullmatch('[A-Z2-7]{32}', secret))
    assert client.post('/auth/login', json=credentials).status_code == 200
    code = pyotp.TOTP(secret).now()
    response = client.post('/auth/totp/confirm', json={'enrollment_id': eid, 'code': code})
    assert response.status_code == 200
    assert client.get('/auth/me').json()['mfa_enabled'] is True
    assert client.get('/auth/totp/status').json()['state'] == 'enabled'
    assert client.post('/auth/login', json=credentials).status_code == 401
    assert client.post('/auth/login', json={**credentials, 'totp_code': 'bad'}).status_code == 401
    assert client.post('/auth/login', json={**credentials, 'totp_code': code}).status_code == 200
    assert client.post('/auth/totp/confirm', json={'enrollment_id': eid, 'code': code}).status_code == 409
    assert client.post('/auth/totp/enroll', json={'restart': True}).status_code == 409
    for path in ['/auth/me', '/auth/totp/status']:
        assert secret not in client.get(path).text
    assert secret not in caplog.text
    with Session(engine) as db:
        row = db.scalar(select(TotpEnrollment))
        assert row.secret is None and row.code_hash is None
        assert bool(db.scalar(select(User)).totp_secret == secret)


def test_unique_server_secrets_and_client_input_rejected(flow):
    client, engine, sent = flow
    response = client.post('/auth/totp/enroll', json={'secret': 'client-selected-secret'})
    assert response.status_code == 422
    assert 'client-selected-secret' not in response.text
    eid = start(client)
    first = disclose(client, sent, eid)
    result = client.post('/auth/register', json={'email': 'another@example.com', 'password': 'correct-password'})
    client.headers['Authorization'] = 'Bearer ' + result.json()['access_token']
    second = disclose(client, sent, start(client))
    assert bool(first != second)


def test_email_attempts_expiry_resend_and_replay(flow):
    client, engine, sent = flow
    eid = start(client)
    real = sent[-1][1]
    wrong = '000000' if real != '000000' else '111111'
    for _ in range(5):
        assert client.post('/auth/totp/email/confirm', json={'enrollment_id': eid, 'code': wrong}).status_code == 400
    assert client.post('/auth/totp/email/confirm', json={'enrollment_id': eid, 'code': real}).status_code == 429
    assert client.post('/auth/totp/resend', json={}).status_code == 429
    age_send(engine)
    assert client.post('/auth/totp/resend', json={}).status_code == 200
    with Session(engine) as db:
        row = db.scalar(select(TotpEnrollment))
        assert row.code_hash != sent[-1][1]
        row.code_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.post('/auth/totp/email/confirm', json={'enrollment_id': eid, 'code': sent[-1][1]}).status_code == 410
    age_send(engine)
    assert client.post('/auth/totp/resend', json={}).status_code == 200
    disclose(client, sent, eid)
    assert client.post('/auth/totp/email/confirm', json={'enrollment_id': eid, 'code': sent[-1][1]}).status_code == 409


def test_totp_must_follow_email_and_attempts_are_bounded(flow):
    client, engine, sent = flow
    eid = start(client)
    assert client.post('/auth/totp/confirm', json={'enrollment_id': eid, 'code': '123456'}).status_code == 409
    secret = disclose(client, sent, eid)
    invalid = next(f'{n:06d}' for n in range(100) if not pyotp.TOTP(secret).verify(f'{n:06d}', valid_window=1))
    for _ in range(5):
        assert client.post('/auth/totp/confirm', json={'enrollment_id': eid, 'code': invalid}).status_code == 400
    assert client.post('/auth/totp/confirm', json={'enrollment_id': eid, 'code': pyotp.TOTP(secret).now()}).status_code == 429
    assert client.get('/auth/me').json()['mfa_enabled'] is False


def test_unauthorized_and_other_user_cannot_receive_secret(flow):
    client, engine, sent = flow
    eid = start(client)
    client.headers.pop('Authorization')
    for path in ['/auth/totp/enroll', '/auth/totp/resend', '/auth/totp/email/confirm', '/auth/totp/confirm']:
        assert client.post(path, json={'enrollment_id': eid, 'code': sent[-1][1]} if 'confirm' in path else {}).status_code == 401
    result = client.post('/auth/register', json={'email': 'other@example.com', 'password': 'correct-password'})
    client.headers['Authorization'] = 'Bearer ' + result.json()['access_token']
    assert client.post('/auth/totp/email/confirm', json={'enrollment_id': eid, 'code': sent[-1][1]}).status_code == 409


def test_pending_restart_invalidates_old_challenge_and_secret(flow):
    client, engine, sent = flow
    eid = start(client)
    old_secret = disclose(client, sent, eid)
    assert client.post('/auth/totp/enroll', json={}).status_code == 409
    age_send(engine)
    result = client.post('/auth/totp/enroll', json={'restart': True})
    assert result.status_code == 200
    new_id = result.json()['enrollment_id']
    assert new_id != eid
    assert client.post('/auth/totp/confirm', json={'enrollment_id': eid, 'code': pyotp.TOTP(old_secret).now()}).status_code == 409
    assert bool(disclose(client, sent, new_id) != old_secret)


def test_resend_failure_is_sanitized_and_never_enables_mfa(flow, monkeypatch):
    client, engine, sent = flow
    def fail(*args):
        raise OSError('private-provider-response')
    monkeypatch.setattr(mfa, 'send_verification_code', fail)
    response = client.post('/auth/totp/enroll', json={})
    assert response.status_code == 503
    assert 'private-provider-response' not in response.text
    assert client.get('/auth/me').json()['mfa_enabled'] is False
    assert client.get('/auth/totp/status').json()['state'] == 'awaiting_email'


def test_corrupt_active_secret_fails_closed(flow, caplog):
    client, engine, sent = flow
    with Session(engine) as db:
        user = db.scalar(select(User))
        user.totp_enabled = True
        user.totp_secret = 'invalid-factor!'
        db.commit()
    assert client.post('/auth/login', json={'email': 'person@example.com', 'password': 'correct-password', 'totp_code': '123456'}).status_code == 401
    assert 'invalid stored factor' in caplog.text
    assert 'invalid-factor!' not in caplog.text


def test_resend_transport_contract(monkeypatch):
    monkeypatch.setattr(settings, 'email_provider', 'resend')
    monkeypatch.setattr(settings, 'resend_api_key', 'test-key-not-real')
    monkeypatch.setattr(settings, 'resend_from_email', 'onboarding@resend.dev')
    captured = []
    class Reply:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"id":"test-message"}'
    def send(request, timeout):
        assert request.full_url == 'https://api.resend.com/emails'
        assert timeout > 0
        captured.append(json.loads(request.data))
        return Reply()
    monkeypatch.setattr(email_service.urllib.request, 'urlopen', send)
    email_service.send_verification_code('person@example.com', '123456')
    body = captured[0]
    assert body['subject'] == 'XAI Authenticator verification'
    assert body['to'] == ['person@example.com']
    assert '123456' in body['text'] and '10 minutes' in body['text']
    assert 'test-key-not-real' not in json.dumps(body)
    assert set(body) == {'from', 'to', 'subject', 'text'}


def test_resend_owner_only_restriction_is_reported(monkeypatch):
    monkeypatch.setattr(settings, 'email_provider', 'resend')
    monkeypatch.setattr(settings, 'resend_api_key', 'test-key-not-real')
    monkeypatch.setattr(settings, 'resend_from_email', 'onboarding@resend.dev')
    def send(*args, **kwargs):
        raise urllib.error.HTTPError('https://api.resend.com/emails', 403, 'Forbidden', {},
            io.BytesIO(b'{"message":"You can only send testing emails to your own email address (private@example.com)"}'))
    monkeypatch.setattr(email_service.urllib.request, 'urlopen', send)
    with pytest.raises(email_service.VerificationEmailError, match='only email the account owner') as exc:
        email_service.send_verification_code('person@example.com', '123456')
    assert 'private@example.com' not in str(exc.value)


def test_resend_attachment_provider_preserves_existing_artifact_contract(monkeypatch, tmp_path):
    import base64
    monkeypatch.setattr(settings, 'email_provider', 'resend')
    monkeypatch.setattr(settings, 'resend_api_key', 'test-key-not-real')
    monkeypatch.setattr(settings, 'resend_from_email', 'onboarding@resend.dev')
    captured = []
    monkeypatch.setattr(email_service, '_send_resend', lambda body: captured.append(body) or 'test-message')
    path = tmp_path / 'file.xaic'
    path.write_bytes(b'unchanged artifact bytes')
    result = email_service.send_artifact(path, 'file.xaic', 'person@example.com')
    assert email_service.configuration_missing() == []
    assert result['email_delivery'] == 'accepted_by_provider'
    assert base64.b64decode(captured[0]['attachments'][0]['content']) == path.read_bytes()
    assert captured[0]['attachments'][0]['filename'] == 'file.xaic'
