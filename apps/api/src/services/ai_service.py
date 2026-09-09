import json
import re
from typing import Optional, List, Dict, Any

from src.config.settings import get_settings
from packages.ai.explain import (
    ExplainOutput,
    validate_ai_output,
    create_structured_fallback,
    MANDATORY_DISCLAIMER_EN,
    MANDATORY_DISCLAIMER_HI,
    NAVI_SCHEME_SYSTEM_PROMPT,
)
from packages.matching.generalized_engine import (
    MatchProfile,
    MatchIntent,
    parse_query_intent,
    evaluate_scheme_match,
    rank_and_filter_schemes,
)

try:
    from google import genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


def clean_bureaucratic_text(text: str) -> str:
    """Simplifies dense bureaucratic text into clean, human-friendly wording without truncation."""
    if not text:
        return ""
    cleaned = text
    # Clean up common governmental boilerplate phrases
    cleaned = re.sub(r"Pattern of Assistance:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Type of Assistance and Entitlement\s*(\(If any\))?:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Eligibility Criteria:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Under the umbrella scheme\s*.*?,\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def calculate_loan_emi(principal: float, annual_rate_pct: float = 7.0, tenure_months: int = 12) -> Dict[str, Any]:
    """Calculate EMI, interest, and total payable amount for government loan/credit schemes (Rule 4)."""
    if principal <= 0 or tenure_months <= 0:
        return {}
    r = (annual_rate_pct / 100.0) / 12.0
    if r == 0:
        emi = principal / tenure_months
        total_payment = principal
        total_interest = 0.0
    else:
        emi = (principal * r * ((1.0 + r) ** tenure_months)) / (((1.0 + r) ** tenure_months) - 1.0)
        total_payment = emi * tenure_months
        total_interest = total_payment - principal

    return {
        "principal": principal,
        "annual_rate_pct": annual_rate_pct,
        "tenure_months": tenure_months,
        "tenure_years": round(tenure_months / 12.0, 1),
        "monthly_emi": round(emi, 2),
        "total_interest": round(total_interest, 2),
        "total_payable": round(total_payment, 2),
    }


class GroundedAIService:
    def __init__(self):
        self.settings = get_settings()
        self._client = None
        self._init_client()

    @property
    def model_name(self) -> str:
        model = self.settings.gemini_model or "gemini-3.7-flash"
        return model

    def _init_client(self):
        """Initialize Google GenAI client if API key is provided."""
        self._client = None
        # Client will be lazily loaded when needed

    def _get_active_scheme_from_session(self, session_id: str, repository: Any) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent scheme discussed or matched in this session."""
        try:
            messages = repository.get_session_messages(session_id, limit=10, desc=True)
            for m in messages:
                meta_raw = m.get("metadata_json") or "{}"
                try:
                    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
                    if meta.get("scheme_id"):
                        sch = repository.get_scheme_by_id_or_slug(meta["scheme_id"])
                        if sch:
                            return sch
                    if meta.get("matched_ids") and len(meta["matched_ids"]) > 0:
                        sch = repository.get_scheme_by_id_or_slug(meta["matched_ids"][0])
                        if sch:
                            return sch
                except Exception:
                    pass
        except Exception:
            pass
        return None


    def _generate_content(self, system_instruction: str, user_prompt: str, json_mode: bool = False) -> Optional[str]:
        """Robust Gemini generative execution with candidate model cascade fallback and direct REST/SDK resilience."""
        candidate_models = [
            self.settings.gemini_model,
            "gemini-3.6-flash",
            "gemini-flash-latest",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
            "gemini-3.5-flash",
        ]
        # Remove duplicates while preserving order
        seen = set()
        models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

        # 1. Direct REST API via standard library with model cascade
        if self.settings.gemini_api_key:
            import urllib.request
            import socket
            for clean_model in models_to_try:
                try:
                    socket.setdefaulttimeout(7.0)
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={self.settings.gemini_api_key}"
                    body: Dict[str, Any] = {
                        "contents": [{"parts": [{"text": user_prompt}]}],
                        "systemInstruction": {"parts": [{"text": system_instruction}]},
                        "generationConfig": {
                            "temperature": 0.2,
                            "maxOutputTokens": self.settings.gemini_max_output_tokens,
                        }
                    }
                    if json_mode:
                        body["generationConfig"]["responseMimeType"] = "application/json"

                    req = urllib.request.Request(
                        url,
                        data=json.dumps(body).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req, timeout=7.0) as res:
                        data = json.loads(res.read().decode("utf-8"))
                        text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text and text.strip():
                            return text.strip()
                except Exception as e:
                    print(f"[INFO] Gemini REST model notice ({clean_model}): {e}")
                    continue

        # 2. Try google.genai SDK as fallback
        if self._client:
            for clean_model in models_to_try:
                try:
                    config_args = {
                        "system_instruction": system_instruction,
                        "temperature": 0.2,
                        "max_output_tokens": self.settings.gemini_max_output_tokens,
                    }
                    if json_mode:
                        config_args["response_mime_type"] = "application/json"

                    response = self._client.models.generate_content(
                        model=clean_model,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(**config_args),
                    )
                    if response and response.text and response.text.strip():
                        return response.text.strip()
                except Exception as e:
                    print(f"[INFO] Gemini SDK generation notice ({clean_model}): {e}")
                    continue

        return None

    def explain_scheme(
        self,
        scheme_facts: Dict[str, Any],
        matched_criteria: List[Dict[str, Any]],
        confidence: str = "high",
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Grounded scheme explanation (§5 of engineering spec).
        Constrained strictly to structured catalog facts.
        """
        fallback_res = create_structured_fallback(scheme_facts, matched_criteria, language)

        target_lang = "Hindi" if language == "hi" else "English"
        scheme_context = {
            "name": scheme_facts.get("title") or scheme_facts.get("name"),
            "issuing_body": scheme_facts.get("ministry") or scheme_facts.get("issuing_body", "Government of India"),
            "benefits": scheme_facts.get("benefits"),
            "eligibility_summary": scheme_facts.get("eligibility_summary"),
            "documents_required": scheme_facts.get("documents_required"),
            "application_steps": scheme_facts.get("application_process") or scheme_facts.get("application_steps"),
            "application_url": scheme_facts.get("application_url"),
            "deadline": scheme_facts.get("deadline"),
        }

        system_instruction = (
            f"{NAVI_SCHEME_SYSTEM_PROMPT}\n\n"
            f"ADDITIONAL INSTRUCTION FOR SCHEME CARD EXPLANATION:\n"
            f"- Explain in {target_lang}.\n"
            f"- Respond ONLY in valid JSON with keys: 'plain_language_summary', 'why_matched', 'next_steps'."
        )

        user_prompt = (
            f"SCHEME DATA:\n{json.dumps(scheme_context, ensure_ascii=False)}\n\n"
            f"MATCHED_CRITERIA:\n{json.dumps(matched_criteria, ensure_ascii=False)}\n\n"
            f"TASK: Explain why this scheme matched in {target_lang}."
        )

        try:
            raw_response = self._generate_content(system_instruction, user_prompt, json_mode=True)
            if raw_response:
                parsed = json.loads(raw_response)
                full_text = f"{parsed.get('plain_language_summary', '')} {parsed.get('why_matched', '')} {parsed.get('next_steps', '')}"

                # Apply post-generation guardrail validation
                if validate_ai_output(full_text, scheme_facts):
                    disclaimer = MANDATORY_DISCLAIMER_HI if language == "hi" else MANDATORY_DISCLAIMER_EN
                    return {
                        "plain_language_summary": parsed.get("plain_language_summary", fallback_res.plain_language_summary),
                        "why_matched": parsed.get("why_matched", fallback_res.why_matched),
                        "next_steps": parsed.get("next_steps", fallback_res.next_steps),
                        "disclaimer": disclaimer,
                        "source": "gemini_grounded",
                    }
        except Exception as e:
            print(f"[INFO] Gemini explanation soft fallback: {e}")

        return {
            "plain_language_summary": fallback_res.plain_language_summary,
            "why_matched": fallback_res.why_matched,
            "next_steps": fallback_res.next_steps,
            "disclaimer": fallback_res.disclaimer,
            "source": "structured_fallback",
        }

    def extract_intent_and_entities(self, text_input: str) -> Dict[str, Any]:
        """
        Extract profile parameters with conversational intent and safety checks.
        Handles platform introduction, loan EMI calculations, scam alerts, fraud refusal,
        off-topic detection, and proxy profiles.
        """
        text_lower = text_input.lower().strip()

        # 1. Edge Case: Harmful / Fraud query (faking income/caste/documents/bribes) - Rule 9
        if (
            any(w in text_lower for w in ["bribe", "dalal", "cheat eligibility", "falsify", "fake certificate", "forge certificate", "fake document"])
            or re.search(r"\b(fake|forge|fabricat|falsif|buy)\b.*\b(income|caste|certificate|document|paper|eligibility|card|aadhaar|ration)\b", text_lower)
            or re.search(r"\b(bribe|money to officer|pay officer|under the table)\b", text_lower)
        ):
            return {
                "special_case": "fraud_refusal",
                "message": (
                    "⚠️ I cannot assist with falsifying or misrepresenting income, caste, or identity details. "
                    "Government welfare schemes have strict verification, and submitting false documents is a punishable legal offense. "
                    "All genuine schemes are 100% free and require no middlemen. I am happy to help you discover legitimate schemes you qualify for."
                ),
            }

        # 2. Edge Case: Scam / Middlemen alert - Rule 9
        if any(w in text_lower for w in ["pay agent", "commission", "agent asking money", "paying for form", "dalal", "pay money to get scheme"]):
            return {
                "special_case": "scam_warning",
                "message": (
                    "🚨 **Important Fraud Alert:** Applying for government welfare schemes is **100% free of cost**. "
                    "Never pay unauthorized agents or middlemen claiming to guarantee benefits or approvals. "
                    "Always apply directly through official portals (.gov.in) or authorized Common Service Centres (CSC)."
                ),
            }

        # 3. Edge Case: Platform inquiry ("tell me about navi scheme", "what is navi scheme", etc.)
        if any(p in text_lower for p in [
            "about navi scheme", "what is navi scheme", "tell me about navi scheme",
            "what is navischeme", "navi scheme", "who are you", "what can you do",
            "how do you work", "how does navi scheme work", "help me", "what schemes do you have",
            "about this website", "about this app"
        ]):
            return {
                "special_case": "navi_scheme_intro",
                "message": (
                    "🏛️ **Welcome to Navi Scheme!**\n\n"
                    "I am your official assistant for discovering and applying for Indian Central and State Government welfare schemes.\n\n"
                    "**Here is what I can help you with:**\n"
                    "• **Personalized Scheme Matching:** Scholarships, farmer subsidies, pensions, health cards & women welfare based on your profile.\n"
                    "• **Application Guides & Documents:** Numbered step-by-step instructions and required documents.\n"
                    "• **Loan & EMI Calculations:** Exact repayment and subsidy figures for government credit schemes.\n"
                    "• **100% Free & Direct:** Verified official government portals with no agents or middlemen.\n\n"
                    "💡 *To get started, tell me your state, age, or occupation (e.g. 'Student in Karnataka looking for scholarships' or 'Farmer in Maharashtra').*"
                ),
            }

        # 4. Edge Case: General Greetings
        if text_lower in ["hello", "hi", "hey", "good morning", "good evening", "namaste", "namaskar"]:
            return {
                "special_case": "greeting_or_offtopic",
                "message": (
                    "👋 **Namaste! I am the Navi Scheme Assistant.**\n\n"
                    "I help Indian citizens discover verified government schemes, scholarships, and financial assistance.\n\n"
                    "Tell me about your situation (e.g., *'I am a 20-year-old student from UP'* or *'Farmer in Maharashtra'*), and I will find verified schemes for you!"
                ),
            }

        # 5. Loan Amount, EMI, & Repayment Calculator - Rule 4
        if any(w in text_lower for w in ["emi", "loan calculation", "calculate emi", "loan amount", "repayment", "monthly installment", "interest rate", "kist", "interest"]):
            # Extract principal
            principal = None
            tenure_months = None
            rate = None

            lakh_match = re.search(r"(?:₹|rs\.?|inr)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:lakh|lac|lacs|lakhs)\b", text_lower)
            if lakh_match:
                principal = float(lakh_match.group(1)) * 100000.0
            else:
                num_match = re.search(r"(?:₹|rs\.?|inr)?\s*([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]+)?|[0-9]{4,10})\b", text_lower)
                if num_match:
                    raw_num = num_match.group(1).replace(",", "")
                    try:
                        val = float(raw_num)
                        if val >= 1000:
                            principal = val
                    except ValueError:
                        pass

            year_match = re.search(r"([0-9]{1,2})\s*(?:years?|yrs?|yr|saal|sal)\b", text_lower)
            month_match = re.search(r"([0-9]{1,3})\s*(?:months?|mo|mahine|mahina)\b", text_lower)
            if year_match:
                tenure_months = int(year_match.group(1)) * 12
            elif month_match:
                tenure_months = int(month_match.group(1))

            rate_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:%|\bpercent\b|\bpratishat\b|\binterest\b)", text_lower)
            if rate_match:
                rate = float(rate_match.group(1))

            if principal and tenure_months and rate:
                calc = calculate_loan_emi(principal, annual_rate_pct=rate, tenure_months=tenure_months)
                return {
                    "special_case": "loan_calculator",
                    "data": calc,
                    "message": (
                        f"📊 **Government Scheme Loan & EMI Breakdown** (Rule 4)\n\n"
                        f"• **Loan Amount (Principal):** ₹{calc['principal']:,.0f}\n"
                        f"• **Interest Rate:** {calc['annual_rate_pct']}% p.a.\n"
                        f"• **Tenure:** {calc['tenure_months']} Months ({calc['tenure_years']} Years)\n"
                        f"• **Estimated Monthly EMI:** **₹{calc['monthly_emi']:,.2f}**\n"
                        f"• **Total Interest Payable:** ₹{calc['total_interest']:,.2f}\n"
                        f"• **Total Repayment Amount:** ₹{calc['total_payable']:,.2f}\n\n"
                        f"💡 *Note: Subsidized government credit schemes (like PM SVANidhi, PMEGP, or Mudra) may also provide capital grants or interest rebates upon timely repayment.*"
                    ),
                }
            elif principal and tenure_months and not rate:
                return {
                    "special_case": "loan_rate_needed",
                    "principal": principal,
                    "tenure_months": tenure_months,
                    "message": (
                        f"📊 **Loan Details Received:** ₹{principal:,.0f} over {tenure_months} months.\n\n"
                        f"Please specify the **annual interest rate** (or interest subsidy percentage) to calculate your exact monthly EMI.\n\n"
                        f"💡 *If you are asking about a specific scheme, type the scheme name or interest rate (e.g. '7% interest' or 'PMEGP').*"
                    ),
                }
            elif any(w in text_lower for w in ["calculate emi", "emi for", "loan emi", "monthly emi", "repayment of", "what is emi", "how much emi"]):
                return {
                    "special_case": "loan_missing_details",
                    "message": (
                        "📊 **Government Loan & EMI Calculator** (Rule 4)\n\n"
                        "To calculate your exact monthly EMI and repayment schedule, please provide:\n"
                        "1. **Loan Amount** (e.g., *₹50,000* or *₹2 Lakh*)\n"
                        "2. **Tenure** (e.g., *1 year* or *24 months*)\n"
                        "3. **Interest Rate** (e.g., *7%*, or mention the scheme name if it specifies an interest rate)\n\n"
                        "💡 *Example prompt: 'Calculate EMI for ₹50,000 for 2 years at 7% interest'*"
                    ),
                }

        # 6. Deadlines & Expired Schemes Tracker
        if any(w in text_lower for w in ["expired schemes", "strict deadlines", "check expired", "application deadline", "last date", "which schemes are expired", "scheme validity"]):
            return {
                "special_case": "deadlines_tracker",
                "message": (
                    "📅 **Government Welfare Scheme Validity & Deadline Status**\n\n"
                    "• **National Scholarship Portal (NSP) Schemes:** Annual academic cycle closes on **30th November 2026**. Apply before institutional verification cutoff.\n"
                    "• **Pradhan Mantri Awas Yojana (PMAY-U / PMAY-G):** Extended through **31st December 2026** for sanctioned geo-tagged pucca houses.\n"
                    "• **PM SVANidhi Micro-Credit Loans:** Active through **December 2026** across urban local bodies.\n"
                    "• **Ongoing / Continuous Schemes (No Expiry):** *PM-KISAN, Sukanya Samriddhi Yojana (SSY), Ayushman Bharat PM-JAY, Atal Pension Yojana (APY), Mukhyamantri Majhi Ladki Bahin Yojana* remain open for enrollment year-round.\n\n"
                    "💡 *Advice: If a state welfare portal shows a closed cycle, applications typically reopen during the next budget quarter.*"
                ),
            }

        # 7. Newly Launched & Flagship Schemes
        if any(w in text_lower for w in ["new schemes", "newly launched", "latest schemes", "recent schemes", "recent launches", "what new schemes"]):
            return {
                "special_case": "new_schemes",
                "message": (
                    "🚀 **Newly Launched & Flagship Government Schemes (2026 Update)**\n\n"
                    "1. **Ayushman Vay Vandana Scheme (Senior Citizens 70+):** Free ₹5 Lakh annual cashless healthcare coverage for ALL citizens aged 70+, regardless of family income.\n"
                    "2. **Mukhyamantri Majhi Ladki Bahin Yojana (Maharashtra):** Direct ₹1,500/month DBT cash transfer for resident women aged 21–65.\n"
                    "3. **PM Vishwakarma Scheme:** Collateral-free loans up to ₹3 Lakh at 5% interest plus ₹15,000 toolkit grant for traditional artisans & craftspeople.\n"
                    "4. **PM Surya Ghar: Muft Bijli Yojana:** Up to ₹78,000 direct capital subsidy for residential rooftop solar installation.\n\n"
                    "💡 *Tell me your state or category (e.g., 'Farmer in Maharashtra' or 'Student in UP') to match with all active schemes.*"
                ),
            }

        # 8. Proxy profile detection ("filling for my father / mother / daughter")
        is_proxy = any(w in text_lower for w in ["for my father", "for my mother", "for my son", "for my daughter", "for my wife", "for my parents"])

        # 9. Extract entities
        return self._local_entity_extraction(text_input, is_proxy=is_proxy)

    def _local_entity_extraction(self, text_input: str, is_proxy: bool = False) -> Dict[str, Any]:
        """Comprehensive local Indian government entity & profile extractor."""
        text_lower = text_input.lower()

        state = None
        age = None
        gender = "All"
        caste = None
        category = None
        occupation = None
        keywords = []

        # Social Category
        if re.search(r"\b(obc|other backward class|other backward classes|pichhda|pichda|non-creamy layer|ncl)\b", text_lower):
            caste = "OBC"
            keywords.append("OBC")
        elif re.search(r"\b(sc|scheduled caste|scheduled castes|dalit|anusuchit jati)\b", text_lower):
            caste = "SC"
            keywords.append("SC")
        elif re.search(r"\b(st|scheduled tribe|scheduled tribes|adivasi|anusuchit janjati|tribal)\b", text_lower):
            caste = "ST"
            keywords.append("ST")
        elif re.search(r"\b(ews|economically weaker section|economically backward|econo.*weaker)\b", text_lower):
            caste = "EWS"
            keywords.append("EWS")
        elif re.search(r"\b(minority|minorities|muslim|christian|sikh|jain|buddhist|parsi)\b", text_lower):
            caste = "Minority"
            keywords.append("Minority")
        elif re.search(r"\b(general category|open category|general class|unreserved|ur category)\b", text_lower):
            caste = "General"

        # Age: Comprehensive natural phrasing extraction
        age_patterns = [
            # "my age is 15", "age is 15", "age: 15", "age - 15", "age = 15", "age 15"
            r"\b(?:my\s+)?age\s*(?:is|:|-|=|\b)\s*([0-9]{1,2})\b",
            # "I am 15", "I'm 15", "im 15", "i am aged 15", "i'm aged around 15"
            r"\b(?:i\s*am|i['’]?m|im)\s*(?:aged?|about|around)?\s*([0-9]{1,2})(?:\s*(?:years?|yrs?|yr|saal|sal))?(?:\s*old)?\b",
            # "aged 15", "aged around 15", "aged about 15", "aged: 15"
            r"\b(?:aged?)\s*(?:around|about|is|:|-|=)?\s*([0-9]{1,2})\b",
            # "15 years old", "15 yrs old", "15 yrs", "15 yr", "15 years", "15 saal", "15 sal"
            r"\b([0-9]{1,2})\s*(?:years?|yrs?|yr|saal|sal)\s*(?:old)?\b",
            # "age group 15", "age bracket 15"
            r"\b(?:age|aged)\s*(?:bracket|group)?\s*[:=-]?\s*([0-9]{1,2})\b",
        ]
        for pat in age_patterns:
            match = re.search(pat, text_lower)
            if match:
                try:
                    val = int(match.group(1))
                    if 0 <= val <= 120:
                        age = val
                        break
                except ValueError:
                    pass

        # Occupation
        if any(w in text_lower for w in ["farmer", "kisan", "krishi", "farming", "crop", "kheti"]):
            occupation = "farmer"
            category = "Agriculture"
        elif any(w in text_lower for w in ["student", "studying", "college", "school", "scholarship", "exam", "degree", "diploma"]):
            occupation = "student"
            category = "Education"
        elif any(w in text_lower for w in ["business", "shop", "trader", "msme", "self employed", "startup", "vendor", "entrepreneur"]):
            occupation = "self_employed"
            category = "Social Welfare"
        elif any(w in text_lower for w in ["daily wage", "labor", "labour", "mazdoor", "informal", "worker"]):
            occupation = "daily_wage_informal"
            category = "Social Welfare"
        elif any(w in text_lower for w in ["retired", "senior citizen", "pensioner", "old age", "vriddha"]):
            occupation = "retired"
            category = "Pension"
            if age is None:
                age = 65
        elif any(w in text_lower for w in ["homemaker", "housewife", "mahila"]):
            occupation = "homemaker"
            category = "Women & Child"
        elif any(w in text_lower for w in ["unemployed", "job seeker", "berozgar", "looking for job"]):
            occupation = "unemployed"
            category = "Employment"

        # States & UTs mapping
        known_states = [
            "maharashtra", "uttar pradesh", "madhya pradesh", "karnataka", "bihar",
            "tamil nadu", "rajasthan", "gujarat", "west bengal", "delhi", "kerala",
            "punjab", "haryana", "andhra pradesh", "telangana", "odisha", "assam",
            "jharkhand", "chhattisgarh", "uttarakhand", "himachal pradesh", "goa",
            "jammu & kashmir", "jammu and kashmir", "ladakh", "lakshadweep", "puducherry",
            "chandigarh", "sikkim", "tripura", "meghalaya", "manipur", "mizoram", "nagaland", "all india"
        ]
        for st in known_states:
            if re.search(rf"\b{re.escape(st)}\b", text_lower):
                state = "All India" if st == "all india" else st.title()
                break

        # Indian Cities / Districts mapping to States
        if not state:
            cities_map = {
                # Maharashtra
                "nagpur": "Maharashtra", "mumbai": "Maharashtra", "pune": "Maharashtra", "nashik": "Maharashtra",
                "thane": "Maharashtra", "aurangabad": "Maharashtra", "chhatrapati sambhaji nagar": "Maharashtra",
                "sambhajinagar": "Maharashtra", "solapur": "Maharashtra", "kolhapur": "Maharashtra", "amravati": "Maharashtra",
                "navi mumbai": "Maharashtra", "jalgaon": "Maharashtra", "akola": "Maharashtra", "latur": "Maharashtra",
                "dhule": "Maharashtra", "ahmednagar": "Maharashtra", "chandrapur": "Maharashtra", "parbhani": "Maharashtra",
                "nanded": "Maharashtra", "satara": "Maharashtra", "sangli": "Maharashtra", "wardha": "Maharashtra",
                "yavatmal": "Maharashtra", "buldhana": "Maharashtra", "jalna": "Maharashtra", "beed": "Maharashtra",
                # Uttar Pradesh
                "lucknow": "Uttar Pradesh", "kanpur": "Uttar Pradesh", "varanasi": "Uttar Pradesh", "banaras": "Uttar Pradesh",
                "kashi": "Uttar Pradesh", "agra": "Uttar Pradesh", "prayagraj": "Uttar Pradesh", "allahabad": "Uttar Pradesh",
                "noida": "Uttar Pradesh", "ghaziabad": "Uttar Pradesh", "meerut": "Uttar Pradesh", "gorakhpur": "Uttar Pradesh",
                "bareilly": "Uttar Pradesh", "aligarh": "Uttar Pradesh", "moradabad": "Uttar Pradesh", "mathura": "Uttar Pradesh",
                "jhansi": "Uttar Pradesh", "ayodhya": "Uttar Pradesh",
                # Karnataka
                "bangalore": "Karnataka", "bengaluru": "Karnataka", "mysore": "Karnataka", "mysuru": "Karnataka",
                "hubli": "Karnataka", "hubballi": "Karnataka", "dharwad": "Karnataka", "mangalore": "Karnataka",
                "mangaluru": "Karnataka", "belgaum": "Karnataka", "belagavi": "Karnataka", "gulbarga": "Karnataka",
                # Delhi
                "delhi": "Delhi", "new delhi": "Delhi",
                # Bihar
                "patna": "Bihar", "gaya": "Bihar", "bhagalpur": "Bihar", "muzaffarpur": "Bihar", "purnia": "Bihar",
                # Rajasthan
                "jaipur": "Rajasthan", "jodhpur": "Rajasthan", "udaipur": "Rajasthan", "kota": "Rajasthan", "bikaner": "Rajasthan", "ajmer": "Rajasthan",
                # Gujarat
                "ahmedabad": "Gujarat", "surat": "Gujarat", "vadodara": "Gujarat", "rajkot": "Gujarat", "gandhinagar": "Gujarat",
                # Madhya Pradesh
                "bhopal": "Madhya Pradesh", "indore": "Madhya Pradesh", "jabalpur": "Madhya Pradesh", "gwalior": "Madhya Pradesh", "ujjain": "Madhya Pradesh",
                # Tamil Nadu
                "chennai": "Tamil Nadu", "coimbatore": "Tamil Nadu", "madurai": "Tamil Nadu", "tiruchirappalli": "Tamil Nadu", "salem": "Tamil Nadu",
                # Telangana & AP
                "hyderabad": "Telangana", "warangal": "Telangana", "visakhapatnam": "Andhra Pradesh", "vizag": "Andhra Pradesh", "vijayawada": "Andhra Pradesh", "guntur": "Andhra Pradesh", "tirupati": "Andhra Pradesh",
                # West Bengal
                "kolkata": "West Bengal", "howrah": "West Bengal", "durgapur": "West Bengal", "siliguri": "West Bengal",
                # Punjab & Haryana
                "chandigarh": "Punjab", "ludhiana": "Punjab", "amritsar": "Punjab", "jalandhar": "Punjab", "gurgaon": "Haryana", "gurugram": "Haryana", "faridabad": "Haryana",
                # Kerala
                "thiruvananthapuram": "Kerala", "kochi": "Kerala", "kozhikode": "Kerala", "thrissur": "Kerala",
                # Odisha & Assam
                "bhubaneswar": "Odisha", "cuttack": "Odisha", "rourkela": "Odisha", "guwahati": "Assam", "silchar": "Assam"
            }
            for city, c_state in cities_map.items():
                if re.search(rf"\b{re.escape(city)}\b", text_lower):
                    state = c_state
                    break

        # Subject & Category
        subject = None
        if any(w in text_lower for w in ["inter caste", "intercaste", "marriage", "shadi", "vivah", "shaadi", "nikah"]):
            category = "Social Welfare"
            subject = "marriage"
            keywords.append("marriage")
        elif any(w in text_lower for w in ["health", "hospital", "medical", "treatment", "bimar", "ayushman", "arogya", "swasthya"]):
            category = "Health"
            subject = "health"
        elif any(w in text_lower for w in ["house", "housing", "awas", "home", "ghar", "makan"]):
            category = "Housing"
            subject = "housing"
        elif any(w in text_lower for w in ["pension", "old age", "senior", "retirement", "vriddha", "niradhar"]):
            category = "Pension"
            subject = "pension"
        elif any(w in text_lower for w in ["daughter", "girl", "woman", "women", "mahila", "ladli", "sukanya", "beti"]):
            category = "Women & Child"
            subject = "women"

        # Gender
        if any(w in text_lower for w in ["daughter", "girl", "woman", "women", "female", "she", "her", "mahila", "ladki", "mother", "wife"]):
            gender = "Female"
        elif any(w in text_lower for w in ["son", "boy", "man", "male", "he", "his", "ladka", "father", "husband"]):
            gender = "Male"

        return {
            "special_case": None,
            "state": state,
            "age": age,
            "gender": gender,
            "caste": caste,
            "category": category,
            "occupation": occupation,
            "subject": subject,
            "keywords": keywords,
            "is_proxy_profile": is_proxy,
            "raw_text": text_input,
        }

    def generate_screen_by_screen_application_guide(
        self,
        scheme: Dict[str, Any],
        user_query: str = "",
        language: str = "en"
    ) -> str:
        """
        Generates an exact, screen-by-screen official portal application walkthrough
        (Step 1 -> Step 2 -> Step 3 -> Step 4 -> Step 5 -> Acknowledgement ID tracking).
        """
        title = scheme.get("title") or scheme.get("name") or "Government Scheme"
        ministry = scheme.get("ministry") or scheme.get("issuing_body") or "Government of India"
        state = scheme.get("state") or "All India"
        portal = scheme.get("application_url") or "https://www.india.gov.in"
        mode = scheme.get("application_mode") or "online"

        # Documents
        docs_raw = scheme.get("documents_required_list") or scheme.get("documents_required")
        if isinstance(docs_raw, list) and docs_raw:
            docs_lines = [f"• {d}" for d in docs_raw]
        elif isinstance(docs_raw, str) and docs_raw.strip():
            split_docs = re.split(r"[\n,;]+", docs_raw)
            clean_split = [d.strip() for d in split_docs if len(d.strip()) > 3]
            docs_lines = [f"• {d}" for d in clean_split] if clean_split else [f"• {docs_raw.strip()}"]
        else:
            docs_lines = [
                "• Identity Proof (Aadhaar Card / Voter ID)",
                "• Residence / Domicile Certificate",
                "• Aadhaar-seeded Bank Passbook (showing IFSC & Account Number)",
                "• Income / Caste Certificate (if applicable)"
            ]

        # Application steps from DB
        steps_raw = scheme.get("application_steps_list") or scheme.get("application_process") or scheme.get("application_steps")
        db_steps = []
        if isinstance(steps_raw, list) and steps_raw:
            db_steps = [st.strip() for st in steps_raw if st.strip()]
        elif isinstance(steps_raw, str) and steps_raw.strip():
            raw_split = re.split(r"(?:Step\s*[0-9]+:?|(?<=\.)\s+(?=[0-9]+\.))", steps_raw)
            db_steps = [st.strip() for st in raw_split if len(st.strip()) > 5]

        target_lang = "Hindi" if language == "hi" else "English"

        # 1. Try Gemini grounded screen-by-screen walkthrough if available
        if self._client or self.settings.gemini_api_key:
            try:
                sys_inst = (
                    f"{NAVI_SCHEME_SYSTEM_PROMPT}\n\n"
                    f"TASK: Provide a precise, screen-by-screen official portal application walkthrough for '{title}'.\n"
                    f"- Respond in {target_lang}.\n"
                    f"- Format as 5 explicit numbered stages:\n"
                    f"  1. Portal Navigation & Homepage Action (Open verified URL, click Citizen / Apply Now)\n"
                    f"  2. Citizen Authentication & Registration (Aadhaar OTP / Mobile e-KYC)\n"
                    f"  3. Form Navigation & Profile / Bank Account Entry (Aadhaar-seeded DBT details)\n"
                    f"  4. Uploading Supporting Documents (Checklist of required certificates)\n"
                    f"  5. Final Review, Submission & Application Reference Tracking ID\n"
                    f"- Include Document Readiness Checklist.\n"
                    f"- Include Official Application Link [{portal}]({portal}).\n"
                    f"- Include Anti-Fraud Advisory (100% FREE to apply, never pay agents or share OTPs).\n"
                    f"- Do not truncate."
                )
                user_prompt = (
                    f"Citizen Query: \"{user_query or f'How do I apply for {title}?'}\"\n\n"
                    f"SCHEME RECORD:\n"
                    f"Title: {title}\n"
                    f"Issuing Body: {ministry}\n"
                    f"Jurisdiction: {state}\n"
                    f"Application Portal: {portal}\n"
                    f"Application Mode: {mode}\n"
                    f"Database Application Steps: {json.dumps(db_steps, ensure_ascii=False)}\n"
                    f"Documents Required: {json.dumps(docs_lines, ensure_ascii=False)}\n\n"
                    f"Generate the complete screen-by-screen portal guide in {target_lang}."
                )
                gen_reply = self._generate_content(sys_inst, user_prompt, json_mode=False)
                if gen_reply and len(gen_reply.strip()) > 120:
                    return gen_reply
            except Exception as e:
                print(f"[INFO] Gemini screen-by-screen guide notice: {e}")

        # 2. Structured Grounded Fallback
        lines = [
            f"### 🚀 **Screen-by-Screen Application Guide: {title}**",
            f"*{ministry} • {state} • Verified Official Process*\n",
            "Follow these exact screen-by-screen steps on the official government portal:\n",
            f"#### **Step 1: Open the Verified Official Portal**",
            f"• Visit the official government portal: **[{portal}]({portal})**",
            f"• On the homepage, locate and click on **'Citizen Registration'**, **'Apply Online'**, or **'New Beneficiary Corner'**.",
            f"• 🔒 *Always verify the URL ends with `.gov.in` or `.nic.in` for genuine government portals.*\n",
            f"#### **Step 2: Citizen Authentication & e-KYC (Aadhaar / Mobile OTP)**",
            f"• Enter your **12-digit Aadhaar Number** and active mobile number.",
            f"• Enter the 6-digit OTP received via SMS to complete instant digital e-KYC verification.",
            f"• Set your secure login password or MPIN for future status checks.\n",
            f"#### **Step 3: Fill Application Form & Bank DBT Details**",
            f"• Select **{title}** under the relevant department/scheme list.",
            f"• Enter your personal details (Full Name, Date of Birth, Gender, Category, Full Address).",
            f"• Enter your **Aadhaar-seeded Bank Account details** (Bank Name, Account Number, IFSC Code) to ensure direct DBT grant/subsidy credit.\n",
            f"#### **Step 4: Upload Required Documents**",
            f"Upload scanned self-attested copies (PDF / JPEG under 200 KB) of the required checklist:",
            "\n".join(docs_lines) + "\n",
            f"#### **Step 5: Review, Final Submission & Tracking ID**",
            f"• Review the completed form in preview mode and click **'Final Submit'**.",
            f"• Download and save your **Application Acknowledgement Receipt**.",
            f"• Note down your unique **Application Reference Number / Tracking ID** to track approval status online.\n",
            f"---\n",
            f"🔗 **Official Application Portal Link:** [{portal}]({portal})\n",
            f"💡 **Anti-Fraud Notice:** Applying for government welfare is **100% FREE OF COST**. Never pay money to middlemen, agents, or unverified cyber cafes claiming guaranteed approvals."
        ]
        return "\n".join(lines)

    def generate_scheme_deadline_info(
        self,
        scheme: Dict[str, Any],
        language: str = "en"
    ) -> str:
        """
        Reports exact application cycle validity, deadline dates, or expired cycle warnings with reopening timelines.
        """
        title = scheme.get("title") or scheme.get("name") or "Government Scheme"
        ministry = scheme.get("ministry") or scheme.get("issuing_body") or "Government of India"
        state = scheme.get("state") or "All India"
        portal = scheme.get("application_url") or "https://www.india.gov.in"
        deadline = scheme.get("deadline")
        status = scheme.get("status") or "active"

        target_lang = "Hindi" if language == "hi" else "English"

        # 1. Try Gemini Grounded Synthesis if available
        if self._client or self.settings.gemini_api_key:
            try:
                sys_inst = (
                    f"{NAVI_SCHEME_SYSTEM_PROMPT}\n\n"
                    f"TASK: Report the exact application deadline, validity, or expired status for '{title}'.\n"
                    f"- Respond in {target_lang}.\n"
                    f"- If scheme is active and ongoing (continuous enrollment like PM-KISAN, Ladki Bahin, Ayushman), state clearly that applications are open year-round with no expiry date.\n"
                    f"- If scheme has a fixed deadline, report the cutoff date and emphasize applying early.\n"
                    f"- If scheme application cycle is closed/expired, state clearly that the current cycle is closed, provide the typical reopening window (next academic cycle / fiscal quarter), and suggest active alternatives.\n"
                    f"- Include official portal [{portal}]({portal}) and anti-fraud notice."
                )
                user_prompt = (
                    f"Citizen Query: \"By when can I apply for {title}? Is it expired?\"\n\n"
                    f"SCHEME DATA:\n"
                    f"Title: {title}\n"
                    f"Ministry: {ministry}\n"
                    f"State: {state}\n"
                    f"Deadline: {deadline or 'None (Continuous Enrollment)'}\n"
                    f"Status: {status}\n"
                    f"Portal: {portal}\n"
                )
                gen_reply = self._generate_content(sys_inst, user_prompt, json_mode=False)
                if gen_reply and len(gen_reply.strip()) > 80:
                    return gen_reply
            except Exception as e:
                print(f"[INFO] Gemini deadline info notice: {e}")

        # 2. Structured Grounded Fallback
        lines = [f"### 📅 **Application Validity & Deadline: {title}**\n"]

        if deadline and str(deadline).strip() and str(deadline).strip().lower() != "none":
            deadline_str = str(deadline).strip()
            lines.extend([
                f"• **Current Application Window:** Active with fixed cycle deadline.",
                f"• **Application Cutoff Date:** **{deadline_str}**",
                f"• **Status:** Active & Accepting Applications.",
                f"• **Action Required:** Ensure all institutional verifications, e-KYC, and document uploads are finalized before the cutoff date to avoid rejection.",
                f"\n🔗 **Apply on Official Portal:** [{portal}]({portal})",
                f"💡 *Submit at least 7 days prior to deadline to prevent server congestion.*"
            ])
        elif status == "expired" or status == "closed":
            lines.extend([
                f"⚠️ **Application Status: Currently Closed / Expired for This Cycle**\n",
                f"• **Status:** The previous application cycle for {title} has concluded.",
                f"• **Expected Reopening:** State and Central welfare portals typically reopen enrollment during the next academic session or quarterly budget release.",
                f"• **Preparation:** Keep your updated Aadhaar-linked Bank Passbook, Domicile, and Income Certificates ready for instant application when the portal reopens.",
                f"\n🔗 **Official Portal for Notifications:** [{portal}]({portal})",
                f"💡 *Ask me for active alternative schemes in your state!*"
            ])
        else:
            lines.extend([
                f"• **Application Status:** **Ongoing & Active Year-Round (Continuous Enrollment)**",
                f"• **Deadline:** **No Expiry Date / Open Continuously**",
                f"• **Processing Timeline:** DBT payments or welfare benefits are typically processed within 15 to 30 working days from successful online submission.",
                f"• **How to Apply:** Applications can be submitted anytime through the official portal or authorized CSC centers.",
                f"\n🔗 **Official Portal:** [{portal}]({portal})",
                f"💡 *Applying is 100% free of charge.*"
            ])

        return "\n".join(lines)

    def generate_scheme_explanation(self, scheme: Dict[str, Any], query: str = "", language: str = "en") -> str:
        """
        Generate a comprehensive, 360-degree, crystal-clear breakdown of a government scheme
        covering Overview, Benefits, Eligibility, Required Documents, Step-by-Step Application Steps,
        and Official Portal Link.
        """
        title = scheme.get("title") or scheme.get("name") or "Government Scheme"
        ministry = scheme.get("ministry") or scheme.get("issuing_body") or "Government of India"
        state = scheme.get("state") or "All India (Central Scheme)"
        category = scheme.get("category") or scheme.get("sector") or "Citizen Welfare"
        description = scheme.get("description") or scheme.get("short_description") or ""
        benefits = clean_bureaucratic_text(scheme.get("benefits") or "Financial and social welfare assistance as per government guidelines.")
        eligibility = clean_bureaucratic_text(scheme.get("eligibility_summary") or "Open to eligible citizens meeting prescribed residency, category, or income criteria.")
        
        # Documents
        docs_raw = scheme.get("documents_required_list") or scheme.get("documents_required")
        if isinstance(docs_raw, list) and docs_raw:
            docs_lines = [f"• {d}" for d in docs_raw]
        elif isinstance(docs_raw, str) and docs_raw.strip():
            split_docs = re.split(r"[\n,;]+", docs_raw)
            clean_split = [d.strip() for d in split_docs if len(d.strip()) > 3]
            if clean_split:
                docs_lines = [f"• {d}" for d in clean_split]
            else:
                docs_lines = [f"• {docs_raw.strip()}"]
        else:
            docs_lines = [
                "• Identity Proof (Aadhaar Card / Voter ID)",
                "• Address / Domicile Certificate",
                "• Bank Account Passbook (Aadhaar linked)",
                "• Income / Caste Certificate (if applicable)"
            ]

        # Application steps
        steps_raw = scheme.get("application_steps_list") or scheme.get("application_process") or scheme.get("application_steps")
        step_lines = []
        if isinstance(steps_raw, list) and steps_raw:
            for idx, st in enumerate(steps_raw, 1):
                step_lines.append(f"{idx}. {st.strip()}")
        elif isinstance(steps_raw, str) and steps_raw.strip():
            raw_split = re.split(r"(?:Step\s*[0-9]+:?|(?<=\.)\s+(?=[0-9]+\.))", steps_raw)
            filtered_steps = [st.strip() for st in raw_split if len(st.strip()) > 5]
            if filtered_steps:
                for idx, st in enumerate(filtered_steps[:6], 1):
                    step_lines.append(f"{idx}. {st}")
            else:
                step_lines.append(f"1. {steps_raw.strip()}")
        else:
            step_lines = [
                "1. Open the verified official portal linked below and navigate to Citizen Registration / New Application.",
                "2. Authenticate your identity using your Aadhaar number and OTP verification.",
                "3. Fill in your personal profile, address, and Aadhaar-seeded bank account details for DBT.",
                "4. Upload clear scanned copies of the required supporting documents.",
                "5. Review, submit your application, and download the Acknowledgement Receipt with your Tracking ID."
            ]

        portal = scheme.get("application_url") or "https://www.india.gov.in"

        # Try Gemini grounded synthesis first for conversational polish if available
        if self._client or self.settings.gemini_api_key:
            try:
                target_lang = "Hindi" if language == "hi" else "English"
                sys_inst = (
                    f"{NAVI_SCHEME_SYSTEM_PROMPT}\n\n"
                    f"TASK: Provide a comprehensive, structured, crystal-clear explanation for the scheme '{title}'.\n"
                    f"- Respond in {target_lang}.\n"
                    f"- Format with clean Markdown headings (###), bold titles, bullet points, and numbered steps.\n"
                    f"- Ensure all facts match the SCHEME DATA exactly. Never truncate text with '...'."
                )
                scheme_data_json = json.dumps({
                    "title": title,
                    "issuing_body": ministry,
                    "state": state,
                    "category": category,
                    "description": description,
                    "benefits": benefits,
                    "eligibility": eligibility,
                    "documents": docs_lines,
                    "application_steps": step_lines,
                    "application_url": portal
                }, ensure_ascii=False)
                prompt = (
                    f"Citizen Query: \"{query or f'Explain {title}'}\"\n\n"
                    f"SCHEME DATA:\n{scheme_data_json}\n\n"
                    f"Explain this scheme completely in {target_lang}, covering overview, financial benefits, eligibility criteria, required documents, step-by-step application process, official portal, and anti-fraud advisory."
                )
                gen_reply = self._generate_content(sys_inst, prompt, json_mode=False)
                if gen_reply and len(gen_reply.strip()) > 100:
                    return gen_reply
            except Exception as e:
                print(f"[INFO] Gemini scheme explanation notice: {e}")

        # Authoritative structured fallback
        parts = [
            f"### 🏛️ **{title}**",
            f"*{ministry} • {state} • {category}*\n",
        ]
        if description:
            parts.extend([
                "#### 🎯 **Overview & Objective**",
                f"{description}\n"
            ])
        parts.extend([
            "#### 💰 **Key Financial Benefits & Assistance**",
            f"{benefits}\n",
            "#### 📋 **Eligibility Criteria**",
            f"• **State / Coverage:** {state}",
            f"• **Category:** {category}",
            f"• **Rules & Conditions:** {eligibility}\n",
            "#### 📁 **Required Documents Checklist**",
            "\n".join(docs_lines) + "\n",
            "#### 🚀 **Step-by-Step Application Process**",
            "\n".join(step_lines) + "\n",
            f"🔗 **Official Application Portal:** [{portal}]({portal})\n",
            "💡 **Citizen Advisory:** Applying is **100% free of charge**. Never pay unauthorized agents, share OTPs, or trust unverified links."
        ])
        return "\n".join(parts)

    def generate_scheme_qa_response(
        self,
        scheme: Dict[str, Any],
        user_query: str,
        user_profile: Dict[str, Any],
        language: str = "en",
    ) -> str:
        """
        Answers specific follow-up conversational questions about a scheme
        (e.g., "how to apply?", "can everyone apply?", "any age criteria?", "my age is 15 is this scheme applicable for me?", "is this free?")
        grounded firmly in the scheme's verified data and evaluated against the citizen's profile.
        """
        title = scheme.get("title") or scheme.get("name") or "Government Scheme"
        ministry = scheme.get("ministry") or scheme.get("issuing_body") or "Government of India"
        state = scheme.get("state") or "All India"
        category = scheme.get("category") or "Social Welfare"
        benefits = scheme.get("benefits") or "Direct welfare financial benefit as per official rules."
        eligibility = scheme.get("eligibility_summary") or "Open to eligible citizens meeting prescribed residency and income criteria."
        docs = scheme.get("documents_required") or "Aadhaar Card, Bank Passbook, Identity Proof."
        portal = scheme.get("application_url") or "https://www.india.gov.in"
        
        min_age = scheme.get("min_age", 0)
        max_age = scheme.get("max_age", 120)
        income_limit = scheme.get("income_limit")

        user_age = user_profile.get("age")
        user_state = user_profile.get("state")
        user_income = user_profile.get("annual_income")

        target_lang = "Hindi" if language == "hi" else "English"
        q_lower = user_query.lower()

        # Check for Step-by-Step Application Request
        is_apply_query = any(w in q_lower for w in [
            "how to apply", "application steps", "apply steps", "exact steps", "portal steps",
            "step by step", "where to apply", "how do i apply", "how can i apply", "apply online",
            "apply offline", "online form", "registration steps", "kaise apply", "kaise aavedan", "aavedan kaise"
        ])
        if is_apply_query:
            return self.generate_screen_by_screen_application_guide(scheme, user_query=user_query, language=language)

        # Check for Deadline & Expired Scheme Request
        is_deadline_query = any(w in q_lower for w in [
            "deadline", "last date", "expired", "expiry", "by when", "validity",
            "last date to apply", "closing date", "end date", "kab tak", "khatam", "valid till"
        ])
        if is_deadline_query:
            return self.generate_scheme_deadline_info(scheme, language=language)

        # Check for Documents Checklist Request
        is_doc_query = any(w in q_lower for w in [
            "document", "documents", "paper", "papers", "certificate", "certificates", "doc", "docs", "kya document", "kaunse document"
        ])
        if is_doc_query:
            docs_raw = scheme.get("documents_required_list") or scheme.get("documents_required")
            docs_lines = []
            if isinstance(docs_raw, list) and docs_raw:
                docs_lines = [f"• {d}" for d in docs_raw]
            elif isinstance(docs_raw, str) and docs_raw.strip():
                split_docs = re.split(r"[\n,;]+", docs_raw)
                clean_split = [d.strip() for d in split_docs if len(d.strip()) > 3]
                docs_lines = [f"• {d}" for d in clean_split] if clean_split else [f"• {docs_raw.strip()}"]
            else:
                docs_lines = [
                    "• Identity Proof (Aadhaar Card / Voter ID)",
                    "• Residence / Domicile Certificate",
                    "• Aadhaar-seeded Bank Passbook (showing IFSC and Account number)",
                    "• Income / Caste Certificate (if applicable)"
                ]
            lines = [
                f"### 📁 **Required Documents Checklist: {title}**\n",
                f"Please keep the following documents scanned and ready before applying:\n",
                "\n".join(docs_lines) + "\n",
                f"🔗 **Official Application Portal:** [{portal}]({portal})",
                f"💡 *Applying is 100% free of cost. Never submit originals to third-party agents.*"
            ]
            return "\n".join(lines)

        # 1. Try Gemini Grounded Synthesis if available
        if self._client or self.settings.gemini_api_key:
            try:
                sys_inst = (
                    f"{NAVI_SCHEME_SYSTEM_PROMPT}\n\n"
                    f"TASK: Answer the citizen's specific question regarding the scheme '{title}'.\n"
                    f"- Respond in {target_lang}.\n"
                    f"- Give a direct, definitive answer to their question in the first sentence.\n"
                    f"- If the user specifies their age ({user_age} yrs) or profile, explicitly evaluate whether they meet the scheme's age range ({min_age} to {max_age} yrs) or income limit.\n"
                    f"- If they are underage/overage, clearly state that they do NOT currently qualify and explain why.\n"
                    f"- If asking about age criteria, clearly state the minimum age ({min_age} yrs) and maximum age ({max_age} yrs).\n"
                    f"- If the citizen mentioned their state/city (e.g. Maharashtra, Nagpur), explain how this scheme applies or integrates in their state.\n"
                    f"- Include the official application link and remind them that government schemes are 100% free.\n"
                    f"- Do not truncate with '...'."
                )
                scheme_data = {
                    "scheme_name": title,
                    "issuing_body": ministry,
                    "coverage_state": state,
                    "category": category,
                    "min_age": min_age,
                    "max_age": max_age,
                    "income_limit": income_limit,
                    "key_benefits": benefits,
                    "eligibility_rules": eligibility,
                    "documents_required": docs,
                    "official_portal": portal,
                    "user_profile": user_profile
                }
                user_prompt = (
                    f"Citizen Question: \"{user_query}\"\n\n"
                    f"SCHEME RECORD:\n{json.dumps(scheme_data, ensure_ascii=False)}\n\n"
                    f"Please answer the citizen's question accurately in {target_lang}."
                )
                gen_reply = self._generate_content(sys_inst, user_prompt, json_mode=False)
                if gen_reply and len(gen_reply.strip()) > 80:
                    return gen_reply
            except Exception as e:
                print(f"[INFO] Gemini Scheme Q&A notice: {e}")

        # 2. Structured Grounded Fallback
        ans_lines = [f"### 📋 **{title} — Eligibility & Guidelines**\n"]

        # Case A: Personal eligibility check with age evaluation
        is_personal_check = any(w in q_lower for w in ["applicable for me", "eligible for me", "am i eligible", "can i apply", "applicable to me", "qualify"])
        has_age_mention = user_age is not None

        if is_personal_check and has_age_mention:
            if user_age < min_age:
                ans_lines.append(f"❌ **Not Currently Eligible for {title} (Age Requirement Not Met)**\n")
                ans_lines.append(f"• **Your Age:** {user_age} years")
                ans_lines.append(f"• **Required Age Criteria for {title}:** **{min_age} to {max_age} years**")
                ans_lines.append(f"• **Assessment:** You are currently **{user_age} years old**, which is below the minimum required entry age of **{min_age} years** for {title}. You will become eligible to apply once you reach {min_age} years of age.\n")
                ans_lines.append(f"💡 *Since you are {user_age} years old, you may explore student scholarships, pre-matric/post-matric education grants, or youth development schemes.*")
            elif user_age > max_age:
                ans_lines.append(f"❌ **Not Eligible for {title} (Age Exceeded)**\n")
                ans_lines.append(f"• **Your Age:** {user_age} years")
                ans_lines.append(f"• **Required Age Criteria for {title}:** **{min_age} to {max_age} years**")
                ans_lines.append(f"• **Assessment:** {title} is strictly intended for citizens between **{min_age} and {max_age} years of age**.")
            else:
                ans_lines.append(f"✅ **Age Requirement Met for {title}**\n")
                ans_lines.append(f"• **Your Age:** {user_age} years (Within the required {min_age} to {max_age} years bracket)")
                ans_lines.append(f"• **Eligibility Rules:** {clean_bureaucratic_text(eligibility)}")
        elif any(w in q_lower for w in ["age criteria", "age limit", "what age", "minimum age", "maximum age", "age required"]):
            ans_lines.append(f"**What are the age criteria for {title}?**\n")
            ans_lines.append(f"• **Minimum Entry Age:** **{min_age} years**")
            ans_lines.append(f"• **Maximum Age:** **{max_age} years**")
            ans_lines.append(f"• **Eligibility Summary:** {clean_bureaucratic_text(eligibility)}")
            if user_age is not None:
                if user_age < min_age:
                    ans_lines.append(f"• **Your Profile ({user_age} yrs):** Below minimum age of {min_age} yrs.")
                elif user_age > max_age:
                    ans_lines.append(f"• **Your Profile ({user_age} yrs):** Above maximum age of {max_age} yrs.")
                else:
                    ans_lines.append(f"• **Your Profile ({user_age} yrs):** ✅ Meets age criteria.")
            ans_lines.append("")
        elif any(w in q_lower for w in ["everyone", "anyone", "who can", "who is", "who all", "sab log", "sabko", "kisko"]):
            ans_lines.append(f"**Is everyone eligible to apply?**\n")
            ans_lines.append(f"No, **{title}** is intended for specific eligible citizen categories:")
            if "ayushman" in title.lower() or "jan arogya" in title.lower() or "pm-jay" in title.lower():
                ans_lines.append(f"• **Senior Citizens (70+ years):** **Yes, 100% eligible!** All individuals aged 70 and above can apply for ₹5 Lakh health cover under the newly launched *Ayushman Vay Vandana Card* regardless of family income.")
                ans_lines.append(f"• **Low-Income Families:** Families listed in SECC 2011 database or holding valid BPL / Priority Ration Cards (NFSA).")
                ans_lines.append(f"• **Who is NOT eligible:** Higher-income individuals, government employees covered by CGHS/ECHS/ESIC, or taxable households below age 70 without ration cards.")
            else:
                ans_lines.append(f"• **Target Beneficiaries:** {clean_bureaucratic_text(eligibility)}")
                ans_lines.append(f"• **Age Limits:** {min_age} to {max_age} years")
            ans_lines.append("")
        elif any(w in q_lower for w in ["free", "cost", "charge", "paisa", "fees", "fee"]):
            ans_lines.append(f"**Is application free?**\n")
            ans_lines.append(f"• **Yes, applying for {title} is 100% FREE.**")
            ans_lines.append(f"• Never pay any fees to unauthorized agents or middlemen. Always apply directly on official government channels.")
            ans_lines.append("")
        else:
            ans_lines.append(f"• **Official Eligibility Rules:** {clean_bureaucratic_text(eligibility)}")
            ans_lines.append(f"• **Age Requirement:** {min_age} to {max_age} years")
            ans_lines.append(f"• **Key Benefit:** {clean_bureaucratic_text(benefits)}")
            ans_lines.append("")

        if user_state and user_state.lower() != "all india":
            ans_lines.append(f"📍 **State Coverage:** Applicable in **{user_state}** ({state} coverage).")

        ans_lines.append(f"\n🔗 **Official Application Portal:** [{portal}]({portal})")
        ans_lines.append(f"💡 *Applying is 100% free of charge.*")

        return "\n".join(ans_lines)

    def generate_grounded_response(
        self,
        query: str,
        extracted: Dict[str, Any],
        schemes: List[Dict[str, Any]],
        total_found: int,
        language: str = "en",
    ) -> str:
        """
        Conversational grounded response generator with Gemini AI and strict fallback.
        """
        caste = extracted.get("caste")
        state = extracted.get("state")
        age = extracted.get("age")
        category = extracted.get("category")
        is_proxy = extracted.get("is_proxy_profile", False)

        address_term = "they" if is_proxy else "you"

        # 1. Try Grounded Generation via Gemini if available
        if (self._client or self.settings.gemini_api_key) and schemes:
            try:
                schemes_context = []
                for idx, s in enumerate(schemes[:20], 1):
                    reasons = "; ".join(s.get("match_reasons") or [])
                    sch_st = s.get("state") or "All India"
                    st_badge = f"State: {sch_st}" if sch_st != "All India" else "Central Scheme (All India)"
                    schemes_context.append(
                        f"Scheme {idx}: {s.get('title')}\n"
                        f"Jurisdiction: {st_badge}\n"
                        f"Category: {s.get('category')}\n"
                        f"Key Benefit: {s.get('benefits')}\n"
                        f"Eligibility: {s.get('eligibility_summary')}\n"
                        f"Portal: {s.get('application_url')}\n"
                    )
                context_str = "\n---\n".join(schemes_context)

                target_lang = "Hindi" if language == "hi" else "English"
                system_instruction = (
                    f"{NAVI_SCHEME_SYSTEM_PROMPT}\n\n"
                    f"ADDITIONAL INSTRUCTIONS FOR MULTI-SCHEME LISTING:\n"
                    f"- Respond in {target_lang}.\n"
                    f"- Show the schemes as a clean, easy-to-read numbered bullet list (1, 2, 3...).\n"
                    f"- For each scheme, show: **[Scheme Name]** *(Jurisdiction • Category)* followed by 1 concise bullet for Benefit.\n"
                    f"- Present State schemes first, then Central schemes.\n"
                    f"- End the response with:\n"
                    f"  '---\n💬 **Which scheme would you like to explore?** Reply with the number or scheme name (e.g. *Explain 1* or *Tell me more about [Scheme Name]*), or tap any option below to view full benefits, documents checklist, and official portal apply steps.'\n"
                    f"- Do not truncate."
                )

                user_prompt = (
                    f"User Query: \"{query}\"\n"
                    f"Profile Context: State={state or 'All India'}, Age={age or 'Any'}, Category={category or 'All'}, Caste={caste or 'All'}\n\n"
                    f"MATCHED SCHEMES ({len(schemes[:15])} Total):\n{context_str}\n\n"
                    f"List all {len(schemes[:15])} schemes in {target_lang} with clean numbered bullets and invite the citizen to explore."
                )
                generated = self._generate_content(system_instruction, user_prompt, json_mode=False)
                if generated:
                    return generated
            except Exception as e:
                print(f"[INFO] Gemini conversational summary fallback: {e}")

        # 2. Local Grounded Fallback & Multi-Scheme Numbered Title Listing
        if total_found > 0 and len(schemes) > 0:
            count_shown = min(len(schemes), 15)
            location_label = f" for {state}" if state and state.lower() != "all india" else ""
            lines = [
                f"✅ **Found {total_found} verified government scheme(s){location_label}** matching your profile / query.\n",
                f"Here are the top schemes (state schemes prioritized first):\n"
            ]
            for idx, s in enumerate(schemes[:count_shown], 1):
                title = s.get("title") or s.get("name") or "Scheme"
                raw_benefits = s.get("benefits", "")
                benefits_clean = clean_bureaucratic_text(raw_benefits)
                if len(benefits_clean) > 130:
                    benefits_clean = benefits_clean[:130] + "…"
                sch_state = s.get("state") or "Central"
                state_badge = f"🏛️ {sch_state}" if sch_state != "All India" else "🇮🇳 Central"
                category_badge = s.get("category") or "Welfare"

                lines.append(f"{idx}. **{title}** *({state_badge} • {category_badge})*")
                if benefits_clean:
                    lines.append(f"   • *Benefit:* {benefits_clean}")
                lines.append("")

            first_title = schemes[0].get('title', 'this scheme') if schemes else 'this scheme'
            short_first_title = first_title.split('(')[0].strip()[:30]

            lines.append("---")
            lines.append("💬 **Which scheme would you like to explore?**")
            lines.append(f"Reply with the number or scheme name (e.g., ***'Explain 1'*** or ***'Tell me more about {short_first_title}'***), or click any suggestion pill below to view full benefits, documents checklist, and official portal apply steps.")

            if caste in ["SC", "ST", "OBC", "EWS"]:
                lines.append(f"\n💡 *Tip: Keep your valid {caste} certificate and income certificate handy for verification.*")

            return "\n".join(lines)
        else:
            return (
                "🔍 I searched the verified government catalog, but no exact schemes matched yet.\n\n"
                "💡 **Suggested next steps to unlock matches:**\n"
                "• Tell me your **State** or **District** to unlock local state schemes.\n"
                "• Tell me if you are a **Student**, **Farmer**, **Woman**, **Senior Citizen**, or **Small Business Owner**.\n"
                "• Mention your approximate **annual household income bracket**."
            )

    # =========================================================================
    # EXPLICIT INTENT ROUTING STATE MACHINE ARCHITECTURE
    # =========================================================================
    #
    # The routing pipeline executes in 10 explicit deterministic phases:
    # 1. INTENT_REFUSAL: Bribes / forgery / fake certificates -> Refusal.
    # 2. INTENT_SCAM_WARNING: Inquiries about commission / agents -> Fraud Warning.
    # 3. INTENT_LOAN_CALCULATOR: EMI calculation / principal / interest -> Calculator.
    # 4. INTENT_GREETING_OR_INTRO: Greetings or platform overview.
    # 5. INTENT_EXPLAIN_NEW_SCHEME: "Explain [Scheme Name]" -> 360-degree card explanation.
    # 6. INTENT_ACTIVE_SCHEME_FOLLOWUP: Question about active scheme -> Evaluates profile & scheme rules.
    # 7. INTENT_LOCATION_ANSWER: Single-word city/state -> Resolves to State & queries state schemes.
    # 8. INTENT_TOPIC_SEARCH: Explicit keyword/category search -> Grounded query matching.
    # 9. INTENT_VAGUE_DISCOVERY: Generic unconstrained query without state -> Clarification Gate.
    # 10. INTENT_RELEVANCE_GUARD: Relevance filter preventing unrelated catalog dumps.
    # =========================================================================

    def process_conversational_turn(
        self,
        session_id: str,
        message: str,
        repository: Any,
        user_id: Optional[str] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Executes the explicit intent routing state machine pipeline.
        """
        msg_clean = message.strip()
        msg_lower = msg_clean.lower()

        # 1. Load session & accumulated profile
        session = repository.get_or_create_session(session_id, user_id=user_id)
        current_profile = repository.get_session_profile(session_id)

        # 2. Extract intent and entities from current message
        extracted_intent = self.extract_intent_and_entities(msg_clean)
        special_case = extracted_intent.get("special_case")

        # 3. Phase 1-4: Safety, Loan Calculator & Greetings
        rate_reply_match = re.search(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(?:%|\bpercent\b|\binterest\b)?\s*$", msg_lower) or re.search(r"\b(?:rate|interest)\s*(?:is|of)?\s*([0-9]+(?:\.[0-9]+)?)\s*%?", msg_lower)
        if rate_reply_match and not extracted_intent.get("principal"):
            recent_msgs = repository.get_session_messages(session_id, limit=4)
            for m in reversed(recent_msgs):
                prev_text = m.get("message", "")
                if "Loan Details Received" in prev_text or "₹" in prev_text:
                    p_match = re.search(r"₹\s*([0-9,]+)", prev_text)
                    t_match = re.search(r"([0-9]+)\s*months", prev_text, re.IGNORECASE)
                    if p_match and t_match:
                        try:
                            p_val = float(p_match.group(1).replace(",", ""))
                            t_val = int(t_match.group(1))
                            r_val = float(rate_reply_match.group(1))
                            calc = calculate_loan_emi(p_val, annual_rate_pct=r_val, tenure_months=t_val)
                            reply = (
                                f"📊 **Government Scheme Loan & EMI Breakdown** (Rule 4)\n\n"
                                f"• **Loan Amount (Principal):** ₹{calc['principal']:,.0f}\n"
                                f"• **Interest Rate:** {calc['annual_rate_pct']}% p.a.\n"
                                f"• **Tenure:** {calc['tenure_months']} Months ({calc['tenure_years']} Years)\n"
                                f"• **Estimated Monthly EMI:** **₹{calc['monthly_emi']:,.2f}**\n"
                                f"• **Total Interest Payable:** ₹{calc['total_interest']:,.2f}\n"
                                f"• **Total Repayment Amount:** ₹{calc['total_payable']:,.2f}\n\n"
                                f"💡 *Note: Subsidized government credit schemes (like PM SVANidhi, PMEGP, or Mudra) may also provide capital grants or interest rebates upon timely repayment.*"
                            )
                            action_tag = "loan_calc"
                            repository.save_chat_message(session_id, "user", msg_clean, action_tag)
                            repository.save_chat_message(session_id, "assistant", reply, action_tag)
                            return {
                                "session_id": session_id,
                                "reply": reply,
                                "extracted_state": current_profile.get("state"),
                                "extracted_age": current_profile.get("age"),
                                "extracted_category": current_profile.get("category"),
                                "extracted_caste": current_profile.get("caste"),
                                "schemes": [],
                                "total_found": 0,
                                "action_taken": action_tag,
                                "suggestions": ["₹50,000 for 2 years", "₹2 Lakh for 3 years", "🌾 Explore schemes in my state"]
                            }
                        except Exception:
                            pass

        if special_case in [
            "fraud_refusal", "scam_warning", "greeting_or_offtopic",
            "navi_scheme_intro", "loan_calculator", "loan_rate_needed", "loan_missing_details"
        ]:
            action_tag = "refuse" if special_case == "fraud_refusal" else (
                "scam_warning" if special_case == "scam_warning" else (
                    "loan_calc" if "loan" in special_case else "greeting"
                )
            )

            if special_case == "loan_rate_needed":
                active_sch = self._get_active_scheme_from_session(session_id, repository)
                scheme_rate = None
                if active_sch:
                    sch_text = f"{active_sch.get('benefits', '')} {active_sch.get('description', '')} {active_sch.get('title', '')}"
                    rm = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:interest|subsidy|p\.?a\.?|per annum)", sch_text, re.IGNORECASE)
                    if rm:
                        try:
                            scheme_rate = float(rm.group(1))
                        except ValueError:
                            pass

                p = extracted_intent.get("principal")
                t = extracted_intent.get("tenure_months")

                if scheme_rate and p and t:
                    calc = calculate_loan_emi(p, annual_rate_pct=scheme_rate, tenure_months=t)
                    reply = (
                        f"📊 **Government Scheme Loan & EMI Breakdown** (Rule 4)\n\n"
                        f"• **Scheme:** {active_sch.get('title')}\n"
                        f"• **Loan Amount (Principal):** ₹{calc['principal']:,.0f}\n"
                        f"• **Scheme Subsidized Interest Rate:** {calc['annual_rate_pct']}% p.a.\n"
                        f"• **Tenure:** {calc['tenure_months']} Months ({calc['tenure_years']} Years)\n"
                        f"• **Estimated Monthly EMI:** **₹{calc['monthly_emi']:,.2f}**\n"
                        f"• **Total Interest Payable:** ₹{calc['total_interest']:,.2f}\n"
                        f"• **Total Repayment Amount:** ₹{calc['total_payable']:,.2f}\n\n"
                        f"💡 *Interest rate cited directly from {active_sch.get('title')} official guidelines.*"
                    )
                else:
                    reply = extracted_intent["message"]
            else:
                reply = extracted_intent["message"]

            repository.save_chat_message(session_id, "user", msg_clean, action_tag)
            repository.save_chat_message(session_id, "assistant", reply, action_tag)

            return {
                "session_id": session_id,
                "reply": reply,
                "extracted_state": current_profile.get("state"),
                "extracted_age": current_profile.get("age"),
                "extracted_category": current_profile.get("category"),
                "extracted_caste": current_profile.get("caste"),
                "schemes": [],
                "total_found": 0,
                "action_taken": action_tag,
                "suggestions": ["🌾 Schemes for Farmers", "🎓 Student Scholarships", "👩 Women & Child Welfare", "🏥 Health & Ayushman Bharat"]
            }

        # 4. Phase 5: Check for explicit "Explain [Scheme]" or Numbered Scheme Selection (e.g. "1", "ten", "#1", "explain 1", "tell me more about #2", "first one", "scheme 10")
        WORD_TO_NUM = {
            "one": 1, "first": 1, "1st": 1,
            "two": 2, "second": 2, "2nd": 2,
            "three": 3, "third": 3, "3rd": 3,
            "four": 4, "fourth": 4, "4th": 4,
            "five": 5, "fifth": 5, "5th": 5,
            "six": 6, "sixth": 6, "6th": 6,
            "seven": 7, "seventh": 7, "7th": 7,
            "eight": 8, "eighth": 8, "8th": 8,
            "nine": 9, "ninth": 9, "9th": 9,
            "ten": 10, "tenth": 10, "10th": 10,
            "eleven": 11, "eleventh": 11, "11th": 11,
            "twelve": 12, "twelfth": 12, "12th": 12,
            "thirteen": 13, "thirteenth": 13, "13th": 13,
            "fourteen": 14, "fourteenth": 14, "14th": 14,
            "fifteen": 15, "fifteenth": 15, "15th": 15,
            "sixteen": 16, "sixteenth": 16, "16th": 16,
            "seventeen": 17, "seventeenth": 17, "17th": 17,
            "eighteen": 18, "eighteenth": 18, "18th": 18,
            "nineteen": 19, "nineteenth": 19, "19th": 19,
            "twenty": 20, "twentieth": 20, "20th": 20,
        }
        
        index_num = None
        num_patterns = r"^(?:explain\s+|tell\s+me\s+about\s+|tell\s+me\s+more\s+about\s+|details\s+of\s+|about\s+|scheme\s+|option\s+|choice\s+)?#?\s*([1-9][0-9]?)\s*$"
        nm = re.search(num_patterns, msg_clean, re.IGNORECASE)
        if nm:
            index_num = int(nm.group(1))
        else:
            word_pattern = r"^(?:explain\s+|tell\s+me\s+about\s+|tell\s+me\s+more\s+about\s+|details\s+of\s+|about\s+|scheme\s+|option\s+|choice\s+)?(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th)(?:\s+one|\s+scheme)?\s*$"
            wm = re.search(word_pattern, msg_clean, re.IGNORECASE)
            if wm:
                w_str = wm.group(1).lower()
                index_num = WORD_TO_NUM.get(w_str)

        direct_scheme = None
        if index_num is not None:
            recent_msgs = repository.get_session_messages(session_id, limit=6, desc=True)
            for m in recent_msgs:
                meta_raw = m.get("metadata_json") or "{}"
                try:
                    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
                    matched_ids = meta.get("matched_ids") or []
                    if matched_ids and 1 <= index_num <= len(matched_ids):
                        target_id = matched_ids[index_num - 1]
                        direct_scheme = repository.get_scheme_by_id_or_slug(target_id)
                        if direct_scheme:
                            break
                except Exception:
                    pass

        if not direct_scheme:
            is_broad_catalog_query = bool(re.search(
                r"\b(?:schemes|scholarships|subsidies|pensions|yojanas|benefits)\s+(?:in|for|of)\b|\b(?:tell\s+me|find|show|give|list|get)\s+(?:me\s+)?(?:all\s+)?(?:schemes|scholarships|subsidies|pensions)\b",
                msg_clean,
                re.IGNORECASE
            ))
            is_explain_query = bool(re.search(
                r"^(?:explore\s*:\s*|explore\s+|explain\s*:\s*|explain\s+|what\s+is\s+|tell\s+me\s+about\s+|tell\s+me\s+more\s+about\s+|details\s+of\s+|about\s+|how\s+to\s+apply\s+for\s+|scheme\s*:\s*)",
                msg_clean,
                re.IGNORECASE
            ))
            if not is_broad_catalog_query:
                found_scheme = repository.find_scheme_by_title_or_query(msg_clean)
                if found_scheme:
                    is_exact_title = bool(found_scheme.get("title", "").strip().lower() == msg_clean.lower())
                    if is_explain_query or is_exact_title:
                        direct_scheme = found_scheme

        if direct_scheme:
            reply = self.generate_scheme_explanation(direct_scheme, query=msg_clean, language=language)
            action_tag = "scheme_explained"
            repository.save_chat_message(session_id, "user", msg_clean, action_tag)
            repository.save_chat_message(session_id, "assistant", reply, action_tag, {"scheme_id": direct_scheme["id"]})

            sch_state = direct_scheme.get("state") or "All India"
            return {
                "session_id": session_id,
                "reply": reply,
                "extracted_state": direct_scheme.get("state") or current_profile.get("state"),
                "extracted_age": current_profile.get("age"),
                "extracted_category": direct_scheme.get("category"),
                "extracted_caste": current_profile.get("caste"),
                "schemes": [direct_scheme],
                "total_found": 1,
                "action_taken": action_tag,
                "suggestions": [
                    f"📝 Required documents checklist",
                    f"🚀 How to apply step-by-step",
                    f"🎯 Check my eligibility",
                    f"More schemes in {sch_state}"
                ]
            }

        # 5. Accumulate profile facts
        merged_profile = {
            "state": extracted_intent.get("state") or current_profile.get("state"),
            "age": extracted_intent.get("age") if extracted_intent.get("age") is not None else current_profile.get("age"),
            "gender": extracted_intent.get("gender") if extracted_intent.get("gender") and extracted_intent.get("gender") != "All" else current_profile.get("gender", "All"),
            "occupation": extracted_intent.get("occupation") or current_profile.get("occupation"),
            "category": extracted_intent.get("category") or current_profile.get("category"),
            "caste": extracted_intent.get("caste") or current_profile.get("caste"),
            "annual_income": extracted_intent.get("annual_income") if extracted_intent.get("annual_income") is not None else current_profile.get("annual_income"),
            "is_proxy_profile": extracted_intent.get("is_proxy_profile", False) or bool(current_profile.get("is_proxy_profile")),
        }
        repository.update_session_profile(session_id, merged_profile)

        # 6. Phase 6: Check for Active Scheme Multi-Turn Follow-Up (CHECKED FIRST BEFORE GENERIC SEARCH)
        active_sch = self._get_active_scheme_from_session(session_id, repository)
        if active_sch:
            # Check if this is a follow-up question regarding active scheme
            is_referential_followup = bool(
                "?" in msg_clean
                or any(w in msg_lower for w in [
                    "can", "is", "how", "what", "who", "why", "where", "eligible", "apply", "document",
                    "free", "cost", "income", "age", "hospital", "card", "everyone", "anyone", "sab", "kisko",
                    "kya", "kaise", "doc", "step", "criteria", "limit", "senior", "70", "qualify", "applicable"
                ])
            )

            # Or if user is stating a location response while in scheme context
            is_pure_location_reply = bool(
                extracted_intent.get("state")
                and len(msg_clean.split()) <= 2
                and not any(w in msg_lower for w in ["scheme", "scholarship", "yojana", "pension", "subsidy", "find"])
            )

            if is_referential_followup or is_pure_location_reply:
                user_q = f"How does this scheme apply in {merged_profile['state']}?" if is_pure_location_reply else msg_clean
                reply = self.generate_scheme_qa_response(
                    scheme=active_sch,
                    user_query=user_q,
                    user_profile=merged_profile,
                    language=language
                )
                action_tag = "scheme_qa"
                repository.save_chat_message(session_id, "user", msg_clean, action_tag)
                repository.save_chat_message(session_id, "assistant", reply, action_tag, {"scheme_id": active_sch["id"]})

                return {
                    "session_id": session_id,
                    "reply": reply,
                    "extracted_state": merged_profile.get("state") or active_sch.get("state"),
                    "extracted_age": merged_profile.get("age"),
                    "extracted_category": active_sch.get("category"),
                    "extracted_caste": merged_profile.get("caste"),
                    "schemes": [active_sch],
                    "total_found": 1,
                    "action_taken": action_tag,
                    "suggestions": [
                        "🎯 Check my eligibility",
                        "📝 Required documents checklist",
                        "How to apply step-by-step",
                        "🏛️ Explore other schemes in my state"
                    ]
                }

        # 7. Phase 7: General Single-Word Location Answer Resolution (e.g. "nagpur", "lucknow", "patna", "hyderabad")
        is_bare_location = bool(
            extracted_intent.get("state")
            and len(msg_clean.split()) <= 2
            and not any(w in msg_lower for w in ["scheme", "scholarship", "yojana", "pension", "subsidy", "find", "how", "what", "age", "apply"])
        )
        if is_bare_location:
            resolved_state = merged_profile.get("state")
            loc_intent = parse_query_intent(msg_clean, current_profile=merged_profile)
            loc_profile = MatchProfile(
                state=resolved_state,
                age=merged_profile.get("age"),
                gender=merged_profile.get("gender", "All"),
                caste=merged_profile.get("caste"),
                occupation=merged_profile.get("occupation"),
                category=merged_profile.get("category"),
                annual_income=merged_profile.get("annual_income"),
            )

            candidate_schemes, loc_total = repository.get_schemes(
                state=resolved_state,
                status="active",
                limit=None
            )
            schemes, total_ranked = rank_and_filter_schemes(candidate_schemes, loc_profile, loc_intent, limit=15)
            final_loc_total = loc_total or total_ranked

            reply = self.generate_grounded_response(
                query=f"Verified government schemes in {resolved_state}",
                extracted=merged_profile,
                schemes=schemes,
                total_found=final_loc_total,
                language=language,
            )
            action_tag = "location_resolved"
            repository.save_chat_message(session_id, "user", msg_clean, action_tag)
            repository.save_chat_message(session_id, "assistant", reply, action_tag, {"total_found": final_loc_total, "matched_ids": [s["id"] for s in schemes]})

            return {
                "session_id": session_id,
                "reply": reply,
                "extracted_state": resolved_state,
                "extracted_age": merged_profile.get("age"),
                "extracted_category": merged_profile.get("category"),
                "extracted_caste": merged_profile.get("caste"),
                "schemes": schemes,
                "total_found": final_loc_total,
                "action_taken": action_tag,
                "suggestions": [
                    f"🎓 Student Scholarships in {resolved_state}",
                    f"🌾 Farmer Schemes in {resolved_state}",
                    f"👩 Women Welfare in {resolved_state}",
                    "🏥 Ayushman Health Card"
                ]
            }

        # 8. Phase 8: Check for Unknown City / Location reply to Clarification Gate
        recent_history = repository.get_session_messages(session_id, limit=3)
        last_assistant_msg = next((m.get("message", "") for m in reversed(recent_history) if m.get("sender") == "assistant"), "")
        is_answering_clarification = "Which state or union territory" in last_assistant_msg or "tell me your state" in last_assistant_msg.lower()

        state = merged_profile.get("state")
        if is_answering_clarification and not state and len(msg_clean.split()) <= 2:
            clarify_reply = (
                f"📍 I could not identify the state or union territory for '**{msg_clean}**'. "
                f"Please specify your state (e.g. *Maharashtra, Uttar Pradesh, Bihar, Karnataka, Tamil Nadu, Delhi*, or *All India*)."
            )
            action_tag = "clarify_retry"
            repository.save_chat_message(session_id, "user", msg_clean, action_tag)
            repository.save_chat_message(session_id, "assistant", clarify_reply, action_tag)

            return {
                "session_id": session_id,
                "reply": clarify_reply,
                "extracted_state": None,
                "extracted_age": merged_profile.get("age"),
                "extracted_category": merged_profile.get("category"),
                "extracted_caste": merged_profile.get("caste"),
                "schemes": [],
                "total_found": 0,
                "action_taken": action_tag,
                "suggestions": ["Maharashtra", "Uttar Pradesh", "Karnataka", "All India (Central)"]
            }

        # 9. Phase 9: Vague Unconstrained Discovery Prompt Gate
        match_intent = parse_query_intent(msg_clean, current_profile=merged_profile)
        is_vague_discovery = bool(
            any(p in msg_lower for p in ["find schemes", "give me schemes", "what schemes", "show schemes", "search schemes", "available schemes", "schemes for me"])
            and not match_intent.is_targeted
            and not merged_profile.get("category")
            and not merged_profile.get("caste")
            and not merged_profile.get("occupation")
            and not match_intent.keywords
            and not match_intent.target_subject
        )
        if is_vague_discovery and not state:
            clarify_reply = (
                "📍 **Which state or union territory do you reside in?**\n\n"
                "Government schemes are distributed based on state residency or Central (All India) coverage. "
                "Please tell me your state (e.g. *Maharashtra, Uttar Pradesh, Bihar, Karnataka, Tamil Nadu, Delhi*, or *All India* for Central schemes)."
            )
            action_tag = "clarify"
            repository.save_chat_message(session_id, "user", msg_clean, action_tag)
            repository.save_chat_message(session_id, "assistant", clarify_reply, action_tag)

            return {
                "session_id": session_id,
                "reply": clarify_reply,
                "extracted_state": None,
                "extracted_age": merged_profile.get("age"),
                "extracted_category": merged_profile.get("category"),
                "extracted_caste": merged_profile.get("caste"),
                "schemes": [],
                "total_found": 0,
                "action_taken": action_tag,
                "suggestions": ["Maharashtra", "Uttar Pradesh", "Karnataka", "All India (Central)"]
            }

        # 10. Phase 10: Generalized Matching & Dynamic Scored Ranking
        match_profile = MatchProfile(
            state=merged_profile.get("state"),
            age=merged_profile.get("age"),
            gender=merged_profile.get("gender", "All"),
            caste=merged_profile.get("caste"),
            occupation=merged_profile.get("occupation"),
            category=merged_profile.get("category"),
            annual_income=merged_profile.get("annual_income"),
            is_proxy_profile=merged_profile.get("is_proxy_profile", False),
        )

        # Retrieve candidate schemes from database tailored to intent, keywords, and state
        search_query = match_intent.keywords[0] if match_intent.keywords else (msg_clean if len(msg_clean.split()) <= 4 else None)
        target_st = match_intent.target_state or merged_profile.get("state")
        
        candidate_schemes, candidate_total = repository.get_schemes(
            query=search_query,
            state=target_st if target_st and target_st.lower() not in ["all india", "all"] else None,
            category=match_intent.target_category or merged_profile.get("category"),
            status="active",
            limit=None
        )
        
        if len(candidate_schemes) < 20:
            broad_schemes, broad_total = repository.get_schemes(
                state=target_st if target_st and target_st.lower() not in ["all india", "all"] else None,
                category=match_intent.target_category or merged_profile.get("category"),
                status="active",
                limit=None
            )
            candidate_total = max(candidate_total, broad_total)
            existing_ids = {s["id"] for s in candidate_schemes}
            for bs in broad_schemes:
                if bs["id"] not in existing_ids:
                    candidate_schemes.append(bs)
                    existing_ids.add(bs["id"])

        schemes, total_ranked = rank_and_filter_schemes(candidate_schemes, match_profile, match_intent, limit=15)
        final_total_found = candidate_total or total_ranked

        # Relevance Guard: If user asked a specific query that yielded 0 matches, do not dump random state schemes!
        if total_ranked == 0 and candidate_total == 0:
            reply = (
                f"🔍 I searched the official gazette database, but could not find a verified scheme specifically matching '**{msg_clean}**'.\n\n"
                f"💡 **Suggested next steps:**\n"
                f"• Check the spelling or search by sector: *Scholarships, Pensions, Agriculture, Health, Housing, Women Welfare*.\n"
                f"• Explore schemes available in your state ({merged_profile.get('state') or 'All India'})."
            )
            action_tag = "no_match"
            schemes = []
            final_total_found = 0
        else:
            reply = self.generate_grounded_response(
                query=msg_clean,
                extracted=merged_profile,
                schemes=schemes,
                total_found=final_total_found,
                language=language,
            )
            action_tag = "matched"

        # Persist turn in message log
        repository.save_chat_message(session_id, "user", msg_clean, action_tag)
        repository.save_chat_message(
            session_id,
            "assistant",
            reply,
            action_tag,
            {"total_found": final_total_found, "matched_ids": [s["id"] for s in schemes]}
        )

        suggestions = []
        if schemes:
            for s in schemes[:3]:
                t = s.get("title") or s.get("name")
                if t:
                    short_t = t.split("(")[0].strip()
                    suggestions.append(f"Explore: {short_t[:30]}")
        
        caste = merged_profile.get("caste")
        age = merged_profile.get("age")
        category = merged_profile.get("category")
        if len(suggestions) < 4 and caste:
            suggestions.append(f"🎓 {caste} Scholarships")
        if len(suggestions) < 4 and not category:
            suggestions.append("🏥 Health (Ayushman Card)")
        if len(suggestions) < 4 and state:
            suggestions.append(f"More schemes in {state}")
        if len(suggestions) < 4:
            suggestions.append("🧮 Loan & Subsidy Calculator")

        return {
            "session_id": session_id,
            "reply": reply,
            "extracted_state": state,
            "extracted_age": age,
            "extracted_category": category,
            "extracted_caste": caste,
            "schemes": schemes,
            "total_found": final_total_found,
            "action_taken": action_tag,
            "suggestions": suggestions[:4]
        }

