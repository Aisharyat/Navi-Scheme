from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from pydantic import BaseModel

from src.models.user import (
    AdminLoginRequest,
    TokenResponse,
    AdminUserResponse,
    AdminCreateRequest,
    UserModel,
)
from src.middleware.security import create_access_token, get_current_admin
from src.repositories.user_repository import UserRepository
from src.repositories.scheme_repository import SchemeRepository

router = APIRouter(prefix="/api/admin", tags=["admin"])

user_repo = UserRepository()
scheme_repo = SchemeRepository()


class SchemeCreatePayload(BaseModel):
    name: str
    title: Optional[str] = None
    issuing_level: str = "central"
    issuing_body: str = "Government of India"
    ministry: Optional[str] = None
    state: Optional[str] = "All India"
    sector: str = "social_welfare"
    category: str = "Social Welfare"
    target_gender: str = "All"
    min_age: int = 0
    max_age: int = 120
    income_limit: Optional[float] = None
    description: str
    short_description: Optional[str] = None
    benefits: str
    eligibility_summary: Optional[str] = None
    eligibility_rules: Optional[Dict[str, Any]] = {"logic": "AND", "rules": []}
    documents_required: Optional[List[str]] = []
    application_steps: Optional[List[str]] = []
    application_url: str
    application_mode: str = "online"
    deadline: Optional[str] = None
    source_urls: Optional[List[str]] = []


