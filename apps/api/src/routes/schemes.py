from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, Depends, HTTPException, Body
from pydantic import BaseModel, Field

from src.models.user import UserModel
from src.middleware.security import get_optional_current_user
from src.repositories.scheme_repository import SchemeRepository
from src.services.ai_service import GroundedAIService

router = APIRouter(prefix="/api", tags=["schemes"])
repository = SchemeRepository()
ai_service = GroundedAIService()


class ProfileMatchRequest(BaseModel):
    state: Optional[str] = None
    district: Optional[str] = None
    pincode: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = "prefer_not_to_say"
    occupation: Optional[str] = None
    income_bracket: Optional[str] = "prefer_not_to_say"
    social_category: Optional[str] = "prefer_not_to_say"
    disability_status: Optional[bool] = None
    marital_status: Optional[str] = "prefer_not_to_say"
    land_owned_hectares: Optional[float] = None
    education_level: Optional[str] = None
    has_ration_card: Optional[bool] = None
    has_aadhaar_linked_bank: Optional[bool] = None
    dependents: Optional[int] = None
    is_proxy_profile: bool = False
    language: str = "en"
    sensitive_fields_consented: bool = False


class ExplainRequest(BaseModel):
    matched_criteria: Optional[List[Dict[str, Any]]] = []
    language: str = "en"


class ChatMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    state: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    category: Optional[str] = None
    caste: Optional[str] = None
    annual_income: Optional[float] = None
    language: str = "en"


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    extracted_state: Optional[str] = None
    extracted_age: Optional[int] = None
    extracted_category: Optional[str] = None
    extracted_caste: Optional[str] = None
    schemes: List[Dict[str, Any]] = []
    total_found: int = 0
    action_taken: str = "matched"
    suggestions: List[str] = []
    messages_used: int = 1
    free_messages_limit: int = 5
    requires_auth: bool = False


class FeedbackRequest(BaseModel):
    scheme_id: Optional[str] = None
    type: str = Field(..., description="match_feedback | report_issue | outcome")
    content: str


@router.get("/taxonomies")
def get_taxonomies():
    """Get standardized taxonomies for Indian welfare schemes."""
    return {
        "states": [
            "All India",
            "Maharashtra",
            "Uttar Pradesh",
            "Madhya Pradesh",
            "Karnataka",
            "Bihar",
            "Tamil Nadu",
            "Rajasthan",
            "Gujarat",
            "West Bengal",
            "Delhi",
            "Kerala",
            "Punjab",
            "Haryana",
            "Andhra Pradesh",
            "Telangana",
            "Odisha",
            "Assam"
        ],
        "sectors": [
            "agriculture",
            "education",
            "health",
            "housing",
            "pension",
            "women",
            "business",
            "social_welfare",
            "employment",
            "disability"
        ],
        "categories": [
            "Agriculture",
            "Education",
            "Health",
            "Housing",
            "Pension",
            "Women & Child",
            "Social Welfare"
        ],
        "occupations": [
            {"id": "farmer", "label": "Farmer / Agriculture (किसान)"},
            {"id": "student", "label": "Student / Scholar (छात्र/छात्रा)"},
            {"id": "salaried", "label": "Salaried / Employed (वेतनभोगी)"},
            {"id": "self_employed", "label": "Self-Employed / Business / Trader (व्यवसायी)"},
            {"id": "daily_wage_informal", "label": "Daily Wage / Informal Worker (दैनिक मजदूर)"},
            {"id": "homemaker", "label": "Homemaker / Housewife (गृहणी)"},
            {"id": "retired", "label": "Retired / Senior Citizen (वरिष्ठ नागरिक)"},
            {"id": "unemployed", "label": "Unemployed / Job Seeker (बेरोजगार)"}
        ],
        "income_brackets": [
            {"id": "below_1l", "label": "Below ₹1,00,000 / year (BPL / Antyodaya)"},
            {"id": "1l_3l", "label": "₹1,00,000 - ₹3,00,000 / year (Low Income Group)"},
            {"id": "3l_6l", "label": "₹3,00,000 - ₹6,00,000 / year (Middle Income Group I)"},
            {"id": "6l_10l", "label": "₹6,00,000 - ₹10,00,000 / year (Middle Income Group II)"},
            {"id": "above_10l", "label": "Above ₹10,00,000 / year"}
        ],
        "social_categories": [
            {"id": "general", "label": "General / Open"},
            {"id": "obc", "label": "OBC (Other Backward Class)"},
            {"id": "sc", "label": "SC (Scheduled Caste)"},
            {"id": "st", "label": "ST (Scheduled Tribe)"},
            {"id": "ews", "label": "EWS (Economically Weaker Section)"},
            {"id": "prefer_not_to_say", "label": "Prefer not to say"}
        ]
    }


