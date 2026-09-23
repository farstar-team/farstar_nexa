import os
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "production"
    database_url: str = "postgresql+psycopg://nexa@postgres/nexa"
    redis_url: str = "redis://redis:6379/0"
    base_url: str = "http://localhost:8080"
    secret_key: str
    encryption_keys: str
    mock_mode: bool = False
    registration_enabled: bool = True
    cookie_secure: bool = True
    session_hours: int = 24
    operations_dir: Path = Path("/runtime/operations")
    backup_dir: Path = Path("/runtime/backups")
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_verify_token: str = ""
    meta_api_version: str = "v23.0"
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_webhook_secret: str = ""

    @model_validator(mode="after")
    def validate_security(self):
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters")
        for key in self.encryption_keys.split(","):
            Fernet(key.strip().encode())
        if self.environment == "production":
            if self.mock_mode or not self.cookie_secure or not self.base_url.startswith("https://"):
                raise ValueError("Production requires HTTPS, secure cookies, and MOCK_MODE=false")
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()


def version() -> str:
    path = Path(os.environ.get("NEXA_VERSION_FILE", str(Path(__file__).resolve().parents[2] / "VERSION")))
    return path.read_text().strip() if path.exists() else "0.1.0"
