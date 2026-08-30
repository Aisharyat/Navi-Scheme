from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SchemeModel(Base):
    __tablename__ = "schemes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    short_description = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    ministry = Column(String(255), nullable=True)
    state = Column(String(100), nullable=False, default="All India", index=True)  # "All India" or specific state
    country = Column(String(100), nullable=False, default="India")
    category = Column(String(100), nullable=False, index=True)  # Education, Healthcare, Agriculture, Housing, Pension, etc.
    target_gender = Column(String(50), nullable=False, default="All")  # All, Female, Male, Transgender
    min_age = Column(Integer, nullable=True)
    max_age = Column(Integer, nullable=True)
    income_limit = Column(Integer, nullable=True)  # Annual in INR, None if no limit
    benefits = Column(Text, nullable=False)
    eligibility_summary = Column(Text, nullable=False)
    documents_required = Column(Text, nullable=True)
    application_url = Column(String(500), nullable=True)
    application_process = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# Pydantic Schemas for API
class SchemeBase(BaseModel):
    slug: str
    title: str
    short_description: str
    description: Optional[str] = None
    ministry: Optional[str] = None
    state: str = "All India"
    country: str = "India"
    category: str
    target_gender: str = "All"
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    income_limit: Optional[int] = None
    benefits: str
    eligibility_summary: str
    documents_required: Optional[str] = None
    application_url: Optional[str] = None
    application_process: Optional[str] = None
    is_active: bool = True


class SchemeResponse(SchemeBase):
    id: int
    match_score: Optional[float] = None
    match_reasons: Optional[List[str]] = None

    class Config:
        from_attributes = True


class SchemeFilterRequest(BaseModel):
    query: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    age: Optional[int] = None
    gender: Optional[str] = None
    category: Optional[str] = None
    limit: int = 20
    offset: int = 0


class ChatMessageRequest(BaseModel):
    message: str
    state: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    category: Optional[str] = None


# Admin Management Schemas
class SchemeCreateRequest(BaseModel):
    slug: Optional[str] = None
    title: str
    short_description: str
    description: Optional[str] = None
    ministry: Optional[str] = None
    state: str = "All India"
    country: str = "India"
    category: str
    target_gender: str = "All"
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    income_limit: Optional[int] = None
    benefits: str
    eligibility_summary: str
    documents_required: Optional[str] = None
    application_url: Optional[str] = None
    application_process: Optional[str] = None
    is_active: bool = True


class SchemeUpdateRequest(BaseModel):
    slug: Optional[str] = None
    title: Optional[str] = None
    short_description: Optional[str] = None
    description: Optional[str] = None
    ministry: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    category: Optional[str] = None
    target_gender: Optional[str] = None
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    income_limit: Optional[int] = None
    benefits: Optional[str] = None
    eligibility_summary: Optional[str] = None
    documents_required: Optional[str] = None
    application_url: Optional[str] = None
    application_process: Optional[str] = None
    is_active: Optional[bool] = None


class AdminStatsResponse(BaseModel):
    total_schemes: int
    active_schemes: int
    inactive_schemes: int
    total_categories: int
    total_states: int
    categories: List[str]
    states: List[str]


class AdminSchemeListResponse(BaseModel):
    total: int
    schemes: List[SchemeResponse]

