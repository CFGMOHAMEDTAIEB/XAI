from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = 'sqlite:///./xai_platform.db'
    jwt_secret: str = 'development-only-change-me-32-characters'
    access_token_minutes: int = 15
    share_code_minutes: int = 60
    public_base_url: str = 'http://localhost:8000'
    cors_origins: str = 'http://localhost:4200,http://localhost:3000,http://localhost:5050'
    storage_path: str = './storage'
    selector_model_path: str = '../../engines/XAI-Compress/checkpoints/selector_v2/best.json'
    refresh_token_days: int = 30
    max_upload_bytes: int = 1073741824
    max_decompressed_bytes: int = 1073741824
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_username: str = ''
    smtp_password: str = ''
    smtp_from: str = ''
    smtp_security: str = 'starttls'
    smtp_timeout_seconds: int = 30
    smtp_max_attachment_bytes: int = 18000000
    admin_emails: str = ''
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]

    @property
    def storage_root(self) -> Path:
        return Path(self.storage_path).resolve()

settings = Settings()
