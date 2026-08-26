import os
from pathlib import Path
from google.cloud.alloydb.connector import Connector, IPTypes
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from src.config.settings import get_settings


_connector: Connector | None = None
_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def get_engine() -> Engine:
    global _connector, _engine, _session_factory

    if _engine is not None:
        return _engine

    settings = get_settings()

    # Set GOOGLE_APPLICATION_CREDENTIALS if configured in settings
    if settings.google_application_credentials:
        cred_path = Path(settings.google_application_credentials)
        if not cred_path.is_absolute():
            # Check relative to apps/api or project root
            base_dir = Path(__file__).resolve().parent.parent.parent
            if (base_dir / cred_path).exists():
                cred_path = (base_dir / cred_path).resolve()
            elif (base_dir.parent.parent / cred_path).exists():
                cred_path = (base_dir.parent.parent / cred_path).resolve()
        if cred_path.exists():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(cred_path)

    # Option A: Direct host/port connection (e.g. AlloyDB Auth Proxy or direct IP)
    if settings.alloydb_host:
        password_part = f":{settings.alloydb_password}" if settings.alloydb_password else ""
        db_url = f"postgresql+pg8000://{settings.alloydb_user}{password_part}@{settings.alloydb_host}:{settings.alloydb_port}/{settings.alloydb_database}"
        _engine = create_engine(db_url, pool_pre_ping=True)
        return _engine

    # Option B: Google Cloud AlloyDB Connector
    _connector = Connector()
    ip_type = IPTypes.PUBLIC if settings.alloydb_ip_type.upper() == "PUBLIC" else IPTypes.PRIVATE

    def get_connection():
        return _connector.connect(
            settings.alloydb_instance_uri,
            "pg8000",
            user=settings.alloydb_user,
            password=settings.alloydb_password,
            db=settings.alloydb_database,
            enable_iam_auth=settings.alloydb_enable_iam_auth,
            ip_type=ip_type,
        )

    _engine = create_engine("postgresql+pg8000://", creator=get_connection, pool_pre_ping=True)
    return _engine


def get_db_session() -> Session:
    """Yield a managed SQLAlchemy session for database operations."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    db = _session_factory()
    try:
        yield db
    finally:
        db.close()


def check_connection() -> None:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


def close_connection() -> None:
    global _connector, _engine, _session_factory

    if _engine is not None:
        _engine.dispose()
        _engine = None
    if _connector is not None:
        _connector.close()
        _connector = None
    _session_factory = None

