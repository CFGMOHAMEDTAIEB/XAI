from datetime import datetime, timedelta
from pathlib import Path
import base64, hashlib, io, os, shutil, pyotp, qrcode, secrets
from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .config import settings
from .db import Base, engine, get_db
from .models import User, FileRecord, ShareCode, AuditEvent, RefreshToken
from .schemas import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest, FileCreate, ShareCreate, ShareRedeem
from .security import hash_password, verify_password, create_token, create_refresh_token, hash_refresh_token, decode_token, generate_share_code, hash_share_code
from .schemas import EmailSend, TotpConfirm
from .email_service import send_artifact
import smtplib

Base.metadata.create_all(engine)
app=FastAPI(title='XAI-Compress Platform API',version='0.1.0')
app.add_middleware(CORSMiddleware,allow_origins=settings.allowed_origins,allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
settings.storage_root.mkdir(parents=True,exist_ok=True)

def token_pair(db:Session,user:User):
    raw=create_refresh_token()
    db.add(RefreshToken(user_id=user.id,token_hash=hash_refresh_token(raw),expires_at=datetime.utcnow()+timedelta(days=settings.refresh_token_days)))
    db.commit()
    return TokenResponse(access_token=create_token(user.id),refresh_token=raw)

def current_user(authorization:str=Header(default=''),db:Session=Depends(get_db)):
    if not authorization.startswith('Bearer '): raise HTTPException(401,'Bearer token required')
    uid=decode_token(authorization[7:]); user=db.get(User,uid)
    if not user: raise HTTPException(401,'User not found')
    return user

def audit(db,user_id,action,resource='',result='success',details=''):
    db.add(AuditEvent(user_id=user_id,action=action,resource=resource,result=result,details=details)); db.commit()

def require_admin(user:User=Depends(current_user)):
    if user.role!='admin' and user.email not in {x.strip().lower() for x in settings.admin_emails.split(',') if x.strip()}:
        raise HTTPException(403,'Admin role required')
    return user

@app.get('/health')
def health():
    selector=Path(settings.selector_model_path)
    return {'status':'ok','service':'xai-platform-api','compression':{'mode':'hybrid-v2','runtime_generation':'v3','routing':'top3','selector_v2':selector.is_file()}}

@app.post('/auth/register',response_model=TokenResponse)
def register(body:RegisterRequest,db:Session=Depends(get_db)):
    if db.scalar(select(User).where(User.email==body.email.lower())): raise HTTPException(409,'Email already registered')
    user=User(email=body.email.lower(),password_hash=hash_password(body.password),display_name=body.display_name)
    db.add(user); db.commit(); db.refresh(user); audit(db,user.id,'user.register')
    return token_pair(db,user)

@app.post('/auth/login',response_model=TokenResponse)
def login(body:LoginRequest,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==body.email.lower()))
    if not user or not verify_password(body.password,user.password_hash): raise HTTPException(401,'Invalid credentials')
    if user.totp_enabled and (not body.totp_code or not pyotp.TOTP(user.totp_secret).verify(body.totp_code,valid_window=1)):
        raise HTTPException(401,'Valid TOTP code required')
    audit(db,user.id,'user.login'); return token_pair(db,user)

@app.post('/auth/refresh',response_model=TokenResponse)
def refresh(body:RefreshRequest,db:Session=Depends(get_db)):
    row=db.scalar(select(RefreshToken).where(RefreshToken.token_hash==hash_refresh_token(body.refresh_token)))
    if not row or row.revoked or row.expires_at<datetime.utcnow(): raise HTTPException(401,'Invalid refresh token')
    row.revoked=True; user=db.get(User,row.user_id); db.commit()
    if not user: raise HTTPException(401,'User not found')
    return token_pair(db,user)