@router.get("/schemes")
def list_schemes(
    q: Optional[str] = Query(None, description="Search query"),
    state: Optional[str] = Query(None, description="Filter by state or All India"),
    country: Optional[str] = Query("India", description="Country"),
    age: Optional[int] = Query(None, description="Citizen age"),
    gender: Optional[str] = Query(None, description="Target gender"),
    category: Optional[str] = Query(None, description="Category"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    schemes, total = repository.get_schemes(
        query=q,
        state=state,
        country=country,
        age=age,
        gender=gender,
        category=category,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "filter": {
            "query": q,
            "state": state,
            "age": age,
            "category": category,
            "gender": gender,
        },
        "schemes": schemes
    }


@router.get("/schemes/{identifier}")
def get_scheme(identifier: str):
    scheme = repository.get_scheme_by_id_or_slug(identifier)
    if not scheme:
        raise HTTPException(status_code=404, detail="SCHEME_NOT_FOUND")
    return scheme


@router.post("/eligibility/match")
def match_eligibility(
    req: ProfileMatchRequest,
    current_user: Optional[UserModel] = Depends(get_optional_current_user)
):
    """
    Pure deterministic matching engine endpoint (§4 & §6.3 of engineering spec).
    Strips unconsented sensitive fields silently server-side per DPDP privacy rules.
    """
    profile_dict = req.model_dump()

    # Privacy enforcement: Strip sensitive fields if not explicitly consented
    if not req.sensitive_fields_consented:
        profile_dict["social_category"] = "prefer_not_to_say"
        profile_dict["disability_status"] = None
        profile_dict["income_bracket"] = "prefer_not_to_say"

    result = repository.match_citizen_profile(profile_dict)
    return result


@router.post("/schemes/{identifier}/explain")
def explain_scheme(
    identifier: str,
    req: ExplainRequest = Body(default=ExplainRequest()),
):
    """
    Grounded AI explanation endpoint (§5 of engineering spec).
    Constrained to DB facts with post-guardrail checks and fallback.
    """
    scheme = repository.get_scheme_by_id_or_slug(identifier)
    if not scheme:
        raise HTTPException(status_code=404, detail="SCHEME_NOT_FOUND")

    explanation = ai_service.explain_scheme(
        scheme_facts=scheme,
        matched_criteria=req.matched_criteria or [],
        confidence="high",
        language=req.language or "en",
    )
    return explanation


@router.post("/chat", response_model=ChatResponse)
def handle_chat_message(
    req: ChatMessageRequest,
    current_user: Optional[UserModel] = Depends(get_optional_current_user)
):
    """
    Conversational AI guide with session profile persistence, 5-message guest limit,
    state clarification gate, and grounded catalog responses.
    """
    import uuid
    session_id = req.session_id or f"sess_{uuid.uuid4().hex[:12]}"
    user_id = current_user.id if current_user else None

    # Note: Message rate limits commented out for now as per task requirements
    # if not current_user:
    #     user_msg_count = repository.count_session_user_messages(session_id)
    #     if user_msg_count >= 5:
    #         return ChatResponse(
    #             session_id=session_id,
    #             reply=(
    #                 "🔒 **You have reached your 5 free messages limit.**\n\n"
    #                 "Please sign in or create a free citizen profile to enjoy **unlimited free chat** "
    #                 "with personalized scheme matching. All your prior conversation data will be saved!"
    #             ),
    #             schemes=[],
    #             total_found=0,
    #             action_taken="auth_required",
    #             suggestions=["Sign In Free", "Create Account"],
    #             messages_used=user_msg_count,
    #             free_messages_limit=5,
    #             requires_auth=True,
    #         )

    # Process conversational turn through AI reasoning pipeline
    result = ai_service.process_conversational_turn(
        session_id=session_id,
        message=req.message,
        repository=repository,
        user_id=user_id,
        language=req.language,
    )

    current_count = repository.count_session_user_messages(session_id)

    return ChatResponse(
        session_id=session_id,
        reply=result["reply"],
        extracted_state=result.get("extracted_state"),
        extracted_age=result.get("extracted_age"),
        extracted_category=result.get("extracted_category"),
        extracted_caste=result.get("extracted_caste"),
        schemes=result.get("schemes", []),
        total_found=result.get("total_found", 0),
        action_taken=result.get("action_taken", "matched"),
        suggestions=result.get("suggestions", []),
        messages_used=current_count,
        free_messages_limit=999999,
        requires_auth=False,
    )


@router.get("/chat/history/{session_id}")
def get_chat_history(
    session_id: str,
    current_user: Optional[UserModel] = Depends(get_optional_current_user)
):
    """Retrieve chat session history and accumulated profile."""
    profile = repository.get_session_profile(session_id)
    raw_messages = repository.get_session_messages(session_id, limit=60)
    user_msg_count = repository.count_session_user_messages(session_id)

    # Normalize messages to have both role/sender and content/message
    normalized_messages = []
    for m in raw_messages:
        sender = m.get("sender") or m.get("role") or "assistant"
        role = "user" if sender == "user" else "assistant"
        content = m.get("message") or m.get("content") or ""
        if content.strip():
            normalized_messages.append({
                "id": m.get("id"),
                "session_id": m.get("session_id"),
                "sender": sender,
                "role": role,
                "message": content,
                "content": content,
                "action_taken": m.get("action_taken"),
                "created_at": m.get("created_at"),
            })

    return {
        "session_id": session_id,
        "profile": profile,
        "messages": normalized_messages,
        "messages_used": user_msg_count,
        "free_messages_limit": 999999,
        "is_authenticated": current_user is not None,
    }


@router.post("/feedback")
def submit_feedback(
    req: FeedbackRequest,
    current_user: Optional[UserModel] = Depends(get_optional_current_user)
):
    """Submit citizen feedback on scheme matches or report inaccuracies."""
    user_id = current_user.id if current_user else None
    repository.record_feedback(
        user_id=user_id,
        scheme_id=req.scheme_id,
        feedback_type=req.type,
        content=req.content,
    )
    return {"status": "ok", "message": "Feedback recorded. Thank you for keeping Navi Scheme accurate!"}
