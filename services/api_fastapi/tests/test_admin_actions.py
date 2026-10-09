"""Focused authorization, audit, and account-safety checks for Admin actions."""
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import account
from app.models import AuditEvent, AuthenticatorDevice, FileRecord, ShareCode, User
from test_authenticator_platform import activate
from test_mfa_enrollment import flow


def test_admin_account_actions_require_completed_mfa_and_audit_changes(flow):
    client, engine, sent = flow
    activate(client)
    admin_header = client.headers['Authorization']

    created = client.post('/auth/register', json={
        'full_name': 'Managed User', 'email': 'managed@example.com',
        'phone_number': '+33612345679', 'password': 'managed-test-password'})
    assert created.status_code == 201
    assert client.post('/auth/verification/email/confirm', json={
        'identifier': 'managed@example.com', 'code': sent[-1][1]}).status_code == 200
    enrollment = client.post('/auth/login', json={
        'email': 'managed@example.com', 'password': 'managed-test-password'}).json()
    client.headers['Authorization'] = 'Bearer ' + enrollment['access_token']
    activate(client)
    normal_header = client.headers['Authorization']
    with Session(engine) as db:
        target = db.scalar(select(User).where(User.email == 'managed@example.com'))
        target_id = target.id

    paths = [('/admin/users/' + str(target_id), 'patch'),
             (f'/admin/users/{target_id}/revoke-refresh-sessions', 'post'),
             (f'/admin/users/{target_id}/reset-mfa', 'post')]
    client.headers.pop('Authorization')
    for path, method in paths:
        response = getattr(client, method)(path, json={'role': 'admin'} if method == 'patch' else None)
        assert response.status_code == 401
    client.headers['Authorization'] = normal_header
    for path, method in paths:
        response = getattr(client, method)(path, json={'role': 'admin'} if method == 'patch' else None)
        assert response.status_code == 403

    client.headers['Authorization'] = admin_header
    assert client.patch(f'/admin/users/{target_id}', json={'role': 'admin'}).status_code == 403
    with Session(engine) as db:
        admin = db.scalar(select(User).where(User.email == 'person@example.com'))
        admin.role = 'admin'
        admin_id = admin.id
        db.commit()

    for path in ['/admin/stats', '/admin/users', f'/admin/users/{target_id}',
                 '/admin/jobs', '/admin/audit', '/admin/security/scanner',
                 '/admin/email/configuration', '/admin/authenticator/devices',
                 '/admin/authenticator/history', '/admin/authenticator/recovery']:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.json() is not None

    assert client.patch(f'/admin/users/{admin_id}', json={'status': 'DISABLED'}).status_code == 409
    assert client.patch(f'/admin/users/{target_id}', json={}).status_code == 422
    assert client.patch('/admin/users/999999', json={'status': 'DISABLED'}).status_code == 404
    assert client.post('/admin/users/999999/reset-mfa').status_code == 404
    assert client.patch(f'/admin/users/{target_id}', json={'role': 'admin'}).status_code == 200
    assert client.patch(f'/admin/users/{target_id}', json={'role': 'user'}).status_code == 200
    assert client.patch(f'/admin/users/{target_id}', json={'status': 'DISABLED'}).status_code == 200
    assert client.get(f'/admin/users/{target_id}').json()['status'] == 'DISABLED'
    assert client.patch(f'/admin/users/{target_id}', json={'status': 'ACTIVE'}).status_code == 200
    assert client.post(f'/admin/users/{target_id}/revoke-refresh-sessions').status_code == 200
    assert client.post(f'/admin/users/{target_id}/reset-mfa').json() == {
        'mfa_enabled': False, 'reenrollment_required': True}
    assert client.post(f'/admin/users/{target_id}/reset-mfa').status_code == 409
    assert client.get('/admin/users/999999').status_code == 404
    with Session(engine) as db:
        user = db.get(User, target_id)
        assert user.role == 'user' and user.account_status == 'ACTIVE'
        assert user.totp_enabled is False and user.totp_secret is None
        actions = {row.action for row in db.scalars(select(AuditEvent).where(AuditEvent.user_id == admin_id))}
        assert {'admin.user_role_changed', 'admin.user_disabled', 'admin.user_enabled',
                'admin.user_refresh_sessions_revoked', 'admin.user_mfa_reset'} <= actions


