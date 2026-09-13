from pydantic import BaseModel, EmailStr, Field, field_validator

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    full_name: str = Field(min_length=1,max_length=120)
    phone_number: str = Field(min_length=8,max_length=32)
    @field_validator('full_name')
    @classmethod
    def clean_name(cls,value):
        value=' '.join(value.split())
        if not value: raise ValueError('Full name is required')
        return value
    @field_validator('password')
    @classmethod
    def password_size(cls,value):
        if len(value.encode('utf-8'))>72:raise ValueError('Password exceeds hashing limit')
        return value
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str|None = None
class IdentifierRequest(BaseModel):
    identifier: str = Field(min_length=3,max_length=320)
class VerificationSendRequest(IdentifierRequest): pass
class VerificationConfirmRequest(IdentifierRequest):
    model_config={'extra':'forbid','hide_input_in_errors':True}
    code: str = Field(pattern=r'^\d{6}$')
class PasswordResetRequest(BaseModel):
    model_config={'extra':'forbid','hide_input_in_errors':True}
    reset_token: str = Field(min_length=32,max_length=256)
    new_password: str = Field(min_length=10)
    @field_validator('new_password')
    @classmethod
    def password_size(cls,value):
        if len(value.encode('utf-8'))>72:raise ValueError('Password exceeds hashing limit')
        return value
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str|None = None
    token_type: str = 'bearer'
class RefreshRequest(BaseModel):
    refresh_token: str
class FileCreate(BaseModel):
    name: str
    sha256: str = Field(pattern=r'^[0-9a-fA-F]{64}$')
    original_size: int = Field(ge=0)
    compressed_size: int = Field(ge=0)
    codec: str
class ShareCreate(BaseModel):
    file_id: int
    recipient_email: EmailStr
    expires_minutes: int = Field(default=60, ge=5, le=10080)
    max_downloads: int = Field(default=1, ge=1, le=100)
    anonymous_sender: bool = False
class ShareRedeem(BaseModel):
    code: str = Field(min_length=8, max_length=32)

class EmailSend(BaseModel):
    recipient_email: EmailStr

class TotpConfirm(BaseModel):
    model_config = {'extra': 'forbid', 'hide_input_in_errors': True}
    code: str = Field(pattern=r'^[0-9]{6}$')
    enrollment_id: str = Field(pattern=r'^[0-9a-f]{32}$')

class TotpStart(BaseModel):
    model_config = {'extra': 'forbid', 'hide_input_in_errors': True}
    restart: bool = False
