from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.models.user import (
    UserModel,
    CustomerRegisterRequest,
    CustomerLoginRequest,
    CustomerProfileResponse,
    CustomerProfileUpdateRequest,
    TokenResponse,
)
from src.middleware.security import create_access_token, get_current_user
from src.repositories.user_repository import UserRepository
from src.repositories.scheme_repository import SchemeRepository

router = APIRouter(prefix="/api/user", tags=["user"])

user_repo = UserRepository()
scheme_repo = SchemeRepository()


# -------------------------------------------------------------
# Citizen Authentication Routes
# -------------------------------------------------------------
@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_citizen(payload: CustomerRegisterRequest):
    """Register a new citizen/customer account with profile preferences."""
    user, error = user_repo.register_customer(payload)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
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
    """Update citizen profile preferences (State, Age, Income, Category, Occupation)."""
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
# Personalized Recommendations based on Citizen Profile
# -------------------------------------------------------------
@router.get("/recommended-schemes")
def get_recommended_schemes_for_citizen(current_user: UserModel = Depends(get_current_user)):
    """Fetch schemes matching the citizen's saved profile attributes in AlloyDB."""
    state = getattr(current_user, "state", None)
    age = getattr(current_user, "age", None)
    gender = getattr(current_user, "gender", None)
    category = getattr(current_user, "category", None)

    schemes, total = scheme_repo.get_schemes(
        state=state if state and state != "All India" else None,
        age=age,
        gender=gender if gender and gender != "All" else None,
        category=category if category and category != "All" else None,
        limit=20,
    )

    return {
        "citizen_profile": {
            "name": current_user.full_name,
            "state": state,
            "age": age,
            "category": category,
            "gender": gender,
        },
        "total_matched": total,
        "schemes": schemes,
    }