def test_admin_invite_share_and_device_actions_are_authorized_and_secret_free(flow, monkeypatch):
    client, engine, sent = flow
    activate(client)
    user_header = client.headers['Authorization']
    invite = {'email': 'invited@example.com', 'full_name': 'Invited Person', 'role': 'user'}
    guarded = [('post', '/admin/users', invite), ('get', '/admin/shares', None),
               ('post', '/admin/shares/1/revoke', None),
               ('post', '/admin/authenticator/devices/device-example/revoke', None)]
    client.headers.pop('Authorization')
    for method, path, body in guarded:
        response = client.get(path) if method == 'get' else getattr(client, method)(path, json=body)
        assert response.status_code == 401
    client.headers['Authorization'] = user_header
    for method, path, body in guarded:
        response = client.get(path) if method == 'get' else getattr(client, method)(path, json=body)
        assert response.status_code == 403

    with Session(engine) as db:
        admin = db.scalar(select(User).where(User.email == 'person@example.com'))
        admin.role = 'admin'
        admin_id = admin.id
        db.commit()
    deliveries = []
    monkeypatch.setattr(account, 'send_account_email',
                        lambda recipient, code, purpose: deliveries.append((recipient, code, purpose)))
    created = client.post('/admin/users', json=invite)
    assert created.status_code == 201
    assert created.json()['password_setup_required'] is True
    assert 'password' not in created.text.lower().replace('password_setup_required', '')
    assert deliveries[-1][2] == 'ADMIN_INVITE_VERIFY'
    assert client.post('/admin/users', json=invite).status_code == 409
    assert client.post('/auth/verification/email/confirm', json={
        'identifier': invite['email'], 'code': deliveries[-1][1]}).status_code == 200
    assert client.post('/auth/password/forgot', json={'identifier': invite['email']}).status_code == 200
    assert deliveries[-1][2] == 'PASSWORD_RESET'
    verified_reset = client.post('/auth/password/verify-code', json={
        'identifier': invite['email'], 'code': deliveries[-1][1]})
    assert verified_reset.status_code == 200
    assert client.post('/auth/password/reset', json={
        'reset_token': verified_reset.json()['reset_token'],
        'new_password': 'invited-test-password'}).status_code == 200
    login = client.post('/auth/login', json={
        'email': invite['email'], 'password': 'invited-test-password'})
    assert login.status_code == 200
    assert login.json()['state'] == 'MFA_ENROLLMENT_REQUIRED'

    with Session(engine) as db:
        target = db.scalar(select(User).where(User.email == invite['email']))
        assert target.email_verified and target.account_status == 'ACTIVE'
        file = FileRecord(owner_id=target.id, name='example.xaic', sha256='a' * 64,
                          original_size=100, compressed_size=75, codec='hybrid',
                          integrity_verified=True, status='completed')
        db.add(file)
        db.flush()
        share = ShareCode(file_id=file.id, sender_id=target.id,
                          recipient_email='recipient@example.com', code_hash='b' * 64,
                          expires_at=datetime.utcnow() + timedelta(hours=1),
                          max_downloads=2, download_count=0)
        device = AuthenticatorDevice(device_id='device-example', user_id=target.id,
                                     public_key='not-returned', platform='android',
                                     app_version='1', status='active')
        db.add_all([share, device])
        db.commit()
        share_id = share.id

    listed = client.get('/admin/shares')
    assert listed.status_code == 200
    assert listed.json()[0]['status'] == 'active'
    assert listed.json()[0]['remaining_downloads'] == 2
    assert 'code_hash' not in listed.text and 'public_key' not in listed.text
    assert client.post(f'/admin/shares/{share_id}/revoke').status_code == 200
    assert client.post(f'/admin/shares/{share_id}/revoke').status_code == 409
    assert client.get('/admin/shares').json()[0]['status'] == 'revoked'
    assert client.post('/admin/authenticator/devices/device-example/revoke').status_code == 200
    assert client.post('/admin/authenticator/devices/device-example/revoke').status_code == 409
    with Session(engine) as db:
        actions = {row.action for row in db.scalars(select(AuditEvent).where(AuditEvent.user_id == admin_id))}
        assert {'admin.user_created', 'admin.share_revoked',
                'admin.authenticator_device_revoked'} <= actions
