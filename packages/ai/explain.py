import re
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

MANDATORY_DISCLAIMER_EN = (
    "This is a guide, not a final decision. Please verify current details on the official source before applying."
)
MANDATORY_DISCLAIMER_HI = (
    "यह एक मार्गदर्शिका है, अंतिम निर्णय नहीं। कृपया आवेदन करने से पहले आधिकारिक स्रोत पर वर्तमान विवरण सत्यापित करें।"
)

NAVI_SCHEME_SYSTEM_PROMPT = (
    "You are the NAVI SCHEME AI Assistant — an authoritative, crystal-clear, and deeply helpful guide "
    "for Indian Central and State Government welfare schemes, scholarships, farmer subsidies, healthcare benefits, "
    "pensions, and citizen entitlements.\n\n"
    "YOUR CORE PRINCIPLES:\n"
    "1. ACCURACY & ZERO HALLUCINATION: Only state facts grounded in the provided SCHEME DATA. Never invent criteria, "
    "benefit amounts, deadlines, or contact portals.\n"
    "2. CRYSTAL-CLEAR & COMPLETE: Provide thorough, structured, and complete explanations. Never truncate with '...' or leave out crucial details.\n"
    "3. STRUCTURED FORMATTING: Use Markdown headings (###), bold key terms (**), bulleted checklists (•), and numbered application steps (1., 2., 3.).\n"
    "4. STEP-BY-STEP APPLICATION: When asked how to apply, give explicit numbered steps and document checklists.\n"
    "5. LOAN & EMI CALCULATIONS: Report verified loan/EMI numbers using provided loan calculator data.\n"
    "6. CITIZEN SAFETY & ZERO MIDDLEMEN: Emphasize that all genuine welfare schemes are 100% FREE to apply. "
    "Warn citizens against paying unauthorized agents, sharing OTPs, or trusting fake links.\n"
    "7. WARM & PROFESSIONAL TONE: Be respectful, empathetic, and accessible to citizens from all backgrounds."
)


@dataclass
class ExplainOutput:
    plain_language_summary: str
    why_matched: str
    next_steps: str
    disclaimer: str
    source_used: str  # "gemini_grounded" or "structured_fallback"


def validate_ai_output(output_text: str, scheme_facts: Dict[str, Any]) -> bool:
    """
    Deterministic post-generation guardrail check:
    Ensures output is grounded and valid.
    """
    if not output_text or not output_text.strip():
        return False

    # Check URLs if present
    found_urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', output_text)
    known_urls = [scheme_facts.get("application_url", "").lower()]
    for u in scheme_facts.get("source_urls", []):
        known_urls.append(u.lower())

    for url in found_urls:
        url_clean = url.lower().rstrip(".,;)")
        if not any(known in url_clean or url_clean in known for known in known_urls if known):
            return False

    return True


def create_structured_fallback(
    scheme_facts: Dict[str, Any],
    matched_criteria: List[Dict[str, Any]],
    language: str = "en",
) -> ExplainOutput:
    """Accurate, zero-hallucination structured explanation fallback."""
    title = scheme_facts.get("title") or scheme_facts.get("name", "Scheme")
    benefits = scheme_facts.get("benefits", "Financial and welfare assistance as per government guidelines.")
    steps = scheme_facts.get("application_steps") or scheme_facts.get("application_process") or "Visit official portal to apply."
    
    satisfied_criteria = [c for c in matched_criteria if c.get("satisfied", True)]
    if satisfied_criteria:
        criteria_bullets = "\n".join(f"• {c.get('rule_description') or c.get('field')}" for c in satisfied_criteria[:3])
    else:
        criteria_bullets = "• General public welfare criteria"

    if language == "hi":
        summary = f"{title} के तहत पात्र नागरिकों को {benefits} प्रदान किया जाता है।"
        why = f"आपकी प्रोफ़ाइल निम्नलिखित पात्रता मानदंडों से मेल खाती है:\n{criteria_bullets}"
        next_steps = f"आवेदन प्रक्रिया: {steps}"
        disclaimer = MANDATORY_DISCLAIMER_HI
    else:
        summary = f"{title} provides eligible citizens with {benefits}"
        why = f"Matched based on your profile criteria:\n{criteria_bullets}"
        next_steps = f"Application Steps: {steps}"
        disclaimer = MANDATORY_DISCLAIMER_EN

    return ExplainOutput(
        plain_language_summary=summary,
        why_matched=why,
        next_steps=next_steps,
        disclaimer=disclaimer,
        source_used="structured_fallback",
    )
