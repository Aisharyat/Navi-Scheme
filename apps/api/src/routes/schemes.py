from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel

from src.models.scheme import SchemeFilterRequest, ChatMessageRequest
from src.models.user import UserModel
from src.middleware.security import get_optional_current_user
from src.repositories.scheme_repository import SchemeRepository
from src.services.ai_service import GroundedAIService

router = APIRouter(prefix="/api", tags=["schemes"])
repository = SchemeRepository()
ai_service = GroundedAIService()


class ChatResponse(BaseModel):
    reply: str
    extracted_state: Optional[str] = None
    extracted_age: Optional[int] = None
    extracted_category: Optional[str] = None
    extracted_caste: Optional[str] = None
    schemes: List[Dict[str, Any]] = []
    total_found: int = 0
    suggestions: List[str] = []


@router.get("/taxonomies")
def get_taxonomies():
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
            "Haryana"
        ],
        "categories": [
            "Education",
            "Health",
            "Housing",
            "Pension",
            "Agriculture",
            "Women & Child",
            "Social Welfare"
        ],
        "age_groups": [
            {"label": "0 - 10 yrs (Girl child / Child)", "value": 8},
            {"label": "18 - 35 yrs (Youth / Higher Education)", "value": 22},
            {"label": "18 - 60 yrs (Working / Family / Housing)", "value": 35},
            {"label": "60+ yrs (Senior Citizens)", "value": 65}
        ]
    }


@router.get("/schemes")
def list_schemes(
    q: Optional[str] = Query(None, description="Search query"),
    state: Optional[str] = Query(None, description="Filter by state (e.g. Maharashtra, UP) or All India"),
    country: Optional[str] = Query("India", description="Country"),
    age: Optional[int] = Query(None, description="Citizen age (e.g. 21)"),
    gender: Optional[str] = Query(None, description="Target gender (Female, Male, All)"),
    category: Optional[str] = Query(None, description="Category (Education, Health, etc.)"),
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
            "gender": gender
        },
        "schemes": schemes
    }


@router.post("/eligibility/match")
def match_schemes(req: SchemeFilterRequest):
    schemes, total = repository.get_schemes(
        query=req.query,
        state=req.state,
        country=req.country,
        age=req.age,
        gender=req.gender,
        category=req.category,
        limit=req.limit,
        offset=req.offset,
    )
    return {
        "total": total,
        "schemes": schemes
    }


@router.get("/schemes/{identifier}")
def get_scheme(identifier: str):
    scheme = repository.get_scheme_by_id_or_slug(identifier)
    if not scheme:
        return {"error": "Scheme not found", "status": 404}
    return scheme


@router.post("/schemes/{identifier}/explain")
def explain_scheme(identifier: str):
    scheme = repository.get_scheme_by_id_or_slug(identifier)
    if not scheme:
        return {"error": "Scheme not found", "status": 404}
    
    explanation = {
        "scheme": scheme,
        "title": scheme["title"],
        "headline": f"Official summary of {scheme['title']} under {scheme.get('ministry') or 'Government of India'}.",
        "key_benefits": scheme["benefits"],
        "eligibility_rules": scheme["eligibility_summary"],
        "required_documents": scheme.get("documents_required") or "Aadhaar Card, Bank Passbook, Identity & Address Proof",
        "application_steps": scheme.get("application_process") or "Visit official portal or nearest CSC centre to apply.",
        "official_url": scheme.get("application_url"),
    }
    return explanation


