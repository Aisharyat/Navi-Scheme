import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

_SRC_DIR = Path(__file__).resolve().parent
_API_DIR = _SRC_DIR.parent
_ROOT_DIR = _API_DIR.parent.parent

if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.routes.users import router as users_router
from src.routes.admin import router as admin_router
from src.repositories.database import check_connection, close_connection
from src.repositories.scheme_repository import SchemeRepository
from src.routes.schemes import router as schemes_router
from src.repositories.user_repository import UserRepository


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Initialize tables and seed data automatically on startup
    SchemeRepository().init_database()

    # Seed default admin user
    try:
        user_repo = UserRepository()
        user_repo.seed_default_admin()
    except Exception as e:
        print(f"[INFO] Startup admin seed check: {e}")

    yield
    close_connection()


from src.config.settings import get_settings

app = FastAPI(title="Navi Scheme API", lifespan=lifespan)

# Allow cross-origin requests with explicit origins for secure credential handling
_settings = get_settings()
_allowed_origins = [o.strip() for o in _settings.cors_origins.split(",") if o.strip()]
if not _allowed_origins:
    _allowed_origins = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(schemes_router)
app.include_router(admin_router)
app.include_router(users_router)

@app.get("/health/database")
def database_health() -> dict[str, str]:
    try:
        check_connection()
    except Exception as error:
        raise HTTPException(status_code=503, detail="Database is unavailable") from error
    return {"status": "ok"}


# Mount static frontend
_WEB_PUBLIC_DIR = _ROOT_DIR / "apps" / "web" / "public"

if _WEB_PUBLIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_WEB_PUBLIC_DIR)), name="static_dir")
    app.mount("/", StaticFiles(directory=str(_WEB_PUBLIC_DIR), html=True), name="static_root")


