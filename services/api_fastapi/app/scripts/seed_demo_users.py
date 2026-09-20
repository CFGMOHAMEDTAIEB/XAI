"""Idempotently provision the two explicitly configured development demo users."""
import os
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal
from app.models import User, AuditEvent
from app.security import hash_password

def configured(name: str) -> str:
    value=os.environ.get(name,'').strip()
    if not value: raise SystemExit(f'{name} is required')
    return value

def upsert(db,email,password,label):
    email=email.strip().lower()
    if '@' not in email or not 10<=len(password.encode('utf-8'))<=72: raise SystemExit('Invalid demo account configuration')
    user=db.scalar(select(User).where(User.email==email))
    expected=f'[DEMO] {label}'
    if user and not (user.display_name or '').startswith('[DEMO]'):
        raise SystemExit('Refusing to replace a non-demo account')
    if not user:
        user=User(email=email,password_hash=hash_password(password),display_name=expected,full_name=expected,
                  email_verified=True,phone_verified=False,account_status='ACTIVE',role='user',totp_enabled=False)
        db.add(user);db.flush()
        action='demo.user.created'
    else:
        user.password_hash=hash_password(password);user.display_name=expected;user.full_name=expected
        user.email_verified=True;user.account_status='ACTIVE';user.role='user'
        action='demo.user.updated'
    db.add(AuditEvent(user_id=user.id,action=action,resource='development-demo',details='development_only'))

def main():
    if settings.app_env!='development': raise SystemExit('Demo seeding is development-only')
    web=(configured('XAI_DEMO_WEB_EMAIL'),configured('XAI_DEMO_WEB_PASSWORD'),'Web User')
    desktop=(configured('XAI_DEMO_DESKTOP_EMAIL'),configured('XAI_DEMO_DESKTOP_PASSWORD'),'Desktop User')
    if web[0].lower()==desktop[0].lower(): raise SystemExit('Demo user emails must be different')
    with SessionLocal() as db:
        try:
            upsert(db,*web);upsert(db,*desktop);db.commit()
        except Exception:
            db.rollback();raise
    print('DEMO_USERS = PASS count=2 environment=development')
if __name__=='__main__': main()
