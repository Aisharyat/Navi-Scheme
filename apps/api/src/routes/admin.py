from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.models.user import AdminLoginRequest, TokenResponse, AdminUserResponse, UserModel
from src.models.scheme import (
    SchemeCreateRequest,
    SchemeUpdateRequest,
    SchemeResponse,
    AdminStatsResponse,
    AdminSchemeListResponse,
)
from src.middleware.security import create_access_token, get_current_admin
from src.repositories.user_repository import UserRepository
from src.repositories.scheme_repository import SchemeRepository

router = APIRouter(prefix="/api/admin", tags=["admin"])

user_repo = UserRepository()
scheme_repo = SchemeRepository()


# -------------------------------------------------------------
# Admin Authentication Endpoints
# -------------------------------------------------------------
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


# -------------------------------------------------------------
# Admin Dashboard & Statistics
# -------------------------------------------------------------
@router.get("/stats", response_model=AdminStatsResponse)
def get_dashboard_stats(current_admin: UserModel = Depends(get_current_admin)):
    """Retrieve aggregate statistics on cataloged schemes."""
    stats = scheme_repo.get_admin_stats()
    return stats


# -------------------------------------------------------------
# Admin Scheme CRUD Operations
# -------------------------------------------------------------
@router.get("/schemes")
def list_admin_schemes(
    q: Optional[str] = Query(None, description="Search query in schemes"),
    state: Optional[str] = Query(None, description="Filter by state"),
    category: Optional[str] = Query(None, description="Filter by category"),
    is_active: Optional[bool] = Query(None, description="Filter by active/inactive"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_admin: UserModel = Depends(get_current_admin),
):
    """Retrieve catalog of all schemes with admin controls."""
    schemes, total = scheme_repo.get_admin_schemes(
        query=q,
        state=state,
        category=category,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "schemes": schemes,
    }


@router.post("/schemes", status_code=status.HTTP_201_CREATED)
def create_new_scheme(
    payload: SchemeCreateRequest,
    current_admin: UserModel = Depends(get_current_admin),
):
    """Add a new government scheme to AlloyDB."""
    created = scheme_repo.create_scheme(payload)
    return {
        "message": "Scheme created successfully",
        "scheme": created,
    }


@router.get("/schemes/{scheme_id}")
def get_admin_scheme_detail(
    scheme_id: str,
    current_admin: UserModel = Depends(get_current_admin),
):
    """Get single scheme for admin viewing/editing."""
    scheme = scheme_repo.get_scheme_by_id_or_slug(scheme_id)
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return scheme


@router.put("/schemes/{scheme_id}")
def update_existing_scheme(
    scheme_id: int,
    payload: SchemeUpdateRequest,
    current_admin: UserModel = Depends(get_current_admin),
):
    """Update details of an existing scheme."""
    updated = scheme_repo.update_scheme(scheme_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Scheme not found for update")
    return {
        "message": "Scheme updated successfully",
        "scheme": updated,
    }


@router.patch("/schemes/{scheme_id}/toggle-status")
def toggle_scheme_active_status(
    scheme_id: int,
    current_admin: UserModel = Depends(get_current_admin),
):
    """Toggle scheme active/inactive status."""
    toggled = scheme_repo.toggle_scheme_status(scheme_id)
    if not toggled:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return {
        "message": f"Scheme status updated to {'Active' if toggled.get('is_active') else 'Inactive'}",
        "scheme": toggled,
    }


@router.delete("/schemes/{scheme_id}")
def delete_scheme_record(
    scheme_id: int,
    current_admin: UserModel = Depends(get_current_admin),
):
    """Delete a scheme record from the database."""
    success = scheme_repo.delete_scheme(scheme_id)
    if not success:
        raise HTTPException(status_code=404, detail="Scheme not found for deletion")
    return {"message": "Scheme deleted successfully", "deleted_id": scheme_id}

