"""
Legacy compatibility wrapper.
Directs all database engine requests to src.repositories.database (SQLite).
"""

from src.repositories.database import (
    get_engine,
    get_db_session,
    check_connection,
    close_connection,
)

__all__ = [
    "get_engine",
    "get_db_session",
    "check_connection",
    "close_connection",
]
