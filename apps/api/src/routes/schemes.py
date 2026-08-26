from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.models.scheme import SchemeFilterRequest, ChatMessageRequest
from src.repositories.scheme_repository import SchemeRepository

router = APIRouter(prefix="/api", tags=["schemes"])
repository = SchemeRepository()


class ChatResponse(BaseModel):
    reply: str
    extracted_state: Optional[str] = None
    extracted_age: Optional[int] = None
    extracted_category: Optional[str] = None
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
def handle_chat_message(req: ChatMessageRequest):
    msg_lower = req.message.lower().strip()

    # Check if user is asking for explanation of a specific scheme
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

    extracted = repository.extract_intent(req.message)

    # Use explicit payload values or fall back to extracted intent
    state = req.state or extracted["state"]
    age = req.age if req.age is not None else extracted["age"]
    gender = req.gender or extracted["gender"]
    category = req.category or extracted["category"]

    schemes, total = repository.get_schemes(
        query=req.message if not (state or age or category) else None,
        state=state,
        age=age,
        gender=gender,
        category=category,
        limit=5,
    )

    # Construct smart conversational reply based on findings
    criteria_parts = []
    if category:
        criteria_parts.append(f"category: {category}")
    if state:
        criteria_parts.append(f"state: {state}")
    if age is not None:
        criteria_parts.append(f"age: {age} years")

    criteria_str = f" for {', '.join(criteria_parts)}" if criteria_parts else ""

    if total > 0:
        reply = f"Based on your profile{criteria_str}, here are {len(schemes)} recommended welfare schemes:"
    else:
        reply = f"I couldn't find specific schemes directly matching{criteria_str}. Try selecting a different state or age bracket."

    suggestions = []
    if not state:
        suggestions.append("State: Maharashtra")
        suggestions.append("State: Karnataka")
    if age is None:
        suggestions.append("Age: 18-35 yrs")
        suggestions.append("Age: 60+ (Senior)")
    if not category:
        suggestions.append("Education")
        suggestions.append("Health insurance")
        suggestions.append("Housing schemes")

    return ChatResponse(
        reply=reply,
        extracted_state=state,
        extracted_age=age,
        extracted_category=category,
        schemes=schemes,
        total_found=total,
        suggestions=suggestions[:4]
    )

