from typing import Optional, List, Dict, Any, Literal
from fastapi import APIRouter, Query, Depends, HTTPException, Body
from pydantic import BaseModel, Field

from src.config.settings import get_settings
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
    userProfile: Optional[Dict[str, Any]] = None
    history: Optional[List[Dict[str, Any]]] = None
    language: str = "en"


class LoanCalculationRequest(BaseModel):
    amount: float = Field(..., description="Project/Loan amount in Rupees")
    schemeType: Optional[str] = "PMEGP"
    category: Optional[str] = "General"
    area: Optional[str] = "Urban"


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    extracted_state: Optional[str] = None
    extracted_age: Optional[int] = None
    extracted_category: Optional[str] = None
    extracted_caste: Optional[str] = None
    schemes: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    total_found: int = 0
    action_taken: str = "matched"
    suggestions: List[str] = []
    quickReplies: List[str] = []
    userProfile: Dict[str, Any] = {}
    messages_used: int = 1
    free_messages_limit: int = 5
    requires_auth: bool = False


class FeedbackRequest(BaseModel):
    scheme_id: Optional[str] = None
    type: Literal["match_feedback", "report_issue", "outcome"] = Field(
        ..., description="match_feedback | report_issue | outcome"
    )
    content: str


@router.get("/taxonomies")
@router.get("/meta")
def get_taxonomies():
    """Get standardized taxonomies and metadata for Indian welfare schemes."""
    _, total = repository.get_schemes(limit=1)
    return {
        "totalSchemes": total,
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
    query: Optional[str] = Query(None, description="Search query alias"),
    state: Optional[str] = Query(None, description="Filter by state or All India"),
    country: Optional[str] = Query("India", description="Country"),
    age: Optional[int] = Query(None, description="Citizen age"),
    gender: Optional[str] = Query(None, description="Target gender"),
    category: Optional[str] = Query(None, description="Category"),
    level: Optional[str] = Query(None, description="Level filter"),
    page: Optional[int] = Query(None, description="Page number 1-indexed"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    effective_query = query if query is not None else q
    if page is not None and page >= 1:
        offset = (page - 1) * limit

    schemes, total = repository.get_schemes(
        query=effective_query,
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
        "page": page or (offset // limit + 1),
        "limit": limit,
        "offset": offset,
        "filter": {
            "query": effective_query,
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
@router.post("/schemes/match")
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
    
    # Ensure backward and forward compatibility with frontend
    enriched_matches = []
    for m in result.get("matches", []):
        sch = m.get("scheme")
        if not sch:
            sch_id = m.get("scheme_id")
            sch = repository.get_scheme_by_id_or_slug(sch_id) if sch_id else None
        
        m_copy = dict(m)
        if sch:
            m_copy["scheme"] = sch
        if "matchPercentage" not in m_copy:
            m_copy["matchPercentage"] = int(m_copy.get("score", 85))
        enriched_matches.append(m_copy)

    result["matches"] = enriched_matches
    result["totalMatches"] = result.get("total_matches", len(enriched_matches))
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
    settings = get_settings()
    guest_limit = settings.guest_chat_limit

    # Enforce real rate limit for unauthenticated guest sessions
    if not current_user:
        user_msg_count = repository.count_session_user_messages(session_id)
        if user_msg_count >= guest_limit:
            return ChatResponse(
                session_id=session_id,
                reply=(
                    f"🔒 **You have reached your {guest_limit} free messages limit.**\n\n"
                    "Please sign in or create a free citizen profile to enjoy **unlimited free chat** "
                    "with personalized scheme matching. All your prior conversation data will be saved!"
                ),
                schemes=[],
                total_found=0,
                action_taken="auth_required",
                suggestions=["Sign In Free", "Create Account"],
                messages_used=user_msg_count,
                free_messages_limit=guest_limit,
                requires_auth=True,
            )

    # Sync profile from authenticated user, request fields, or userProfile dict
    profile_updates = {}
    if current_user:
        if current_user.state and current_user.state != "All India":
            profile_updates["state"] = current_user.state
        if current_user.age is not None:
            profile_updates["age"] = current_user.age
        if current_user.gender and current_user.gender != "All":
            profile_updates["gender"] = current_user.gender
        if current_user.category and current_user.category != "All":
            profile_updates["category"] = current_user.category
        if current_user.annual_income is not None:
            profile_updates["annual_income"] = current_user.annual_income
        if current_user.occupation:
            profile_updates["occupation"] = current_user.occupation

    # Also extract from userProfile dict if passed by client
    if req.userProfile and isinstance(req.userProfile, dict):
        for k, v in req.userProfile.items():
            if v is not None and v != "" and v != "All" and v != "All India":
                profile_updates[k] = v

    for field in ["state", "age", "gender", "category", "caste", "annual_income"]:
        val = getattr(req, field, None)
        if val is not None and val != "" and val != "All" and val != "All India":
            profile_updates[field] = val

    if profile_updates:
        repository.update_session_profile(session_id, profile_updates)

    # Process conversational turn through AI reasoning pipeline
    result = ai_service.process_conversational_turn(
        session_id=session_id,
        message=req.message,
        repository=repository,
        user_id=user_id,
        language=req.language,
    )

    current_count = repository.count_session_user_messages(session_id)
    free_limit = 999999 if current_user else guest_limit
    needs_auth = False if current_user else (current_count >= guest_limit)

    raw_schemes = result.get("schemes", [])
    sources_list = []
    for s in raw_schemes:
        is_exp = (s.get("status") in ["expired", "closed"]) or bool(s.get("isExpired"))
        sources_list.append({
            "id": s.get("id") or s.get("slug"),
            "slug": s.get("slug") or s.get("id"),
            "title": s.get("title") or s.get("name"),
            "level": s.get("issuing_level") or s.get("level") or "Central",
            "issuing_level": s.get("issuing_level") or s.get("level") or "Central",
            "state": s.get("state") or "All India",
            "deadline": s.get("deadline") or ("Expired" if is_exp else "Active & Open"),
            "isExpired": is_exp,
            "application_url": s.get("application_url"),
            "portalUrl": s.get("application_url") or s.get("portalUrl"),
            "description": s.get("description") or s.get("short_description"),
        })

    suggs = result.get("suggestions", [])
    user_prof = {
        "state": result.get("extracted_state") or profile_updates.get("state"),
        "age": result.get("extracted_age") or profile_updates.get("age"),
        "category": result.get("extracted_category") or profile_updates.get("category"),
        "caste": result.get("extracted_caste") or profile_updates.get("caste"),
        "gender": profile_updates.get("gender"),
        "occupation": profile_updates.get("occupation"),
    }
    user_prof = {k: v for k, v in user_prof.items() if v is not None}

    return ChatResponse(
        session_id=session_id,
        reply=result["reply"],
        extracted_state=result.get("extracted_state"),
        extracted_age=result.get("extracted_age"),
        extracted_category=result.get("extracted_category"),
        extracted_caste=result.get("extracted_caste"),
        schemes=raw_schemes,
        sources=sources_list,
        total_found=result.get("total_found", 0),
        action_taken=result.get("action_taken", "matched"),
        suggestions=suggs,
        quickReplies=suggs,
        userProfile=user_prof,
        messages_used=current_count,
        free_messages_limit=free_limit,
        requires_auth=needs_auth,
    )


@router.post("/calculate-loan")
def calculate_loan_endpoint(req: LoanCalculationRequest):
    """
    Government Loan & Subsidy Calculator endpoint (PMEGP, Mudra, Stand-Up India, etc.)
    """
    loan_amount = float(req.amount) if req.amount else 0.0
    if loan_amount <= 0:
        raise HTTPException(status_code=400, detail="Please provide a valid loan amount in Rupees.")

    scheme_type = (req.schemeType or "PMEGP").upper()
    category = (req.category or "General").upper()
    area = (req.area or "Urban").lower()

    is_special_category = any(
        c in category for c in ["SC", "ST", "OBC", "WOMEN", "WOMAN", "MINORITY", "EX-SERVICEMEN", "DIVYANG", "SPECIAL"]
    )
    is_rural = "rural" in area

    own_contribution_percent = 10
    subsidy_percent = 15
    interest_rate = 9.5
    tenure_years = 5

    if "PMEGP" in scheme_type:
        if is_special_category:
            own_contribution_percent = 5
            subsidy_percent = 35 if is_rural else 25
        else:
            own_contribution_percent = 10
            subsidy_percent = 25 if is_rural else 15
    elif "SHISHU" in scheme_type:
        own_contribution_percent = 0
        subsidy_percent = 0
        tenure_years = 3
        interest_rate = 8.5
    elif "KISHORE" in scheme_type or "TARUN" in scheme_type or "MUDRA" in scheme_type:
        own_contribution_percent = 10
        subsidy_percent = 0
        tenure_years = 5
        interest_rate = 9.5
    elif "STANDUP" in scheme_type or "STAND_UP" in scheme_type or "STAND-UP" in scheme_type:
        own_contribution_percent = 15
        subsidy_percent = 10
        tenure_years = 7
        interest_rate = 8.75
    else:
        if is_special_category:
            own_contribution_percent = 5
            subsidy_percent = 25
        else:
            own_contribution_percent = 10
            subsidy_percent = 15

    own_contribution = (loan_amount * own_contribution_percent) / 100.0
    govt_subsidy = (loan_amount * subsidy_percent) / 100.0
    net_bank_loan = max(0.0, loan_amount - own_contribution - govt_subsidy)

    monthly_rate = interest_rate / (12.0 * 100.0)
    total_months = tenure_years * 12
    if monthly_rate > 0 and total_months > 0:
        emi = (net_bank_loan * monthly_rate * ((1.0 + monthly_rate) ** total_months)) / (((1.0 + monthly_rate) ** total_months) - 1.0)
    else:
        emi = net_bank_loan / max(1, total_months)

    total_payment = emi * total_months
    total_interest = total_payment - net_bank_loan

    summary = (
        f"For a project cost of ₹{loan_amount:,.0f}, your own margin money contribution is ₹{round(own_contribution):,.0f} ({own_contribution_percent}%). "
        f"The government capital subsidy is ₹{round(govt_subsidy):,.0f} ({subsidy_percent}%). "
        f"The net bank loan is ₹{round(net_bank_loan):,.0f}, with an estimated monthly EMI of ₹{round(emi):,.0f} over {tenure_years} years at {interest_rate}% p.a."
    )

    return {
        "schemeType": req.schemeType,
        "projectCost": loan_amount,
        "category": req.category,
        "area": req.area,
        "ownContributionPercent": own_contribution_percent,
        "ownContributionAmount": round(own_contribution),
        "govtSubsidyPercent": subsidy_percent,
        "govtSubsidyAmount": round(govt_subsidy),
        "netBankLoanAmount": round(net_bank_loan),
        "estimatedInterestRate": interest_rate,
        "tenureYears": tenure_years,
        "monthlyEMI": round(emi),
        "totalInterestPayable": round(total_interest),
        "totalRepaymentToBank": round(total_payment),
        "summary": summary
    }


@router.post("/chat/{session_id}/reset")
@router.delete("/chat/{session_id}/profile")
def reset_chat_session_profile(session_id: str):
    """Reset all accumulated profile entities for a session (state, age, caste, category, etc.)."""
    repository.reset_session_profile(session_id)
    return {"status": "ok", "message": f"Session profile for '{session_id}' has been reset."}


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
