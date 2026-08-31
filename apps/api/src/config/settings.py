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

    # JWT Authentication
    jwt_secret_key: str = "navi-scheme-super-secret-key-change-in-production-2026"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours

    # Default Seed Admin Credentials
    default_admin_email: str = "admin@navischeme.gov.in"
    default_admin_password: str = "Admin@123"
    default_admin_name: str = "Navi Scheme Administrator"

    # Google Gemini AI & Grounding
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"

    model_config = SettingsConfigDict(
        env_file=[_API_DIR / ".env", _ROOT_DIR / ".env", ".env"],
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

