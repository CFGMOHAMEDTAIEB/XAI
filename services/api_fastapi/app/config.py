from pathlib import Path
from urllib.parse import urlsplit
from pydantic import model_validator, Field
import secrets
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = 'development'
    database_url: str = Field(default='sqlite:///./xai_platform.db', repr=False)
    jwt_secret: str = Field(default='', repr=False)
    xai_seed_admin: bool = False
    xai_seed_admin_email: str = Field(default='', repr=False)
    xai_seed_admin_password: str = Field(default='', repr=False)
    access_token_minutes: int = 15
    share_code_minutes: int = 60
    public_base_url: str = 'http://localhost:8000'
    cors_origins: str = 'http://localhost:4200,http://localhost:3000,http://localhost:5050'
    storage_path: str = './storage'
    selector_model_path: str = 'engines/XAI-Compress/checkpoints/selector_v2/best.json'
    refresh_token_days: int = 30
    max_upload_bytes: int = 1073741824
    max_decompressed_bytes: int = 1073741824
    email_provider: str = 'smtp'
    brevo_api_key: str = Field(default='', repr=False)
    brevo_sender_email: str = ''
    brevo_sender_name: str = 'XAI Compress'
    resend_api_key: str = Field(default='', repr=False)
    resend_from_email: str = ''
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_username: str = ''
    smtp_password: str = Field(default='', repr=False)
    smtp_from: str = ''
    smtp_from_name: str = 'XAI Compress'
    smtp_security: str = 'starttls'
    smtp_timeout_seconds: int = 30
    smtp_max_attachment_bytes: int = 18000000
    admin_emails: str = ''
    clamav_host: str = 'clamav'
    clamav_port: int = 3310
    security_scan_required: bool = True
    security_scan_timeout: int = 60
    yara_rules_path: str = ''
    max_heavy_requests: int = 2
    min_free_disk_bytes: int = 1073741824
    upload_idle_timeout: int = 30
    upload_total_timeout: int = 300
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', hide_input_in_errors=True)

    @model_validator(mode='after')
    def resolve_runtime_paths(self):
        if not self.yara_rules_path:
            self.yara_rules_path = str(Path(__file__).resolve().parent.parent / 'security/yara' /
                                       ('production' if self.app_env == 'production' else 'test'))
        selector = Path(self.selector_model_path).expanduser()
        if not selector.is_absolute():
            repository = next((parent for parent in Path(__file__).resolve().parents
                               if (parent / 'engines/XAI-Compress').is_dir()), None)
            if repository is not None:
                selector = repository / selector
            elif self.selector_model_path == 'engines/XAI-Compress/checkpoints/selector_v2/best.json':
                import xai_compress
                selector = Path(xai_compress.__file__).resolve().parent.parent / 'checkpoints/selector_v2/best.json'
            else:
                selector = Path(__file__).resolve().parent.parent / selector
        self.selector_model_path = str(selector.resolve())
        return self

    @model_validator(mode='after')
    def validate_production(self):
        if self.email_provider not in ('smtp', 'resend', 'brevo', 'mailpit'):
            raise ValueError('EMAIL_PROVIDER must be smtp, resend, brevo or mailpit')
        if self.smtp_security not in ('starttls','ssl','none'):
            raise ValueError('SMTP_SECURITY must be starttls, ssl or none')
        if not 1 <= self.smtp_port <= 65535 or not 1 <= self.clamav_port <= 65535:
            raise ValueError('Service ports must be between 1 and 65535')
        if self.smtp_timeout_seconds <= 0:
            raise ValueError('SMTP_TIMEOUT_SECONDS must be positive')
        if any(value <= 0 for value in (self.max_upload_bytes, self.max_decompressed_bytes,
               self.max_heavy_requests, self.min_free_disk_bytes, self.upload_idle_timeout,
               self.upload_total_timeout, self.security_scan_timeout)):
            raise ValueError('Resource limits must be positive')
        if self.app_env not in ('development','production'):
            raise ValueError('APP_ENV must be development or production')
        if self.app_env == 'production':
            if self.email_provider == 'mailpit':
                raise ValueError('Mailpit is development-only')
            if self.email_provider == 'smtp' and self.smtp_security == 'none':
                raise ValueError('Production SMTP requires certificate-verified TLS')
            if not self.security_scan_required:
                raise ValueError('Production requires security scanning')
            if 'test' in Path(self.yara_rules_path).parts:
                raise ValueError('Production cannot load test YARA rules')
            secret_marker = self.jwt_secret.lower()
            if (len(self.jwt_secret) < 32 or 'replace' in secret_marker
                    or 'development' in secret_marker or 'changeme' in secret_marker
                    or (secret_marker.startswith('eyj') and self.jwt_secret.count('.') == 2)):
                raise ValueError('Production JWT_SECRET must be a configured random secret')
            if not self.database_url.startswith('postgresql+psycopg://') or 'REPLACE_' in self.database_url:
                raise ValueError('Production DATABASE_URL must use configured PostgreSQL/psycopg')
            for origin in self.allowed_origins:
                parsed=urlsplit(origin)
                if parsed.scheme!='https' or not parsed.hostname or '*' in origin or parsed.hostname in ('localhost','127.0.0.1','10.0.2.2','backend') or 'REPLACE_' in origin or parsed.path or parsed.query or parsed.fragment or parsed.username:
                    raise ValueError('Production CORS_ORIGINS must contain exact public HTTPS origins')
            if not self.allowed_origins: raise ValueError('Production CORS_ORIGINS must be configured')
        elif not self.jwt_secret:
            self.jwt_secret = secrets.token_urlsafe(48)
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]

    @property
    def storage_root(self) -> Path:
        return Path(self.storage_path).resolve()

settings = Settings()
