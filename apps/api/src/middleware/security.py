import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from src.config.settings import get_settings
from src.models.user import UserModel
from src.repositories.alloydb import get_engine

security_scheme = HTTPBearer(auto_error=True)

# -------------------------------------------------------------
# Password Hashing Utilities (PBKDF2-HMAC-SHA256)
# -------------------------------------------------------------
ITERATIONS = 100_000
SALT_SIZE = 16


def hash_password(password: str) -> str:
    """Generate a secure salted PBKDF2-HMAC-SHA256 password hash."""
    salt = secrets.token_bytes(SALT_SIZE)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored salted hash."""
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        stored_key = bytes.fromhex(parts[3])
        new_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(stored_key, new_key)
    except Exception:
        return False


# -------------------------------------------------------------
# JWT Token Utilities
# -------------------------------------------------------------
def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT access token."""
    settings = get_settings()
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    
    to_encode.update({
        "exp": expire,
        "iat": now,
    })
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT access token."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# -------------------------------------------------------------
# Admin RBAC Dependency
# -------------------------------------------------------------
def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> UserModel:
    """FastAPI dependency that authenticates the user and verifies admin role."""
    token = credentials.credentials
    payload = decode_access_token(token)
    
    email: Optional[str] = payload.get("sub")
    role: Optional[str] = payload.get("role")
    
    if not email or role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to access this resource.",
        )
    
    # Query database to confirm active status
    try:
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        with Session(engine) as session:
            user = session.query(UserModel).filter(UserModel.email == email.lower().strip()).first()
            if not user:
                # If default admin, seed and return
                settings = get_settings()
                if email.lower().strip() == settings.default_admin_email.lower().strip():
                    user = UserModel(
                        email=settings.default_admin_email.lower().strip(),
                        hashed_password=hash_password(settings.default_admin_password),
                        full_name=settings.default_admin_name,
                        role="admin",
                        is_active=True,
                    )
                    session.add(user)
                    session.commit()
                    session.refresh(user)
                    return user

                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Admin user no longer exists.",
                )
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin account has been disabled.",
                )
            if user.role != "admin":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User does not possess administrative privileges.",
                )
            return user
    except HTTPException:
        raise
    except Exception as e:
        # Fallback for transient DB issue if payload is valid
        return UserModel(
            id=payload.get("user_id", 1),
            email=email,
            full_name=payload.get("name", "Admin"),
            role="admin",
            is_active=True
        )

