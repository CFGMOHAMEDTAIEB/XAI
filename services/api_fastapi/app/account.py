from datetime import datetime, timedelta
import logging, re, secrets
from fastapi import Depends, HTTPException, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User, AccountVerificationChallenge, RefreshToken
from .schemas import VerificationSendRequest, VerificationConfirmRequest, PasswordResetRequest
from .security import generate_numeric_code, hash_verification_secret, hash_password
from .email_service import send_account_email, VerificationEmailError
from .sms_service import send_verification_code as send_sms, SmsUnavailableError

EMAIL_VERIFY='ACCOUNT_EMAIL_VERIFY'; PHONE_VERIFY='ACCOUNT_PHONE_VERIFY'; PASSWORD_RESET='PASSWORD_RESET'
logger=logging.getLogger('uvicorn.error.account')

def normalize_email(value:str)->str: return value.strip().lower()
def normalize_phone(value:str)->str:
    value=value.strip();digits=re.sub(r'[^0-9]','',value)
    if value.startswith('00'): digits=digits[2:]
    if not value.startswith(('+','00')) or not 8<=len(digits)<=15 or digits.startswith('0'):
        raise ValueError('Use an international phone number including country code')
    return '+'+digits

def find_user(db:Session,identifier:str):
    identifier=identifier.strip()
    if '@' in identifier:return db.scalar(select(User).where(User.email==normalize_email(identifier)))
    try: phone=normalize_phone(identifier)
    except ValueError:return None
    return db.scalar(select(User).where(User.phone_number==phone))

def issue(db:Session,user:User,channel:str,purpose:str):
    now=datetime.utcnow();latest=db.scalar(select(AccountVerificationChallenge).where(
        AccountVerificationChallenge.user_id==user.id,AccountVerificationChallenge.purpose==purpose,
        AccountVerificationChallenge.used_at.is_(None)).order_by(AccountVerificationChallenge.created_at.desc()))
    if latest and latest.last_sent_at>now-timedelta(seconds=settings.verification_resend_seconds):
        raise HTTPException(429,'Please wait before requesting another code')
    if latest: latest.used_at=now
    code=generate_numeric_code();row=AccountVerificationChallenge(user_id=user.id,channel=channel,purpose=purpose,
        code_hash=hash_verification_secret(code),expires_at=now+timedelta(minutes=settings.account_verification_minutes),
        max_attempts=settings.verification_max_attempts,last_sent_at=now)
    db.add(row);db.commit()
    try:
        if channel=='email':send_account_email(user.email,code,purpose)
        else:send_sms(user.phone_number,code)
    except (VerificationEmailError,SmsUnavailableError):
        row.used_at=datetime.utcnow();db.commit();raise

def active_challenge(db,user,purpose):
    return db.scalar(select(AccountVerificationChallenge).where(AccountVerificationChallenge.user_id==user.id,
        AccountVerificationChallenge.purpose==purpose,AccountVerificationChallenge.used_at.is_(None),
        AccountVerificationChallenge.verified_at.is_(None))
        .order_by(AccountVerificationChallenge.created_at.desc()))

def confirm_code(db,user,purpose,code):
    row=active_challenge(db,user,purpose);now=datetime.utcnow()
    if not row or row.expires_at<=now or row.attempt_count>=row.max_attempts:raise HTTPException(400,'Invalid or expired verification code')
    if not secrets.compare_digest(row.code_hash,hash_verification_secret(code)):
        row.attempt_count+=1;db.commit();raise HTTPException(400,'Invalid or expired verification code')
    row.verified_at=now;return row

