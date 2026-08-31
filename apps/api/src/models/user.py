from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, Integer, String, Boolean, DateTime

from src.models.scheme import Base


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), default="customer", nullable=False, index=True)  # 'admin' or 'customer'
    
    # Citizen profile attributes
    state = Column(String(100), default="All India")
    age = Column(Integer, nullable=True)
    gender = Column(String(20), nullable=True)          # 'Male', 'Female', 'All'
    annual_income = Column(Integer, nullable=True)       # In INR
    category = Column(String(100), nullable=True)        # 'Education', 'Health', etc.
    occupation = Column(String(100), nullable=True)      # 'Student', 'Farmer', etc.

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# Pydantic Schemas for Auth & Users
class AdminLoginRequest(BaseModel):
    email: str
    password: str


class CustomerLoginRequest(BaseModel):
    email: str
    password: str


class CustomerRegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    state: Optional[str] = "All India"
    age: Optional[int] = None
    gender: Optional[str] = "All"
    annual_income: Optional[int] = None
    category: Optional[str] = "All"
    occupation: Optional[str] = None


class CustomerProfileResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    state: Optional[str] = "All India"
    age: Optional[int] = None
    gender: Optional[str] = "All"
    annual_income: Optional[int] = None
    category: Optional[str] = "All"
    occupation: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustomerProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    state: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    annual_income: Optional[int] = None
    category: Optional[str] = None
    occupation: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: int
    full_name: str
    email: str


class AdminUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
