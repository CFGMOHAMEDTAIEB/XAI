"""The desktop/web/admin enrollment contract uses one mobile-held TOTP factor."""
import pyotp
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import User
from test_mfa_enrollment import flow


def test_local_demo_enrollment_and_second_login(flow):
    client, engine, _ = flow
    credentials = {'email': 'person@example.com', 'password': 'correct-password'}
    first = client.post('/auth/login', json=credentials)
    assert first.status_code == 200
    assert first.json()['enrollment_required'] is True
    assert first.json()['refresh_token'] is None
    assert client.get('/auth/history').status_code == 401
    assert client.get('/admin/stats').status_code == 401
    assert client.post('/auth/totp/enroll', json={}).status_code == 401

    started = client.post('/auth/authenticator/enroll/start')
    assert started.status_code == 200
    assert 'secret' not in started.text and 'otpauth' not in started.text
    mobile = client.post('/auth/authenticator/enroll/mobile')
    assert mobile.status_code == 200
    assert mobile.json()['enrollment_id'] == started.json()['enrollment_id']
    assert mobile.json()['email'] == credentials['email']
    code = pyotp.parse_uri(mobile.json()['otpauth_uri']).now()
    assert client.post('/auth/authenticator/enroll/confirm', json={
        'enrollment_id': started.json()['enrollment_id'], 'code': '000000'
    }).status_code == 400
    completed = client.post('/auth/authenticator/enroll/confirm', json={
        'enrollment_id': started.json()['enrollment_id'], 'code': code
    })
    assert completed.status_code == 200
    assert completed.json()['enabled'] is True
    assert completed.json()['refresh_token']
    assert client.get('/auth/history').status_code == 401  # Enrollment token cannot be upgraded.

    challenge = client.post('/auth/login', json=credentials)
    assert challenge.status_code == 401
    mfa_token = challenge.json()['detail']['mfa_token']
    client.headers['Authorization'] = 'Bearer ' + mfa_token
    assert client.get('/auth/me').status_code == 401
    assert client.get('/auth/history').status_code == 401
    wrong = client.post('/auth/login/mfa/verify', json={'mfa_token': mfa_token, 'code': '000000'})
    assert wrong.status_code == 401
    verified = client.post('/auth/login/mfa/verify', json={'mfa_token': mfa_token, 'code': code})
    assert verified.status_code == 200
    client.headers['Authorization'] = 'Bearer ' + verified.json()['access_token']
    assert client.get('/auth/history').status_code == 200
    assert client.get('/admin/stats').status_code == 403

    # Authorization remains role-bound after the same mobile factor is accepted.
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == credentials['email']))
        user.role = 'admin'
        db.commit()
    for client_name in ('Angular', 'Desktop', 'Admin'):
        sign_in = client.post('/auth/login', json=credentials)
        assert sign_in.status_code == 401, client_name
        challenge_token = sign_in.json()['detail']['mfa_token']
        session = client.post('/auth/login/mfa/verify', json={
            'mfa_token': challenge_token, 'code': code
        })
        assert session.status_code == 200, client_name
        client.headers['Authorization'] = 'Bearer ' + session.json()['access_token']
        assert client.get('/admin/stats').status_code == 200, client_name