def register_account_routes(app,current_user):
    @app.post('/auth/verification/email/send')
    def email_send(body:VerificationSendRequest,db:Session=Depends(get_db)):
        user=find_user(db,body.identifier)
        if user and not user.email_verified:
            try:issue(db,user,'email',EMAIL_VERIFY)
            except (VerificationEmailError,HTTPException):pass
        return {'accepted':True,'message':'If verification is available, a code will be sent.'}

    @app.post('/auth/verification/email/confirm')
    def email_confirm(body:VerificationConfirmRequest,db:Session=Depends(get_db)):
        user=find_user(db,body.identifier)
        if not user:raise HTTPException(400,'Invalid or expired verification code')
        row=confirm_code(db,user,EMAIL_VERIFY,body.code);row.used_at=datetime.utcnow();user.email_verified=True
        if user.account_status!='DISABLED' and (not settings.phone_verification_required or user.phone_verified):user.account_status='ACTIVE'
        db.commit();return {'verified':True,'account_status':user.account_status}

    @app.post('/auth/verification/phone/send')
    def phone_send(user:User=Depends(current_user),db:Session=Depends(get_db)):
        if not user.phone_number:raise HTTPException(400,'No phone number is configured')
        try:issue(db,user,'phone',PHONE_VERIFY)
        except SmsUnavailableError:raise HTTPException(503,'SMS delivery is not configured')
        return {'accepted':True}

    @app.post('/auth/verification/phone/confirm')
    def phone_confirm(body:VerificationConfirmRequest,user:User=Depends(current_user),db:Session=Depends(get_db)):
        row=confirm_code(db,user,PHONE_VERIFY,body.code);row.used_at=datetime.utcnow();user.phone_verified=True
        if user.account_status!='DISABLED' and user.email_verified:user.account_status='ACTIVE'
        db.commit();return {'verified':True}

    @app.post('/auth/password/forgot')
    def forgot(body:VerificationSendRequest,db:Session=Depends(get_db)):
        user=find_user(db,body.identifier)
        if user and user.account_status!='DISABLED':
            try:issue(db,user,'email',PASSWORD_RESET)
            except (VerificationEmailError,HTTPException):pass
        else: hash_password(secrets.token_urlsafe(16))
        return {'accepted':True,'message':'If the account is eligible, reset instructions will be sent.'}

    @app.post('/auth/password/verify-code')
    def verify_reset(body:VerificationConfirmRequest,response:Response,db:Session=Depends(get_db)):
        response.headers['Cache-Control']='no-store';user=find_user(db,body.identifier)
        if not user or user.account_status=='DISABLED':raise HTTPException(400,'Invalid or expired verification code')
        row=confirm_code(db,user,PASSWORD_RESET,body.code);token=secrets.token_urlsafe(48)
        row.reset_token_hash=hash_verification_secret(token);row.reset_token_expires_at=datetime.utcnow()+timedelta(minutes=settings.password_reset_token_minutes)
        db.commit();return {'reset_token':token,'expires_in_seconds':settings.password_reset_token_minutes*60}

    @app.post('/auth/password/reset')
    def reset_password(body:PasswordResetRequest,db:Session=Depends(get_db)):
        now=datetime.utcnow();row=db.scalar(select(AccountVerificationChallenge).where(
            AccountVerificationChallenge.reset_token_hash==hash_verification_secret(body.reset_token),
            AccountVerificationChallenge.purpose==PASSWORD_RESET,AccountVerificationChallenge.used_at.is_(None)))
        user=db.get(User,row.user_id) if row else None
        if not row or not user or user.account_status=='DISABLED' or not row.verified_at or not row.reset_token_expires_at or row.reset_token_expires_at<=now:
            raise HTTPException(400,'Invalid or expired reset authorization')
        user.password_hash=hash_password(body.new_password);row.used_at=now;row.reset_token_hash=None
        db.execute(update(RefreshToken).where(RefreshToken.user_id==user.id,RefreshToken.revoked.is_(False)).values(revoked=True));db.commit()
        try:send_account_email(user.email,None,'PASSWORD_RESET_SUCCESS')
        except VerificationEmailError:logger.warning('password_reset_notification_failed')
        return {'reset':True}
