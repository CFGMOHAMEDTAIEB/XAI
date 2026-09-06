from datetime import datetime, timedelta, timezone
import hashlib, secrets
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import HTTPException, status
from .config import settings

pwd = CryptContext(schemes=['pbkdf2_sha256','bcrypt'], deprecated='auto')
def hash_password(value): return pwd.hash(value)
def verify_password(value, hashed): return pwd.verify(value, hashed)
def create_token(user_id:int):
    exp=datetime.now(timezone.utc)+timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({'sub':str(user_id),'exp':exp},settings.jwt_secret,algorithm='HS256')
def create_refresh_token(): return secrets.token_urlsafe(48)
def hash_refresh_token(token:str): return hashlib.sha256(token.encode()).hexdigest()
def decode_token(token:str)->int:
    try: return int(jwt.decode(token,settings.jwt_secret,algorithms=['HS256'])['sub'])
    except (JWTError,KeyError,ValueError): raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail='Invalid token')
def generate_share_code():
    raw=secrets.token_urlsafe(9).replace('-','').replace('_','')[:12].upper()
    code='XC-'+raw[:4]+'-'+raw[4:8]+'-'+raw[8:12]
    return code, hashlib.sha256(code.encode()).hexdigest()
def hash_share_code(code): return hashlib.sha256(code.strip().upper().encode()).hexdigest()
