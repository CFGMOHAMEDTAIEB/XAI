from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = 'sqlite:///./xai_platform.db'
    jwt_secret: str = 'development-only-change-me-32-characters'
    access_token_minutes: int = 15
    share_code_minutes: int = 60
    public_base_url: str = 'http://localhost:8000'
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

settings = Settings()