@app.post('/auth/logout')
def logout(body:RefreshRequest,db:Session=Depends(get_db)):
    row=db.scalar(select(RefreshToken).where(RefreshToken.token_hash==hash_refresh_token(body.refresh_token)))
    if row: row.revoked=True; db.commit()
    return {'logged_out':True}

@app.get('/auth/me')
def me(user:User=Depends(current_user)):
    return {'id':user.id,'email':user.email,'display_name':user.display_name,'role':user.role,'mfa_enabled':user.totp_enabled}

@app.post('/auth/totp/enroll')
def totp_enroll(user:User=Depends(current_user),db:Session=Depends(get_db)):
    if user.totp_enabled: raise HTTPException(409,'TOTP is already enabled; enrollment cannot replace an active factor')
    secret=pyotp.random_base32(); user.totp_secret=secret; user.totp_enabled=False; db.commit()
    uri=pyotp.TOTP(secret).provisioning_uri(name=user.email,issuer_name='XAI-Compress')
    img=qrcode.make(uri); buf=io.BytesIO(); img.save(buf,format='PNG')
    return {'secret':secret,'otpauth_uri':uri,'qr_png_base64':base64.b64encode(buf.getvalue()).decode()}

@app.post('/auth/totp/confirm')
def totp_confirm(body:TotpConfirm,user:User=Depends(current_user),db:Session=Depends(get_db)):
    if not user.totp_secret or not pyotp.TOTP(user.totp_secret).verify(body.code,valid_window=1): raise HTTPException(400,'Invalid TOTP code')
    user.totp_enabled=True; db.commit(); audit(db,user.id,'totp.enabled'); return {'enabled':True}