class SchemeUpdatePayload(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    issuing_level: Optional[str] = None
    issuing_body: Optional[str] = None
    ministry: Optional[str] = None
    state: Optional[str] = None
    sector: Optional[str] = None
    category: Optional[str] = None
    target_gender: Optional[str] = None
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    income_limit: Optional[float] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    benefits: Optional[str] = None
    eligibility_summary: Optional[str] = None
    eligibility_rules: Optional[Dict[str, Any]] = None
    documents_required: Optional[List[str]] = None
    application_steps: Optional[List[str]] = None
    application_url: Optional[str] = None
    application_mode: Optional[str] = None
    deadline: Optional[str] = None
    source_urls: Optional[List[str]] = None
    status: Optional[str] = None


@router.post("/auth/login", response_model=TokenResponse)
def admin_login(payload: AdminLoginRequest):
    """Authenticate administrator and return JWT Bearer token."""
    user = user_repo.authenticate_admin(payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={
            "sub": user.email,
            "user_id": user.id,
            "role": user.role,
            "name": user.full_name,
        }
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        role=user.role,
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
    )


@router.get("/auth/me", response_model=AdminUserResponse)
def get_admin_profile(current_admin: UserModel = Depends(get_current_admin)):
    """Fetch profile of currently logged-in administrator."""
    return AdminUserResponse(
        id=current_admin.id,
        email=current_admin.email,
        full_name=current_admin.full_name,
        role=current_admin.role,
        is_active=current_admin.is_active,
        created_at=getattr(current_admin, "created_at", None),
    )


@router.get("/analytics")
def get_admin_analytics(current_admin: UserModel = Depends(get_current_admin)):
    """Retrieve complete KPI Analytics: Coverage, Accuracy, Engagement, Freshness (§11.6)."""
    return scheme_repo.get_analytics()


@router.get("/pipeline/health")
def get_pipeline_health(current_admin: UserModel = Depends(get_current_admin)):
    """Ingestion pipeline health and staleness metrics (§11.4)."""
    # TODO: Wire real ingestion state for sources_monitored.
    # Currently returning mock data for 'last_synced'. Needs integration with the actual ingestion pipeline tracking sync times.
    analytics = scheme_repo.get_analytics()
    return {
        "status": "healthy",
        "sources_monitored": [
            {"name": "National Scholarship Portal (scholarships.gov.in)", "status": "active", "last_synced": "2026-08-25T00:00:00Z"},
            {"name": "PM-Kisan Portal (pmkisan.gov.in)", "status": "active", "last_synced": "2026-08-15T00:00:00Z"},
            {"name": "NHA Ayushman Beneficiary Portal (beneficiary.nha.gov.in)", "status": "active", "last_synced": "2026-08-28T00:00:00Z"},
            {"name": "Govt of Maharashtra Welfare Portal (ladkibahin.maharashtra.gov.in)", "status": "active", "last_synced": "2026-08-30T00:00:00Z"},
            {"name": "PMAY-U Portal (pmaymis.gov.in)", "status": "active", "last_synced": "2026-08-22T00:00:00Z"},
        ],
        "queue_depth": analytics["coverage"]["under_review"],
        "freshness_kpi": analytics["freshness"],
    }


@router.get("/schemes")
def list_admin_schemes(
    q: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    current_admin: UserModel = Depends(get_current_admin),
):
    """List schemes with query, status, state, and category filtering."""
    schemes, total = scheme_repo.get_schemes(
        query=q,
        status=status,
        state=state,
        category=category,
        limit=limit,
        offset=offset,
    )
    return {"schemes": schemes, "total": total}


@router.post("/schemes")
def create_scheme(
    payload: SchemeCreatePayload,
    current_admin: UserModel = Depends(get_current_admin),
):
    """Create new scheme in 'under_review' status."""
    created = scheme_repo.create_scheme(payload.model_dump(), admin_id=current_admin.id)
    return created


@router.patch("/schemes/{scheme_id}")
def update_scheme(
    scheme_id: str,
    payload: SchemeUpdatePayload,
    current_admin: UserModel = Depends(get_current_admin),
):
    """Partially update an existing scheme."""
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updated = scheme_repo.update_scheme(scheme_id, updates, admin_id=current_admin.id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheme not found")
    return {"status": "ok", "scheme": updated}


@router.post("/schemes/{scheme_id}/publish")
def publish_scheme(
    scheme_id: str,
    current_admin: UserModel = Depends(get_current_admin),
):
    """Publish gate: enforces non-empty structured eligibility rules (§6.3)."""
    ok, msg = scheme_repo.publish_scheme(scheme_id, admin_id=current_admin.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=msg,
        )
    return {"status": "ok", "message": msg}


@router.post("/schemes/{scheme_id}/unpublish")
def unpublish_scheme(
    scheme_id: str,
    current_admin: UserModel = Depends(get_current_admin),
):
    """Revert a published scheme back to under_review (draft)."""
    ok, msg = scheme_repo.unpublish_scheme(scheme_id, admin_id=current_admin.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/schemes/{scheme_id}/archive")
def archive_scheme(
    scheme_id: str,
    current_admin: UserModel = Depends(get_current_admin),
):
    """Archive a scheme (set status = 'archived')."""
    ok, msg = scheme_repo.archive_scheme(scheme_id, admin_id=current_admin.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    return {"status": "ok", "message": msg}


@router.delete("/schemes/{scheme_id}")
def delete_scheme(
    scheme_id: str,
    current_admin: UserModel = Depends(get_current_admin),
):
    """Delete a scheme record from the database."""
    ok, msg = scheme_repo.delete_scheme(scheme_id, admin_id=current_admin.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    return {"status": "ok", "message": msg}


# -------------------------------------------------------------
# Admin User Management Routes (Fix 6)
# -------------------------------------------------------------

@router.get("/users", response_model=List[AdminUserResponse])
@router.get("/admins", response_model=List[AdminUserResponse])
def list_admin_users(current_admin: UserModel = Depends(get_current_admin)):
    """List all administrator accounts in the system."""
    admins = user_repo.list_admins()
    return [
        AdminUserResponse(
            id=a.id,
            email=a.email,
            full_name=a.full_name,
            role=a.role,
            is_active=a.is_active,
            created_at=getattr(a, "created_at", None),
        )
        for a in admins
    ]


@router.post("/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
@router.post("/admins", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
def create_admin_user(
    payload: AdminCreateRequest,
    current_admin: UserModel = Depends(get_current_admin),
):
    """Create a new administrator account (restricted to existing authenticated admins)."""
    admin_user, error = user_repo.create_admin(payload)
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    return AdminUserResponse(
        id=admin_user.id,
        email=admin_user.email,
        full_name=admin_user.full_name,
        role=admin_user.role,
        is_active=admin_user.is_active,
        created_at=getattr(admin_user, "created_at", None),
    )


@router.patch("/users/{user_id}/deactivate")
@router.post("/users/{user_id}/deactivate")
def deactivate_admin_user(
    user_id: int,
    current_admin: UserModel = Depends(get_current_admin),
):
    """Deactivate an admin account. Enforces that the last remaining active admin cannot be deactivated."""
    ok, msg = user_repo.deactivate_admin(user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"status": "ok", "message": msg}

