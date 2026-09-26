import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import field_validator, model_validator
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
    meta_api_version: str = "v26.0"
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_webhook_secret: str = ""
    exchange_provider: str = "open_er_api"
    exchange_cache_ttl: int = 86400
    bonbast_api_url: str = "https://www.bonbast.com/api"
    bonbast_username: str = ""
    bonbast_hash: str = ""

    @field_validator("exchange_cache_ttl")
    @classmethod
    def cache_ttl_range(cls, value):
        if not 3600 <= value <= 86400:
            raise ValueError("EXCHANGE_CACHE_TTL must be between 3600 and 86400 seconds")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("BASE_URL must be an HTTP(S) origin without credentials or a path")
        # Accessing port also validates malformed or out-of-range ports.
        parsed.port
        return value

    @property
    def public_urls(self) -> dict[str, str]:
        return {
            "base_url": self.base_url,
            "instagram_callback": self.base_url + "/api/instagram/callback",
            "meta_webhook": self.base_url + "/webhooks/meta",
            "telegram_webhook": self.base_url + "/webhooks/telegram",
        }

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
    return path.read_text().strip() if path.exists() else "0.2.1"