@router.post("/chat", response_model=ChatResponse)
def handle_chat_message(
    req: ChatMessageRequest,
    current_user: Optional[UserModel] = Depends(get_optional_current_user)
):
    msg_lower = req.message.lower().strip()

    # 1. Check if user is asking for explanation of a specific scheme
    for seed in repository.get_schemes(limit=50)[0]:
        if seed["slug"] in msg_lower or seed["title"].lower() in msg_lower:
            detailed = repository.get_scheme_by_id_or_slug(seed["slug"])
            if detailed:
                reply = f"Here are the complete details and official application guide for **{detailed['title']}**:"
                return ChatResponse(
                    reply=reply,
                    extracted_state=detailed["state"],
                    extracted_category=detailed["category"],
                    schemes=[detailed],
                    total_found=1,
                    suggestions=[
                        "🎯 Find schemes for my age",
                        "ℹ️ Ask about another scheme",
                        "📝 How to apply online"
                    ]
                )

    # 2. Extract structured entities (State, Age, Gender, Category, Caste) via Grounded NLP extractor
    extracted = ai_service.extract_intent_and_caste(req.message)

    # 3. Dynamic Profile Resolution (eliminating stale / hardcoded fallbacks):
    # - Priority 1: Explicit entity extracted from message text (e.g. "I am 60 yrs old")
    # - Priority 2: Explicit request payload parameter passed by client
    # - Priority 3: Live authenticated database profile of current_user
    # - Priority 4: None (no arbitrary hardcoded default)
    user_state = current_user.state if current_user else None
    user_age = current_user.age if current_user else None
    user_gender = current_user.gender if current_user else None
    user_category = current_user.category if current_user else None
    user_income = current_user.annual_income if current_user else None

    state = extracted.get("state") or req.state or user_state
    age = extracted.get("age") if extracted.get("age") is not None else (req.age if req.age is not None else user_age)
    gender = extracted.get("gender") if (extracted.get("gender") and extracted.get("gender") != "All") else (req.gender or user_gender or "All")
    category = extracted.get("category") or req.category or user_category
    caste = extracted.get("caste") or req.caste or (user_category if user_category in ["SC", "ST", "OBC", "EWS", "General", "Minority"] else None)
    income = req.annual_income or user_income

    # Update extracted dict for AI prompt context
    extracted["state"] = state
    extracted["age"] = age
    extracted["gender"] = gender
    extracted["category"] = category
    extracted["caste"] = caste
    extracted["income"] = income

    # 4. Query AlloyDB for matching verified schemes with strict eligibility checking
    subject = extracted.get("subject")
    keywords = extracted.get("keywords") or []

    # If user searched for a specific topic (e.g. "marriage", "inter-caste", "solar", "pension"), prioritize querying those keywords
    primary_query = None
    if "inter-caste" in keywords:
        primary_query = "inter-caste"
    elif "marriage" in keywords or subject == "marriage":
        primary_query = "marriage"
    elif keywords:
        primary_query = keywords[0]
    elif subject:
        primary_query = subject

    schemes, total = repository.get_schemes(
        query=primary_query,
        state=state if state and state != "All India" else None,
        age=age,
        gender=gender if gender != "All" else None,
        category=category if category != "All" else None,
        income=income,
        limit=5,
    )

    # If 0 matches in that specific state, search across All India / National level for that subject
    if total == 0 and (primary_query or caste):
        schemes, total = repository.get_schemes(
            query=primary_query or caste,
            age=age,
            gender=gender if gender != "All" else None,
            income=income,
            limit=5,
        )

    # If still 0 matches and no specific subject was requested, try general category query
    if total == 0 and not primary_query and category and category != "All":
        schemes, total = repository.get_schemes(
            category=category,
            state=state if state and state != "All India" else None,
            age=age,
            gender=gender if gender != "All" else None,
            income=income,
            limit=5,
        )

    # 5. Generate grounded, factual anti-hallucination response
    reply = ai_service.generate_grounded_response(
        query=req.message,
        extracted=extracted,
        schemes=schemes,
        total_found=total,
    )

    # 6. Smart contextual suggestions
    suggestions = []
    if caste:
        suggestions.append(f"🎓 {caste} Scholarships")
        suggestions.append(f"📝 {caste} Certificate docs")
    if not state:
        suggestions.append("State: Maharashtra")
        suggestions.append("State: Karnataka")
    if age is None:
        suggestions.append("Age: 18-35 yrs")
        suggestions.append("Age: 60+ (Senior)")
    if not category:
        suggestions.append("Education & Scholarships")
        suggestions.append("Health insurance (Ayushman)")

    return ChatResponse(
        reply=reply,
        extracted_state=state,
        extracted_age=age,
        extracted_category=category,
        extracted_caste=caste,
        schemes=schemes,
        total_found=total,
        suggestions=suggestions[:4]
    )


