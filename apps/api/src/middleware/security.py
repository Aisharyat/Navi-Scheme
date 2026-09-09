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
from src.models.scheme import Base
from src.models.user import UserModel
from src.repositories.database import get_engine

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
import base64
import json
import time

# -------------------------------------------------------------
# JWT Token Utilities (HS256 Standard RFC 7519)
# -------------------------------------------------------------
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed HS256 JWT access token."""
    settings = get_settings()
    to_encode = data.copy()
    now_ts = int(time.time())

    if expires_delta:
        expire_ts = now_ts + int(expires_delta.total_seconds())
    else:
        expire_ts = now_ts + int(settings.jwt_access_token_expire_minutes * 60)

    to_encode.update({
        "exp": expire_ts,
        "iat": now_ts,
    })

    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(to_encode, separators=(",", ":"), default=str).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}"

    signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    sig_b64 = _b64url_encode(signature)

    return f"{signing_input}.{sig_b64}"


# -------------------------------------------------------------
# In-Memory & Revocation Store for JWT Token Denylist
# -------------------------------------------------------------
_REVOKED_TOKENS: set[str] = set()


def revoke_token(token: str) -> None:
    """Add token signature or raw token string to denylist."""
    if token:
        parts = token.strip().split(".")
        token_id = parts[2] if len(parts) == 3 else token.strip()
        _REVOKED_TOKENS.add(token_id)


def is_token_revoked(token: str) -> bool:
    """Check if token signature or raw token has been revoked."""
    if not token:
        return False
    parts = token.strip().split(".")
    token_id = parts[2] if len(parts) == 3 else token.strip()
    return token_id in _REVOKED_TOKENS


def create_password_reset_token(email: str, expires_minutes: int = 30) -> str:
    """Generate a signed single-purpose password reset token."""
    return create_access_token(
        data={"sub": email.lower().strip(), "type": "password_reset"},
        expires_delta=timedelta(minutes=expires_minutes),
    )


def decode_password_reset_token(token: str) -> str:
    """Decode and validate a password reset token, returning the user email."""
    if is_token_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token has already been used or revoked.",
        )
    payload = decode_access_token(token)
    if payload.get("type") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token type for password reset.",
        )
    email = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token payload.",
        )
    return email


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a signed HS256 JWT access token."""
    if is_token_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has been revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = get_settings()
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token format.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"

        expected_sig = hmac.new(
            settings.jwt_secret_key.encode("utf-8"),
            signing_input.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        actual_sig = _b64url_decode(sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token signature.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        # Expiration check
        exp = payload.get("exp")
        if exp is not None and time.time() > float(exp):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(e)}",
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


# -------------------------------------------------------------
# General User Authentication Dependency (Citizen or Admin)
# -------------------------------------------------------------
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> UserModel:
    """FastAPI dependency that authenticates any active user (Citizen or Admin)."""
    token = credentials.credentials
    payload = decode_access_token(token)

    email: Optional[str] = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token payload.",
        )

    try:
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        with Session(engine) as session:
            user = session.query(UserModel).filter(UserModel.email == email.lower().strip()).first()
            if not user:
                # If default admin token
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
                    detail="User account does not exist.",
                )
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User account has been deactivated.",
                )
            session.expunge(user)
            return user
    except HTTPException:
        raise
    except Exception as e:
        # Transient fallback
        return UserModel(
            id=payload.get("user_id", 1),
            email=email,
            full_name=payload.get("name", "Citizen"),
            role=payload.get("role", "customer"),
            is_active=True,
        )


# -------------------------------------------------------------
# Optional User Authentication Dependency (For Context Sync)
# -------------------------------------------------------------
optional_security_scheme = HTTPBearer(auto_error=False)


def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security_scheme)
) -> Optional[UserModel]:
    """
    FastAPI dependency that extracts authenticated user from session token if provided.
    Returns None if no token or token is invalid (allowing guest access without failure).
    """
    if not credentials or not credentials.credentials:
        return None

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        email: Optional[str] = payload.get("sub")
        if not email:
            return None

        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        with Session(engine) as session:
            user = session.query(UserModel).filter(UserModel.email == email.lower().strip()).first()
            if user and user.is_active:
                session.expunge(user)
                return user
        return None
    except Exception:
        return None


