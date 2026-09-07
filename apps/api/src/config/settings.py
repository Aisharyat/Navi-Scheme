from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Look for .env in apps/api/ or project root
_API_DIR = Path(__file__).resolve().parent.parent.parent
_ROOT_DIR = _API_DIR.parent.parent


class Settings(BaseSettings):
    # App & Runtime
    app_name: str = "Navi Scheme"
    node_env: str = "development"
    default_language: str = "en"
    supported_languages: str = "en,hi"
    rate_limit_rpm: int = 60
    guest_chat_limit: int = 5
    cors_origins: str = "http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000,http://127.0.0.1:3000,http://localhost:5173"

    # Database connection URL (Default: local SQLite database for zero-cost localhost dev & deploy)
    db_driver: str = "sqlite"
    database_url: str = "sqlite:///./navi_scheme.db"
    sqlite_path: str = "./navi_scheme.db"

    # Optional AlloyDB specific settings (preserved for GCP cloud deployment)
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
    jwt_secret_key: str = "navi-scheme-jwt-secret-key-production-2026-secure-token"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 10080  # 7 days for citizens
    admin_token_expire_minutes: int = 120  # 2 hours for admin

    # Default Seed Admin Credentials
    admin_bootstrap_email: str = "admin@navischeme.gov.in"
    default_admin_email: str = "admin@navischeme.gov.in"
    default_admin_password: str = "Admin@123"
    default_admin_name: str = "Navi Scheme Administrator"

    # Google Gemini AI & Grounding
    gemini_api_key: str | None = "AQ.Ab8RN6KcGw9SWdXPdXuO5PaX34-e-hg67CTt3LK7RSq6dxzz4Q"
    gemini_model: str = "gemini-3.7-flash"
    gemini_max_output_tokens: int = 2048
    gemini_timeout_ms: int = 8000

    model_config = SettingsConfigDict(
        env_file=[_API_DIR / ".env", _ROOT_DIR / ".env", ".env"],
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


