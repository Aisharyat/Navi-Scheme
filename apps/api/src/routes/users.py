from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.models.user import (
    UserModel,
    CustomerRegisterRequest,
    CustomerLoginRequest,
    CustomerProfileResponse,
    CustomerProfileUpdateRequest,
    TokenResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
)
from src.middleware.security import (
    create_access_token,
    get_current_user,
    security_scheme,
    revoke_token,
    create_password_reset_token,
    decode_password_reset_token,
    HTTPAuthorizationCredentials,
)
from src.repositories.user_repository import UserRepository
from src.repositories.scheme_repository import SchemeRepository

router = APIRouter(prefix="/api/user", tags=["user"])

user_repo = UserRepository()
scheme_repo = SchemeRepository()


class ApplicationStatusUpdateRequest(BaseModel):
    status: str  # not_started | applying | submitted | approved | rejected | need_help
    notes: Optional[str] = None


# -------------------------------------------------------------
# Citizen Authentication Routes
# -------------------------------------------------------------
@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_citizen(payload: CustomerRegisterRequest):
    """Register a new citizen account."""
    user, error = user_repo.register_customer(payload)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    # Link session if provided
    if payload.session_id:
        try:
            scheme_repo.link_session_to_user(payload.session_id, str(user.id))
        except Exception:
            pass

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


@router.post("/auth/login", response_model=TokenResponse)
def login_citizen(payload: CustomerLoginRequest):
    """Authenticate citizen credentials and return JWT Bearer token."""
    user = user_repo.authenticate_customer(payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid citizen email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Link guest session if provided
    if payload.session_id:
        try:
            scheme_repo.link_session_to_user(payload.session_id, str(user.id))
        except Exception:
            pass

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


@router.post("/auth/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    """Generate a password reset token for a citizen account."""
    user = user_repo.get_by_email(payload.email)
    if not user:
        # Return standard response for security, but allow testing
        return {
            "status": "ok",
            "message": "If an account exists with this email, password reset instructions have been sent.",
            "reset_token": None,
        }

    reset_token = create_password_reset_token(user.email)
    return {
        "status": "ok",
        "message": "Password reset instructions have been generated.",
        "reset_token": reset_token,
    }


@router.post("/auth/reset-password")
def reset_password(payload: ResetPasswordRequest):
    """Consume a valid password reset token and update user password."""
    email = decode_password_reset_token(payload.token)
    success = user_repo.reset_password(email, payload.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to reset password. User may no longer exist.",
        )

    # Invalidate token so it cannot be re-used
    revoke_token(payload.token)
    return {
        "status": "ok",
        "message": "Password has been successfully reset. Please log in with your new password.",
    }


@router.post("/auth/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """Change password for an authenticated citizen or admin user."""
    ok, msg = user_repo.change_password(
        user_id=current_user.id,
        old_password=payload.old_password,
        new_password=payload.new_password,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/auth/logout")
def logout_citizen(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
):
    """Log out citizen and revoke their active JWT token."""
    revoke_token(credentials.credentials)
    return {"status": "ok", "message": "Successfully logged out. Access token has been revoked."}


# -------------------------------------------------------------
# Citizen Profile Management
# -------------------------------------------------------------
@router.get("/profile", response_model=CustomerProfileResponse)
def get_citizen_profile(current_user: UserModel = Depends(get_current_user)):
    """Retrieve profile and eligibility preferences of currently logged-in citizen."""
    return CustomerProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        state=getattr(current_user, "state", "All India"),
        age=getattr(current_user, "age", None),
        gender=getattr(current_user, "gender", "All"),
        annual_income=getattr(current_user, "annual_income", None),
        category=getattr(current_user, "category", "All"),
        occupation=getattr(current_user, "occupation", None),
        is_active=current_user.is_active,
        created_at=getattr(current_user, "created_at", None),
    )


@router.put("/profile", response_model=CustomerProfileResponse)
def update_citizen_profile(
    payload: CustomerProfileUpdateRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """Update citizen profile preferences."""
    updated = user_repo.update_profile(current_user.id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found for update")

    return CustomerProfileResponse(
        id=updated.id,
        email=updated.email,
        full_name=updated.full_name,
        role=updated.role,
        state=getattr(updated, "state", "All India"),
        age=getattr(updated, "age", None),
        gender=getattr(updated, "gender", "All"),
        annual_income=getattr(updated, "annual_income", None),
        category=getattr(updated, "category", "All"),
        occupation=getattr(updated, "occupation", None),
        is_active=updated.is_active,
        created_at=getattr(updated, "created_at", None),
    )


# -------------------------------------------------------------
# Saved Schemes (Bookmarks)
# -------------------------------------------------------------
@router.get("/saved-schemes")
def get_saved_schemes(current_user: UserModel = Depends(get_current_user)):
    """Get all schemes bookmarked by the citizen."""
    return scheme_repo.get_saved_schemes(current_user.id)


@router.post("/saved-schemes/{scheme_id}")
def save_scheme(scheme_id: str, current_user: UserModel = Depends(get_current_user)):
    """Bookmark a scheme for future tracking."""
    scheme_repo.save_scheme_for_user(current_user.id, scheme_id)
    return {"status": "ok", "message": "Scheme saved to your profile"}


@router.delete("/saved-schemes/{scheme_id}")
def remove_saved_scheme(scheme_id: str, current_user: UserModel = Depends(get_current_user)):
    """Remove a scheme from saved bookmarks."""
    scheme_repo.remove_saved_scheme(current_user.id, scheme_id)
    return {"status": "ok", "message": "Scheme removed from saved list"}


# -------------------------------------------------------------
# Scheme Tracker (Self-Reported Progress)
# -------------------------------------------------------------
@router.get("/applications")
def get_user_applications(current_user: UserModel = Depends(get_current_user)):
    """Retrieve all self-reported application statuses."""
    return scheme_repo.get_applications(current_user.id)


@router.post("/applications/{scheme_id}")
def update_application_status(
    scheme_id: str,
    payload: ApplicationStatusUpdateRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """
    Update self-reported application state:
    not_started -> applying -> submitted -> approved -> rejected -> need_help
    """
    scheme_repo.update_application_status(
        user_id=current_user.id,
        scheme_id=scheme_id,
        status=payload.status,
        notes=payload.notes,
    )
    return {"status": "ok", "message": f"Application status updated to '{payload.status}'"}


# -------------------------------------------------------------
# DPDP Consent & Data Deletion
# -------------------------------------------------------------
@router.delete("/me/delete-data")
def delete_citizen_data(current_user: UserModel = Depends(get_current_user)):
    """Single-tap DPDP Act compliance data deletion."""
    user_repo.delete_user(current_user.id)
    return {"status": "ok", "message": "All your profile data and saved matches have been permanently deleted."}
