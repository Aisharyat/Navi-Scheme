from fastapi import APIRouter

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/health")
def user_health():
    return {"status": "user service ready"}

