from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class User(Base):
    __tablename__='users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120), default='')
    totp_secret: Mapped[str|None] = mapped_column(String(128), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(32), default='user')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class TotpEnrollment(Base):
    __tablename__ = 'totp_enrollments'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    enrollment_id: Mapped[str] = mapped_column(String(32), unique=True)
    secret: Mapped[str|None] = mapped_column(String(128), nullable=True)
    code_hash: Mapped[str|None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    code_expires_at: Mapped[datetime] = mapped_column(DateTime)
    disclosed: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    totp_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime)
    send_window_at: Mapped[datetime] = mapped_column(DateTime)
    send_count: Mapped[int] = mapped_column(Integer, default=0)

class FileRecord(Base):
    __tablename__='files'
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64))
    original_size: Mapped[int] = mapped_column(Integer)
    compressed_size: Mapped[int] = mapped_column(Integer)
    codec: Mapped[str] = mapped_column(String(64))
    source_path: Mapped[str|None] = mapped_column(String(1024), nullable=True)
    artifact_path: Mapped[str|None] = mapped_column(String(1024), nullable=True)
    integrity_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default='completed')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ShareCode(Base):
    __tablename__='share_codes'
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey('files.id'), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    recipient_email: Mapped[str] = mapped_column(String(320), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    max_downloads: Mapped[int] = mapped_column(Integer, default=1)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    anonymous_sender: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

class AuditEvent(Base):
    __tablename__='audit_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int|None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    resource: Mapped[str] = mapped_column(String(255), default='')
    result: Mapped[str] = mapped_column(String(32), default='success')
    details: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class RefreshToken(Base):
    __tablename__='refresh_tokens'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AuthenticatorDevice(Base):
    __tablename__='authenticator_devices'
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    public_key: Mapped[str] = mapped_column(Text)
    platform: Mapped[str] = mapped_column(String(32))
    app_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default='active', index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AuthChallenge(Base):
    __tablename__='auth_challenges'
    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey('authenticator_devices.id'), index=True)
    nonce: Mapped[str] = mapped_column(String(96))
    number_hash: Mapped[str] = mapped_column(String(64))
    application: Mapped[str] = mapped_column(String(120), default='XAI')
    request_context: Mapped[str] = mapped_column(Text, default='{}')
    status: Mapped[str] = mapped_column(String(24), default='pending', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    completed_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)

class AuthEvent(Base):
    __tablename__='auth_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    device_id: Mapped[int|None] = mapped_column(ForeignKey('authenticator_devices.id'), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    result: Mapped[str] = mapped_column(String(24))
    application: Mapped[str] = mapped_column(String(120), default='XAI')
    details: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class RecoveryCode(Base):
    __tablename__='recovery_codes'
    __table_args__=(UniqueConstraint('user_id','code_hash',name='uq_recovery_user_code'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    used_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)

class AuthPolicy(Base):
    __tablename__='auth_policies'
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), unique=True, default='global')
    mfa_required: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    push_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    number_matching_required: Mapped[bool] = mapped_column(Boolean, default=True)
    challenge_seconds: Mapped[int] = mapped_column(Integer, default=120)
    session_minutes: Mapped[int] = mapped_column(Integer, default=15)
