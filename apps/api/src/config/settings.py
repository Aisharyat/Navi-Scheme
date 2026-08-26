from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Look for .env in apps/api/ or project root
_API_DIR = Path(__file__).resolve().parent.parent.parent
_ROOT_DIR = _API_DIR.parent.parent


class Settings(BaseSettings):
    alloydb_instance_uri: str = ""
    alloydb_database: str = "postgres"
    alloydb_user: str = "postgres"
    alloydb_password: str | None = None
    alloydb_enable_iam_auth: bool = False
    alloydb_ip_type: str = "PRIVATE"
    google_application_credentials: str | None = None
    alloydb_host: str | None = None
    alloydb_port: int = 5432

    model_config = SettingsConfigDict(
        env_file=[_API_DIR / ".env", _ROOT_DIR / ".env", ".env"],
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

