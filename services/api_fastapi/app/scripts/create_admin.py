"""Explicit environment-gated admin bootstrap. Never outputs credentials."""
import argparse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import settings
from ..db import Base, engine
from ..models import User, AuditEvent
from ..schemas import RegisterRequest
from ..security import hash_password


def create_admin(db, config, *, promote_existing=False, allow_production=False):
    if not config.xai_seed_admin:
        return 'DISABLED'
    if config.app_env == 'production' and not allow_production:
        raise ValueError('Production bootstrap requires the explicit CLI approval flag')
    try:
        request=RegisterRequest(email=config.xai_seed_admin_email,password=config.xai_seed_admin_password)
        # bcrypt has a byte limit, not a character limit.
        if len(request.password.encode('utf-8')) > 72:
            raise ValueError('Password exceeds hashing input limit')
    except (ValidationError,ValueError):
        raise ValueError('Configure a valid seed email and a password of at least 10 characters and at most 72 UTF-8 bytes') from None
    user=db.scalar(select(User).where(User.email==request.email.lower()))
    if user:
        if user.role=='admin':return 'ALREADY_EXISTS'
        if not promote_existing:
            raise ValueError('Existing non-admin account was not modified; explicit promotion required')
        user.role='admin'
        action='admin.bootstrap.promoted'
    else:
        user=User(email=request.email.lower(),password_hash=hash_password(request.password),role='admin',display_name='')
        db.add(user);db.flush()
        action='admin.bootstrap.created'
    # Promotion never replaces an existing password or MFA factor.
    db.add(AuditEvent(user_id=user.id,action=action,resource=str(user.id)))
    db.commit()
    return 'CREATED' if action.endswith('created') else 'PROMOTED'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--promote-existing',action='store_true')
    parser.add_argument('--allow-production-bootstrap',action='store_true')
    args=parser.parse_args()
    if not settings.xai_seed_admin:
        print('Admin bootstrap: DISABLED');return 0
    if settings.app_env=='production' and not args.allow_production_bootstrap:
        print('Admin bootstrap: BLOCKED (production safeguard)');return 1
    if settings.app_env!='production':Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            result=create_admin(db,settings,promote_existing=args.promote_existing,allow_production=args.allow_production_bootstrap)
    except ValueError as error:
        print(str(error));return 1
    except Exception:
        print('Admin bootstrap failed; verify database connectivity and schema. No credentials logged.');return 1
    print('Admin bootstrap: '+result);return 0

if __name__=='__main__':raise SystemExit(main())
