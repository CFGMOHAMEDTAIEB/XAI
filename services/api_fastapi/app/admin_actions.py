"""Audited, deliberately limited administrator account actions."""
from datetime import datetime
import secrets

from fastapi import Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from typing import Literal

from .db import get_db
from .models import (AuditEvent, AuthChallenge, AuthenticatorDevice, FileRecord,
                     RecoveryCode, RefreshToken, ShareCode, TotpEnrollment, User)
from .security import hash_password
from .account import issue, EMAIL_VERIFY
from .email_service import VerificationEmailError


class AdminUserChange(BaseModel):
    model_config = {'extra': 'forbid'}
    role: Literal['user', 'admin'] | None = None
    status: Literal['ACTIVE', 'DISABLED'] | None = None

    @model_validator(mode='after')
    def require_change(self):
        if self.role is None and self.status is None:
            raise ValueError('At least one account change is required')
        return self


class AdminUserCreate(BaseModel):
    model_config = {'extra': 'forbid'}
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    role: Literal['user', 'admin'] = 'user'


def register_admin_actions(app, require_admin):
    @app.post('/admin/users', status_code=201)
    def create_user(body: AdminUserCreate, admin: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
        email = body.email.strip().lower()
        if db.scalar(select(User).where(User.email == email)):
            raise HTTPException(409, 'Account already exists')
        name = ' '.join(body.full_name.split())
        if not name:
            raise HTTPException(422, 'Name is required')
        user = User(email=email, full_name=name, display_name=name, role=body.role,
                    password_hash=hash_password(secrets.token_urlsafe(48)),
                    email_verified=False, phone_verified=False,
                    account_status='PENDING_VERIFICATION')
        db.add(user)
        db.flush()
        db.add(AuditEvent(user_id=admin.id, action='admin.user_created', resource=f'user:{user.id}'))
        db.commit()
        try:
            issue(db, user, 'email', EMAIL_VERIFY, email_template='ADMIN_INVITE_VERIFY')
        except VerificationEmailError:
            raise HTTPException(503, 'Account created; invitation email is temporarily unavailable')
        return {'created': True, 'email': user.email, 'role': user.role,
                'verification_required': True, 'password_setup_required': True}

    @app.patch('/admin/users/{user_id}')
    def change_user(user_id: int, body: AdminUserChange,
                    admin: User = Depends(require_admin), db: Session = Depends(get_db)):
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(404, 'User not found')
        if user.id == admin.id:
            raise HTTPException(409, 'Administrators cannot change their own role or status')
        if body.role == 'admin' and (not user.email_verified or user.account_status != 'ACTIVE'):
            raise HTTPException(409, 'Only active verified accounts can become administrators')
        if body.status == 'ACTIVE' and not user.email_verified:
            raise HTTPException(409, 'Email verification is required before enabling an account')
        if body.role is not None and body.role != user.role:
            user.role = body.role
            db.add(AuditEvent(user_id=admin.id, action='admin.user_role_changed', resource=f'user:{user_id}'))
        if body.status is not None and body.status != user.account_status:
            user.account_status = body.status
            db.add(AuditEvent(user_id=admin.id, action='admin.user_enabled' if body.status == 'ACTIVE'
                              else 'admin.user_disabled', resource=f'user:{user_id}'))
        if not db.new and not db.dirty:
            raise HTTPException(409, 'Account already has the requested state')
        if body.status == 'DISABLED' or body.role == 'user':
            db.execute(update(RefreshToken).where(RefreshToken.user_id == user_id,
                                                 RefreshToken.revoked.is_(False)).values(revoked=True))
        db.commit()
        return {'updated': True, 'role': user.role, 'status': user.account_status,
                'email_verified': user.email_verified, 'mfa_enabled': user.totp_enabled}

    @app.post('/admin/users/{user_id}/revoke-refresh-sessions')
    def revoke_refresh_sessions(user_id: int, admin: User = Depends(require_admin),
                                db: Session = Depends(get_db)):
        if not db.get(User, user_id):
            raise HTTPException(404, 'User not found')
        result = db.execute(update(RefreshToken).where(RefreshToken.user_id == user_id,
                                                     RefreshToken.revoked.is_(False)).values(revoked=True))
        db.add(AuditEvent(user_id=admin.id, action='admin.user_refresh_sessions_revoked',
                          resource=f'user:{user_id}'))
        db.commit()
        return {'revoked_refresh_sessions': result.rowcount,
                'note': 'Previously issued access tokens remain valid until expiry unless the account is disabled.'}

    @app.post('/admin/users/{user_id}/reset-mfa')
    def reset_mfa(user_id: int, admin: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(404, 'User not found')
        if user.id == admin.id:
            raise HTTPException(409, 'Administrators cannot reset their own MFA here')
        if not user.totp_enabled:
            raise HTTPException(409, 'MFA is not enabled for this account')
        user.totp_enabled = False
        user.totp_secret = None
        db.execute(delete(TotpEnrollment).where(TotpEnrollment.user_id == user_id))
        db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))
        db.execute(update(AuthenticatorDevice).where(AuthenticatorDevice.user_id == user_id)
                   .values(status='revoked'))
        db.execute(update(AuthChallenge).where(AuthChallenge.user_id == user_id,
                                               AuthChallenge.status == 'pending').values(status='expired'))
        db.execute(update(RefreshToken).where(RefreshToken.user_id == user_id,
                                             RefreshToken.revoked.is_(False)).values(revoked=True))
        db.add(AuditEvent(user_id=admin.id, action='admin.user_mfa_reset', resource=f'user:{user_id}'))
        db.commit()
        return {'mfa_enabled': False, 'reenrollment_required': True}

    @app.post('/admin/authenticator/devices/{device_id}/revoke')
    def revoke_device(device_id: str, admin: User = Depends(require_admin),
                      db: Session = Depends(get_db)):
        device = db.scalar(select(AuthenticatorDevice).where(AuthenticatorDevice.device_id == device_id))
        if device is None:
            raise HTTPException(404, 'Authenticator device not found')
        if device.user_id == admin.id:
            raise HTTPException(409, 'Administrators cannot revoke their own device here')
        if device.status == 'revoked':
            raise HTTPException(409, 'Device is already revoked')
        device.status = 'revoked'
        db.execute(update(AuthChallenge).where(AuthChallenge.device_id == device.id,
                                               AuthChallenge.status == 'pending').values(status='expired'))
        db.add(AuditEvent(user_id=admin.id, action='admin.authenticator_device_revoked',
                          resource=f'device:{device.id}'))
        db.commit()
        return {'status': 'revoked'}

    @app.get('/admin/shares')
    def list_shares(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
        rows = db.execute(select(ShareCode, FileRecord, User)
                          .join(FileRecord, ShareCode.file_id == FileRecord.id)
                          .join(User, ShareCode.sender_id == User.id)
                          .order_by(ShareCode.id.desc()).limit(500)).all()
        now = datetime.utcnow()
        result = []
        for share, file, sender in rows:
            status = ('revoked' if share.revoked else 'expired' if share.expires_at <= now else
                      'exhausted' if share.download_count >= share.max_downloads else 'active')
            result.append({'id': share.id, 'sender_email': sender.email,
                           'recipient_email': share.recipient_email, 'file_name': file.name,
                           'created_at': share.created_at, 'expires_at': share.expires_at,
                           'status': status,
                           'remaining_downloads': max(0, share.max_downloads - share.download_count)})
        return result

    @app.post('/admin/shares/{share_id}/revoke')
    def revoke_share(share_id: int, admin: User = Depends(require_admin),
                     db: Session = Depends(get_db)):
        share = db.get(ShareCode, share_id)
        if share is None:
            raise HTTPException(404, 'Share not found')
        if share.revoked:
            raise HTTPException(409, 'Share is already revoked')
        share.revoked = True
        db.add(AuditEvent(user_id=admin.id, action='admin.share_revoked', resource=f'share:{share_id}'))
        db.commit()
        return {'status': 'revoked'}
