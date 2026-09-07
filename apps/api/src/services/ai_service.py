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
        """Robust Gemini generative execution with direct REST and SDK fallback."""
        # 1. Direct REST API via standard library
        if self.settings.gemini_api_key:
            try:
                import urllib.request
                import socket
                socket.setdefaulttimeout(7.0)
                clean_model = self.model_name.replace("models/", "")
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
                    if text:
                        return text.strip()
            except Exception as e:
                print(f"[INFO] Gemini REST notice: {e}")

        # 2. Try google.genai SDK as fallback
        if self._client:
            try:
                config_args = {
                    "system_instruction": system_instruction,
                    "temperature": 0.2,
                    "max_output_tokens": self.settings.gemini_max_output_tokens,
                }
                if json_mode:
                    config_args["response_mime_type"] = "application/json"

                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(**config_args),
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                print(f"[INFO] Gemini SDK generation notice: {e}")

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

        # 6. Proxy profile detection ("filling for my father / mother / daughter")
        is_proxy = any(w in text_lower for w in ["for my father", "for my mother", "for my son", "for my daughter", "for my wife", "for my parents"])

        # 7. Extract entities
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
                "1. Visit the verified official government portal linked below.",
                "2. Register or log in using your Aadhaar or mobile number.",
                "3. Fill in the online citizen application form with verified profile details.",
                "4. Upload the required supporting documents in prescribed format.",
                "5. Submit the application and record your unique Application Acknowledgement / Reference ID."
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
        (e.g., "can everyone apply?", "any age criteria?", "my age is 15 is this scheme applicable for me?", "is this free?")
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
                for s in schemes[:3]:
                    reasons = "; ".join(s.get("match_reasons") or [])
                    missing = "; ".join(s.get("missing_requirements") or [])
                    schemes_context.append(
                        f"Scheme Name: {s.get('title')}\n"
                        f"State: {s.get('state')}\n"
                        f"Category: {s.get('category')}\n"
                        f"Key Benefits: {s.get('benefits')}\n"
                        f"Eligibility Rules: {s.get('eligibility_summary')}\n"
                        f"Match Reasons: {reasons or 'Matches profile constraints'}\n"
                        f"Missing/Pending Verification: {missing or 'None'}\n"
                        f"Official Application Portal: {s.get('application_url')}\n"
                    )
                context_str = "\n---\n".join(schemes_context)

                target_lang = "Hindi" if language == "hi" else "English"
                system_instruction = (
                    f"{NAVI_SCHEME_SYSTEM_PROMPT}\n\n"
                    f"ADDITIONAL INSTRUCTIONS:\n"
                    f"- Respond in {target_lang}.\n"
                    f"- Format clearly with headings, bold titles, and bullet points.\n"
                    f"- ONLY mention eligibility criteria and match reasons supported directly by SCHEME DATA.\n"
                    f"- Never claim a scheme is exclusively for SC, women, or students unless explicitly stated in that scheme's data.\n"
                    f"- Do not truncate with '...' — provide complete facts.\n"
                    f"- If filling for someone else, address them respectfully in third person."
                )

                user_prompt = (
                    f"User Query: \"{query}\"\n"
                    f"Profile Context: Caste={caste or 'Not specified'}, State={state or 'All India'}, Age={age or 'Any'}, Category={category or 'All'}\n\n"
                    f"SCHEME DATA:\n{context_str}\n\n"
                    f"Summarize what {address_term} qualify for and how to apply in {target_lang}."
                )
                generated = self._generate_content(system_instruction, user_prompt, json_mode=False)
                if generated:
                    return generated
            except Exception as e:
                print(f"[INFO] Gemini conversational summary fallback: {e}")

        # 2. Local Grounded Fallback (Formatted clearly without truncation)
        if total_found > 0 and len(schemes) > 0:
            count_shown = len(schemes)
            location_label = f" in {state}" if state and state.lower() != "all india" else ""
            lines = [
                f"✅ **Found {count_shown} verified government scheme(s){location_label}** matching your criteria:\n",
            ]
            for s in schemes[:count_shown]:
                title = s.get("title") or s.get("name") or "Scheme"
                raw_benefits = s.get("benefits", "")
                raw_eligibility = s.get("eligibility_summary", "")
                benefits_clean = clean_bureaucratic_text(raw_benefits)
                eligibility_clean = clean_bureaucratic_text(raw_eligibility)
                portal = s.get("application_url", "")
                match_reasons = s.get("match_reasons") or []
                missing_reqs = s.get("missing_requirements") or []
                match_status = s.get("match_status") or "eligible"

                lines.append(f"### 🏛️ {title}")
                if benefits_clean:
                    lines.append(f"• **Key Benefit:** {benefits_clean}")
                if eligibility_clean:
                    lines.append(f"• **Eligibility Criteria:** {eligibility_clean}")

                if match_reasons:
                    lines.append("• **Why this matches:**")
                    for r in match_reasons:
                        lines.append(f"  - {r}")

                if match_status == "potential_match" and missing_reqs:
                    lines.append(f"• ⚠️ **Potential Match — Please verify:** {'; '.join(missing_reqs)}")

                if portal:
                    lines.append(f"• **Official Application Portal:** [{portal}]({portal})")
                lines.append("")

            if caste in ["SC", "ST", "OBC", "EWS"]:
                lines.append(f"💡 *Tip: Ensure your valid {caste} certificate and income certificate are ready.*")

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

        # 4. Phase 5: Check for explicit "Explain [Scheme]" query
        is_explain_query = bool(re.search(r"^(?:explain\s+|what\s+is\s+|tell\s+me\s+about\s+|details\s+of\s+|about\s+)", msg_clean, re.IGNORECASE))
        direct_scheme = repository.find_scheme_by_title_or_query(msg_clean) if len(msg_clean.split()) >= 2 else None
        
        if direct_scheme and (is_explain_query or len(msg_clean.split()) >= 3):
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
                    "🎯 Check my eligibility for this scheme",
                    "📝 Required documents checklist",
                    "How to apply step-by-step",
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

            candidate_schemes, _ = repository.get_schemes(status="active", limit=200)
            schemes, total = rank_and_filter_schemes(candidate_schemes, loc_profile, loc_intent, limit=4)

            reply = self.generate_grounded_response(
                query=f"Verified government schemes in {resolved_state}",
                extracted=merged_profile,
                schemes=schemes,
                total_found=len(schemes),
                language=language,
            )
            action_tag = "location_resolved"
            repository.save_chat_message(session_id, "user", msg_clean, action_tag)
            repository.save_chat_message(session_id, "assistant", reply, action_tag, {"total_found": len(schemes), "matched_ids": [s["id"] for s in schemes]})

            return {
                "session_id": session_id,
                "reply": reply,
                "extracted_state": resolved_state,
                "extracted_age": merged_profile.get("age"),
                "extracted_category": merged_profile.get("category"),
                "extracted_caste": merged_profile.get("caste"),
                "schemes": schemes,
                "total_found": len(schemes),
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

        candidate_schemes, _ = repository.get_schemes(status="active", limit=200)
        schemes, total = rank_and_filter_schemes(candidate_schemes, match_profile, match_intent, limit=4)

        # Relevance Guard: If user asked a specific query that yielded 0 matches, do not dump random state schemes!
        if total == 0:
            reply = (
                f"🔍 I searched the official gazette database, but could not find a verified scheme specifically matching '**{msg_clean}**'.\n\n"
                f"💡 **Suggested next steps:**\n"
                f"• Check the spelling or search by sector: *Scholarships, Pensions, Agriculture, Health, Housing, Women Welfare*.\n"
                f"• Explore schemes available in your state ({merged_profile.get('state') or 'All India'})."
            )
            action_tag = "no_match"
            schemes = []
            total = 0
        else:
            reply = self.generate_grounded_response(
                query=msg_clean,
                extracted=merged_profile,
                schemes=schemes,
                total_found=len(schemes),
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
            {"total_found": len(schemes), "matched_ids": [s["id"] for s in schemes]}
        )

        suggestions = []
        caste = merged_profile.get("caste")
        age = merged_profile.get("age")
        category = merged_profile.get("category")
        if caste:
            suggestions.append(f"🎓 {caste} Scholarships")
        if age is None:
            suggestions.append("Age: 18 - 35 yrs (Youth)")
            suggestions.append("Age: 60+ (Senior Citizen)")
        if not category:
            suggestions.append("Health (Ayushman Card)")
            suggestions.append("PM Kisan Farming Support")
        if state:
            suggestions.append(f"More schemes in {state}")

        return {
            "session_id": session_id,
            "reply": reply,
            "extracted_state": state,
            "extracted_age": age,
            "extracted_category": category,
            "extracted_caste": caste,
            "schemes": schemes,
            "total_found": len(schemes),
            "action_taken": action_tag,
            "suggestions": suggestions[:4]
        }

