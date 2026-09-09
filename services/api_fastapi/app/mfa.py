"""Pending enrollment extends the existing User TOTP factor; it is never a login factor."""
from datetime import datetime, timedelta
import binascii
import hashlib
import hmac
import logging
import re
import secrets

import pyotp
from fastapi import Depends, HTTPException, Response
from sqlalchemy import update
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .email_service import send_verification_code, VerificationEmailError
from .models import User, TotpEnrollment, AuditEvent
from .schemas import TotpConfirm, TotpStart

logger = logging.getLogger(__name__)


def verify_totp(secret, code):
    if not secret or not code or not re.fullmatch(r'[0-9]{6}', code):
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except (ValueError, TypeError, binascii.Error):
        logger.warning('TOTP verification failed: invalid stored factor')
        return False


def code_digest(row, code):
    # Keyed hash prevents offline enumeration of the short numeric code from a DB dump.
    return hmac.new(settings.jwt_secret.encode(),
        f'mfa-email:{row.user_id}:{row.enrollment_id}:{code}'.encode(), hashlib.sha256).hexdigest()


def lock_user(db, user):
    # Serialize state changes on PostgreSQL and SQLite, including first enrollment.
    db.execute(update(User).where(User.id == user.id).values(id=User.id))
    db.refresh(user)
    if user.totp_enabled:
        raise HTTPException(409, 'MFA is already enabled')


def pending(db, user, enrollment_id):
    lock_user(db, user)
    row = db.get(TotpEnrollment, user.id)
    if not row or row.enrollment_id != enrollment_id or not row.secret:
        raise HTTPException(409, 'Enrollment is no longer available; restart setup')
    if row.expires_at <= datetime.utcnow():
        raise HTTPException(410, 'Enrollment expired; restart setup')
    return row


def register_mfa_routes(app, current_user):
    @app.get('/auth/totp/status')
    def status(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
        response.headers['Cache-Control'] = 'no-store'
        row = db.get(TotpEnrollment, user.id)
        state = 'enabled' if user.totp_enabled else 'not_configured'
        if not user.totp_enabled and row and row.secret:
            state = 'expired' if row.expires_at <= datetime.utcnow() else ('awaiting_totp' if row.disclosed else 'awaiting_email')
        return {'state': state, 'email': user.email,
                'enrollment_id': row.enrollment_id if row else None}

    @app.post('/auth/totp/enroll')
    def enroll(response: Response, body: TotpStart = TotpStart(),
               user: User = Depends(current_user), db: Session = Depends(get_db)):
        response.headers['Cache-Control'] = 'no-store'
        lock_user(db, user)
        now = datetime.utcnow()
        row = db.get(TotpEnrollment, user.id)
        if row and row.secret and row.expires_at > now and not body.restart:
            raise HTTPException(409, 'Enrollment already pending; continue setup or resend the email code')
        if row is None:
            row = TotpEnrollment(user_id=user.id, send_count=0, send_window_at=now, last_sent_at=now-timedelta(hours=1))
            db.add(row)
        check_send_limit(row, now)
        row.enrollment_id = secrets.token_hex(16)
        row.secret = pyotp.random_base32()
        user.totp_secret = None  # Discard only legacy, unconfirmed enrollment material.
        row.expires_at = now + timedelta(minutes=20)
        row.disclosed = False
        row.attempts = row.totp_attempts = 0
        return deliver(db, user, row, now)

    @app.post('/auth/totp/resend')
    def resend(body: TotpStart = TotpStart(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        lock_user(db, user)
        row = db.get(TotpEnrollment, user.id)
        now = datetime.utcnow()
        if not row or not row.secret or row.disclosed or row.expires_at <= now:
            raise HTTPException(409, 'Cannot resend; continue TOTP verification or restart setup')
        check_send_limit(row, now)
        return deliver(db, user, row, now)

    @app.post('/auth/totp/email/confirm')
    def email_confirm(body: TotpConfirm, response: Response,
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
        response.headers['Cache-Control'] = 'no-store'
        row = pending(db, user, body.enrollment_id)
        if row.disclosed or not row.code_hash:
            raise HTTPException(409, 'Email code already used; continue TOTP verification or restart setup')
        if row.code_expires_at <= datetime.utcnow():
            raise HTTPException(410, 'Email code expired; request a new code')
        if row.attempts >= 5:
            raise HTTPException(429, 'Too many incorrect codes; request a new code')
        if not hmac.compare_digest(row.code_hash, code_digest(row, body.code)):
            row.attempts += 1
            db.commit()
            raise HTTPException(400, 'Invalid email verification code')
        row.code_hash = None
        row.disclosed = True
        secret = row.secret
        enrollment_id = row.enrollment_id
        db.commit()  # Consume before returning: lost responses require explicit restart.
        return {'enrollment_id': enrollment_id, 'secret': secret,
                'otpauth_uri': pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name='XAI-Compress')}

    @app.post('/auth/totp/confirm')
    def confirm(body: TotpConfirm, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = pending(db, user, body.enrollment_id)
        if not row.disclosed:
            raise HTTPException(409, 'Verify the email code before confirming TOTP')
        if row.totp_attempts >= 5:
            raise HTTPException(429, 'Too many incorrect TOTP codes; restart setup')
        if not verify_totp(row.secret, body.code):
            row.totp_attempts += 1
            db.commit()
            raise HTTPException(400, 'Invalid or expired TOTP code; use a fresh code and check device time')
        user.totp_secret = row.secret
        user.totp_enabled = True
        row.secret = row.code_hash = None
        db.add(AuditEvent(user_id=user.id, action='totp.enabled'))
        db.commit()
        return {'enabled': True}


def check_send_limit(row, now):
    if row.last_sent_at > now - timedelta(seconds=60):
        raise HTTPException(429, 'Wait 60 seconds before requesting another email')
    if row.send_window_at <= now - timedelta(hours=1):
        row.send_window_at, row.send_count = now, 0
    if row.send_count >= 5:
        raise HTTPException(429, 'Email request limit reached; retry in one hour')


def deliver(db, user, row, now):
    code = f'{secrets.randbelow(1000000):06d}'
    row.code_hash = code_digest(row, code)
    row.code_expires_at = min(now + timedelta(minutes=10), row.expires_at)
    row.attempts = 0
    row.last_sent_at = now
    row.send_count += 1
    # Persist request and throttle before contacting the provider. A failed/uncertain
    # delivery never releases a secret; resend replaces the code after the cooldown.
    db.commit()
    try:
        send_verification_code(user.email, code)
    except VerificationEmailError as error:
        raise HTTPException(503, str(error)) from None
    except (OSError, ValueError):
        raise HTTPException(503, 'Verification email unavailable; retry later') from None
    return {'state': 'awaiting_email', 'enrollment_id': row.enrollment_id,
            'email': user.email, 'expires_in_seconds': max(0, int((row.code_expires_at - now).total_seconds())), 'resend_after_seconds': 60}