@app.post('/files')
def create_file(body:FileCreate,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=FileRecord(owner_id=user.id,**body.model_dump()); db.add(row); db.commit(); db.refresh(row); audit(db,user.id,'file.recorded',str(row.id))
    return {'id':row.id,**body.model_dump()}

@app.post('/compression/jobs')
def compress_upload(upload:UploadFile=File(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    job_key=secrets.token_hex(12); job_dir=settings.storage_root/str(user.id)/job_key; job_dir.mkdir(parents=True,exist_ok=False)
    safe_name=safe_upload_name(upload.filename); source=job_dir/'source.bin'; artifact=job_dir/'artifact.xaic'; restored=job_dir/'verified.bin'
    digest=hashlib.sha256(); size=0
    try:
        with source.open('wb') as target:
            while chunk:=upload.file.read(1024*1024):
                size+=len(chunk)
                if size>settings.max_upload_bytes: raise HTTPException(413,'Upload too large')
                digest.update(chunk); target.write(chunk)
    except Exception:
        shutil.rmtree(job_dir); raise
    try:
        from xai_compress.compression import compress_file, decompress_file
        info=compress_file(source,artifact,mode='hybrid-v2',profile='balanced',selector_model=settings.selector_model_path,overwrite=True)
        decompress_file(artifact,restored,overwrite=True)
        verified=digest.hexdigest()==hashlib.sha256(restored.read_bytes()).hexdigest()
        if not verified: raise RuntimeError('round-trip SHA-256 mismatch')
    except Exception as exc:
        shutil.rmtree(job_dir)
        audit(db,user.id,'compression.failed',job_key,'failure',str(exc)); raise HTTPException(500,f'Compression failed: {exc}')
    row=FileRecord(owner_id=user.id,name=safe_name,sha256=digest.hexdigest(),original_size=size,compressed_size=artifact.stat().st_size,
        codec='hybrid-v3-top3',source_path=str(source),artifact_path=str(artifact),integrity_verified=True,status='completed')
    db.add(row); db.commit(); db.refresh(row); restored.unlink(missing_ok=True); audit(db,user.id,'compression.completed',str(row.id))
    return {'id':row.id,'job_id':job_key,'name':row.name,'status':row.status,'codec':row.codec,'original_size':row.original_size,
            'compressed_size':row.compressed_size,'sha256':row.sha256,'integrity_verified':row.integrity_verified,'engine':info}

@app.get('/files/{file_id}/download')
def download_artifact(file_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=db.get(FileRecord,file_id)
    if not row or row.owner_id!=user.id or not row.artifact_path: raise HTTPException(404,'File not found')
    return FileResponse(row.artifact_path,filename=f'{row.name}.xaic',media_type='application/octet-stream')

@app.post('/compression/decompress')
def decompress_upload(upload:UploadFile=File(...),user:User=Depends(current_user)):
    work=settings.storage_root/str(user.id)/f'decompress-{secrets.token_hex(8)}'; work.mkdir(parents=True)
    artifact=work/'input.xaic'; restored=work/'restored.bin'
    filename=safe_upload_name(upload.filename)
    if filename.lower().endswith('.xaic'): filename=filename[:-5]
    filename=safe_upload_name(filename)
    try:
        size=0
        with artifact.open('wb') as target:
            while chunk:=upload.file.read(1024*1024):
                size+=len(chunk)
                if size>settings.max_upload_bytes: raise HTTPException(413,'Upload too large')
                target.write(chunk)
        with artifact.open('rb') as probe:
            prefix=probe.read(5)
        if len(prefix)!=5 or prefix[:4]!=b'XAIC' or prefix[4] not in (1,2,3,5,6):
            raise HTTPException(400,'Invalid or unsupported lossless XAIC container')
        from xai_compress.compression import decompress_file
        decompress_file(artifact,restored,overwrite=True,max_output_size=settings.max_decompressed_bytes)
        with restored.open('rb') as result_file:
            digest=hashlib.file_digest(result_file,'sha256').hexdigest()
    except HTTPException:
        shutil.rmtree(work); raise
    except Exception:
        shutil.rmtree(work); raise HTTPException(400,'Invalid XAIC attachment: format, size or integrity validation failed')
    return FileResponse(restored,filename=filename,media_type='application/octet-stream',
                        headers={'X-Content-SHA256':digest},background=BackgroundTask(shutil.rmtree,work))

def safe_upload_name(filename):
    name=(filename or 'upload.bin').replace('\\','/').rsplit('/',1)[-1]
    name=''.join(c for c in name if ord(c)>=32 and c not in ':<>"|?*').strip(' .')
    return name[:180] or 'upload.bin'

@app.post('/files/{file_id}/email')
def email_artifact(file_id:int,body:EmailSend,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=db.get(FileRecord,file_id)
    if not row or row.owner_id!=user.id or not row.artifact_path or not row.integrity_verified:
        raise HTTPException(404,'Verified artifact not found')
    try:
        result=send_artifact(Path(row.artifact_path),f'{row.name}.xaic',str(body.recipient_email))
    except ValueError as exc: raise HTTPException(503,str(exc))
    except (OSError,smtplib.SMTPException):
        audit(db,user.id,'email.failed',str(file_id),'failure','SMTP delivery failed')
        raise HTTPException(502,'SMTP delivery failed; check provider and server configuration')
    audit(db,user.id,'email.accepted',str(file_id))
    return result

@app.get('/history')
def history(user:User=Depends(current_user),db:Session=Depends(get_db)):
    files=db.scalars(select(FileRecord).where(FileRecord.owner_id==user.id).order_by(FileRecord.created_at.desc())).all()
    return [{'id':f.id,'name':f.name,'codec':f.codec,'original_size':f.original_size,'compressed_size':f.compressed_size,'sha256':f.sha256,'created_at':f.created_at,'status':f.status,'integrity_verified':f.integrity_verified} for f in files]

@app.post('/shares')
def create_share(body:ShareCreate,user:User=Depends(current_user),db:Session=Depends(get_db)):
    file=db.get(FileRecord,body.file_id)
    if not file or file.owner_id!=user.id: raise HTTPException(404,'File not found')
    code,digest=generate_share_code(); row=ShareCode(file_id=file.id,sender_id=user.id,recipient_email=body.recipient_email.lower(),code_hash=digest,
        expires_at=datetime.utcnow()+timedelta(minutes=body.expires_minutes),max_downloads=body.max_downloads,anonymous_sender=body.anonymous_sender)
    db.add(row); db.commit(); audit(db,user.id,'share.created',str(file.id))
    return {'share_code':code,'expires_at':row.expires_at,'recipient_email':row.recipient_email,'email_delivery':'not_configured_in_mvp'}

@app.post('/shares/redeem')
def redeem(body:ShareRedeem,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=db.scalar(select(ShareCode).where(ShareCode.code_hash==hash_share_code(body.code)))
    if not row or row.revoked or row.expires_at<datetime.utcnow() or row.download_count>=row.max_downloads: raise HTTPException(404,'Invalid or expired code')
    if row.recipient_email!=user.email: raise HTTPException(403,'Code is not assigned to this account')
    file=db.get(FileRecord,row.file_id); row.download_count+=1; db.commit(); audit(db,user.id,'share.redeemed',str(row.id))
    return {'file':{'id':file.id,'name':file.name,'sha256':file.sha256,'original_size':file.original_size,'compressed_size':file.compressed_size,'codec':file.codec},
            'sender':None if row.anonymous_sender else row.sender_id,'remaining_downloads':row.max_downloads-row.download_count}

@app.get('/public/shares/{code}')
def public_share(code:str,db:Session=Depends(get_db)):
    row=db.scalar(select(ShareCode).where(ShareCode.code_hash==hash_share_code(code)))
    if not row or row.revoked or row.expires_at<datetime.utcnow() or row.download_count>=row.max_downloads: raise HTTPException(404,'Invalid or expired code')
    file=db.get(FileRecord,row.file_id)
    return {'code':code,'file_name':file.name,'original_size':file.original_size,'compressed_size':file.compressed_size,'codec':file.codec,'expires_at':row.expires_at,'authentication_required':True}

@app.get('/admin/stats')
def admin_stats(_:User=Depends(require_admin),db:Session=Depends(get_db)):
    original=db.scalar(select(func.coalesce(func.sum(FileRecord.original_size),0))) or 0; compressed=db.scalar(select(func.coalesce(func.sum(FileRecord.compressed_size),0))) or 0
    return {'activeUsers':db.scalar(select(func.count()).select_from(User)) or 0,'jobsToday':db.scalar(select(func.count()).select_from(FileRecord)) or 0,
            'bytesSaved':max(0,original-compressed),'openIncidents':0,'quarantinedFiles':0,'losslessSuccessRate':100.0}

@app.get('/admin/users')
def admin_users(_:User=Depends(require_admin),db:Session=Depends(get_db)):
    return [{'id':u.id,'email':u.email,'displayName':u.display_name,'role':u.role,'status':'active','mfaEnabled':u.totp_enabled,'createdAt':u.created_at,'lastLogin':None} for u in db.scalars(select(User).order_by(User.created_at.desc())).all()]

@app.get('/admin/jobs')
def admin_jobs(_:User=Depends(require_admin),db:Session=Depends(get_db)):
    rows=db.execute(select(FileRecord,User).join(User,FileRecord.owner_id==User.id).order_by(FileRecord.created_at.desc())).all()
    return [{'id':str(f.id),'fileName':f.name,'userEmail':u.email,'mode':f.codec,'status':f.status,'originalSize':f.original_size,'compressedSize':f.compressed_size,'integrityVerified':f.integrity_verified,'createdAt':f.created_at} for f,u in rows]

@app.get('/admin/audit')
def admin_audit(_:User=Depends(require_admin),db:Session=Depends(get_db)):
    return [{'id':e.id,'actor':str(e.user_id or 'system'),'action':e.action,'resource':e.resource,'result':e.result,'ipAddress':'','createdAt':e.created_at} for e in db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(500)).all()]
