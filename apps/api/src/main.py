import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.routes.users import router as users_router
from src.routes.admin import router as admin_router
from src.repositories.alloydb import check_connection, close_connection
from src.routes.schemes import router as schemes_router
from src.repositories.user_repository import UserRepository


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Initialize DB & seed default admin
    try:
        user_repo = UserRepository()
        user_repo.seed_default_admin()
    except Exception as e:
        print(f"[INFO] Startup admin seed check: {e}")
    yield
    close_connection()


app = FastAPI(title="Navi Scheme API", lifespan=lifespan)

# Allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
        raise HTTPException(status_code=503, detail="AlloyDB is unavailable") from error
    return {"status": "ok"}


# Mount static frontend
_WEB_PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "apps" / "web" / "public"

if _WEB_PUBLIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_WEB_PUBLIC_DIR)), name="static")

    @app.get("/")
    def serve_frontend():
        index_file = _WEB_PUBLIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Navi Scheme API is running. Place index.html in apps/web/public to view the UI."}

