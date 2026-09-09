from datetime import datetime, timedelta
import pyotp
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import TotpEnrollment
from test_mfa_enrollment import flow, start, disclose, age_send


def test_expired_enrollment_and_totp_rejected(flow):
    client, engine, sent = flow
    eid = start(client)
    secret = disclose(client, sent, eid)
    old_code = pyotp.TOTP(secret).at(datetime.utcnow() - timedelta(minutes=5))
    # Avoid the tiny chance of a six-digit collision with a current accepted code.
    if not pyotp.TOTP(secret).verify(old_code, valid_window=1):
        assert client.post('/auth/totp/confirm', json={'enrollment_id': eid, 'code': old_code}).status_code == 400
    with Session(engine) as db:
        row = db.scalar(select(TotpEnrollment))
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.get('/auth/totp/status').json()['state'] == 'expired'
    assert client.post('/auth/totp/confirm', json={'enrollment_id': eid, 'code': pyotp.TOTP(secret).now()}).status_code == 410


def test_hourly_limit_survives_restart(flow):
    client, engine, sent = flow
    start(client)
    for _ in range(4):
        age_send(engine)
        assert client.post('/auth/totp/enroll', json={'restart': True}).status_code == 200
    age_send(engine)
    assert client.post('/auth/totp/enroll', json={'restart': True}).status_code == 429
    assert len(sent) == 5


def test_legacy_unconfirmed_secret_is_not_an_active_factor(flow):
    from app.models import User
    client, engine, sent = flow
    with Session(engine) as db:
        user = db.scalar(select(User))
        user.totp_secret = pyotp.random_base32()
        db.commit()
    assert client.post('/auth/login', json={'email': 'person@example.com', 'password': 'correct-password'}).status_code == 200
    assert client.post('/auth/totp/confirm', json={'enrollment_id': '0'*32, 'code': '123456'}).status_code == 409
    start(client)
    with Session(engine) as db:
        assert db.scalar(select(User)).totp_secret is None


def test_additive_migration_is_repeatable_and_preserves_active_users():
    from pathlib import Path
    from sqlalchemy import create_engine, inspect
    from app.models import User
    engine = create_engine('sqlite://', hide_parameters=True)
    User.__table__.create(engine)
    with Session(engine) as db:
        user = User(email='migration@example.com', password_hash='test-only',
                    totp_secret=pyotp.random_base32(), totp_enabled=True)
        db.add(user)
        db.commit()
        original = user.totp_secret
    migration = (Path(__file__).parents[1] / 'migrations/001_totp_enrollments.sql').read_text()
    for _ in range(2):
        with engine.begin() as connection:
            connection.exec_driver_sql(migration)
    assert {c['name'] for c in inspect(engine).get_columns('totp_enrollments')} == set(TotpEnrollment.__table__.columns.keys())
    with Session(engine) as db:
        user = db.scalar(select(User))
        assert user.totp_enabled and bool(user.totp_secret == original)
    engine.dispose()


def test_refresh_rotation_and_logout_invalidate_replay(flow):
    client, engine, sent = flow
    login = client.post('/auth/login', json={'email': 'person@example.com', 'password': 'correct-password'})
    refresh = login.json()['refresh_token']
    rotated = client.post('/auth/refresh', json={'refresh_token': refresh})
    assert rotated.status_code == 200
    assert client.post('/auth/refresh', json={'refresh_token': refresh}).status_code == 401
    new_refresh = rotated.json()['refresh_token']
    assert client.post('/auth/logout', json={'refresh_token': new_refresh}).status_code == 200
    assert client.post('/auth/refresh', json={'refresh_token': new_refresh}).status_code == 401
