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
                socket.setdefaulttimeout(3.0)
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
                with urllib.request.urlopen(req, timeout=3.0) as res:
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

        # Age
        age_patterns = [
            r"\b(?:age|aged|am)\s*([0-9]{1,2})\b",
            r"\b([0-9]{1,2})\s*(?:years?|yrs?|yr)\s*(?:old)?\b",
            r"\b([0-9]{1,2})\s*(?:saal|sal)\b",
        ]
        for pat in age_patterns:
            match = re.search(pat, text_lower)
            if match:
                try:
                    age = int(match.group(1))
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

        # States
        known_states = [
            "maharashtra", "uttar pradesh", "madhya pradesh", "karnataka", "bihar",
            "tamil nadu", "rajasthan", "gujarat", "west bengal", "delhi", "kerala",
            "punjab", "haryana", "andhra pradesh", "telangana", "odisha", "assam", "all india"
        ]
        for st in known_states:
            if st in text_lower:
                state = "All India" if st == "all india" else st.title()
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
                    schemes_context.append(
                        f"Scheme Name: {s.get('title')}\n"
                        f"State: {s.get('state')}\n"
                        f"Category: {s.get('category')}\n"
                        f"Key Benefits: {s.get('benefits')}\n"
                        f"Eligibility Rules: {s.get('eligibility_summary')}\n"
                        f"Official Application Portal: {s.get('application_url')}\n"
                    )
                context_str = "\n---\n".join(schemes_context)

                target_lang = "Hindi" if language == "hi" else "English"
                system_instruction = (
                    f"{NAVI_SCHEME_SYSTEM_PROMPT}\n\n"
                    f"ADDITIONAL INSTRUCTIONS:\n"
                    f"- Respond in {target_lang}.\n"
                    f"- Format clearly with headings, bold titles, and bullet points.\n"
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
        if total_found > 0:
            lines = [
                f"✅ **Found {len(schemes)} verified government scheme(s)** matching your criteria:\n",
            ]
            for s in schemes[:3]:
                title = s.get("title", "Scheme")
                raw_benefits = s.get("benefits", "")
                raw_eligibility = s.get("eligibility_summary", "")
                benefits_clean = clean_bureaucratic_text(raw_benefits)
                eligibility_clean = clean_bureaucratic_text(raw_eligibility)
                portal = s.get("application_url", "")

                lines.append(f"### 🏛️ {title}")
                if benefits_clean:
                    lines.append(f"• **Key Benefit:** {benefits_clean}")
                if eligibility_clean:
                    lines.append(f"• **Eligibility Criteria:** {eligibility_clean}")
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

    def process_conversational_turn(
        self,
        session_id: str,
        message: str,
        repository: Any,
        user_id: Optional[str] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Executes the multi-turn session reasoning pipeline:
        1. Load session & accumulated profile facts.
        2. Run safety checks (fraud refusal / scam warning / off-topic / navi scheme intro / loan calculator).
        3. Check for application steps or specific scheme guidance.
        4. Extract new profile facts and merge into session (new overwrites old).
        5. Clarification gate (ask 1 clarifying question if state is missing).
        6. Grounded search & explanation constrained to verified DB facts.
        7. Persist message log with action_taken tag for Looker Studio analytics.
        """
        msg_clean = message.strip()
        msg_lower = msg_clean.lower()

        # 1. Load or initialize session
        session = repository.get_or_create_session(session_id, user_id=user_id)
        current_profile = repository.get_session_profile(session_id)

        # 2. Safety & Intent Check
        extracted_intent = self.extract_intent_and_entities(msg_clean)
        special_case = extracted_intent.get("special_case")

        # Handle follow-up response with just the interest rate (e.g. "7.5%" or "interest is 8%")
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
                                "suggestions": [
                                    "₹50,000 for 2 years",
                                    "₹2 Lakh for 3 years",
                                    "🌾 Explore schemes in my state"
                                ]
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

            # For loan_rate_needed, check if active scheme in session mentions an interest rate
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

            # Save turn in session log
            repository.save_chat_message(session_id, "user", msg_clean, action_tag)
            repository.save_chat_message(session_id, "assistant", reply, action_tag)

            # Suggestions tailored to intent
            if "loan" in special_case:
                suggestions = [
                    "₹50,000 for 2 years (PM SVANidhi)",
                    "₹2 Lakh for 3 years (Mudra Kishore)",
                    "🌾 Farmer Subsidy Schemes",
                    "🏛️ Explore central schemes"
                ]
            elif special_case == "navi_scheme_intro":
                suggestions = [
                    "🎓 Student Scholarships in UP",
                    "🌾 Schemes for Farmers in Maharashtra",
                    "👩 Women Self-Help Group Schemes",
                    "📊 Calculate Loan EMI"
                ]
            else:
                suggestions = [
                    "🌾 Schemes for Farmers",
                    "🎓 Student Scholarships",
                    "👩 Women & Child Welfare",
                    "🏥 Health & Ayushman Bharat"
                ]

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
                "suggestions": suggestions
            }

        # 3. Check for specific scheme inquiry or "Explain ..." (e.g. from Explain with AI button or direct search)
        is_explain_query = bool(re.search(r"^(?:explain\s+|what\s+is\s+|tell\s+me\s+about\s+|details\s+of\s+|about\s+)", msg_clean, re.IGNORECASE))
        direct_scheme = repository.find_scheme_by_title_or_query(msg_clean)
        
        # If user explicitly asked to Explain / inquiring on a scheme OR entered an exact/close scheme name
        if direct_scheme and (is_explain_query or len(msg_clean.split()) >= 2):
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

        # 4. Check for "check eligibility" query for active scheme
        if any(w in msg_lower for w in ["check eligibility", "check my eligibility", "am i eligible", "eligibility check"]):
            active_sch = repository.find_scheme_by_title_or_query(msg_clean) or self._get_active_scheme_from_session(session_id, repository)
            if active_sch:
                sch_title = active_sch.get("title", "this scheme")
                sch_state = active_sch.get("state") or "All India (Central)"
                sch_elig = clean_bureaucratic_text(active_sch.get("eligibility_summary") or "Open to eligible citizens as per official criteria.")
                sch_target = active_sch.get("category") or "General"

                user_state = current_profile.get("state")
                user_age = current_profile.get("age")
                user_caste = current_profile.get("caste")

                state_match = "✅ Matched" if (not sch_state or sch_state == "All India" or (user_state and user_state.lower() in sch_state.lower())) else f"⚠️ Requires residency in {sch_state}"
                age_match = f"Age: {user_age} yrs" if user_age else "Age: Not specified"

                reply = (
                    f"### 🎯 Eligibility Check for **{sch_title}**\n\n"
                    f"**Official Scheme Criteria:**\n"
                    f"• **State Coverage:** {sch_state} ({state_match})\n"
                    f"• **Target Category:** {sch_target} ({age_match})\n"
                    f"• **Key Eligibility Rules:** {sch_elig}\n\n"
                    f"💡 *If you meet these requirements, you can submit your application directly on the official portal.*"
                )
                action_tag = "eligibility_check"
                repository.save_chat_message(session_id, "user", msg_clean, action_tag)
                repository.save_chat_message(session_id, "assistant", reply, action_tag, {"scheme_id": active_sch["id"]})

                return {
                    "session_id": session_id,
                    "reply": reply,
                    "extracted_state": user_state or sch_state,
                    "extracted_age": user_age,
                    "extracted_category": active_sch.get("category"),
                    "extracted_caste": user_caste,
                    "schemes": [active_sch],
                    "total_found": 1,
                    "action_taken": action_tag,
                    "suggestions": [
                        "📝 Documents required",
                        "How to apply step-by-step",
                        "🏛️ Explore other schemes in my state"
                    ]
                }

        # 5. Check for "documents required" query
        if any(w in msg_lower for w in ["documents required", "required documents", "what documents", "document checklist", "docs required"]):
            active_sch = repository.find_scheme_by_title_or_query(msg_clean) or self._get_active_scheme_from_session(session_id, repository)
            if active_sch:
                docs = active_sch.get("documents_required_list") or active_sch.get("documents_required")
                if isinstance(docs, list) and docs:
                    docs_text = "\n".join(f"• {d}" for d in docs)
                elif isinstance(docs, str) and docs.strip():
                    docs_text = "\n".join(f"• {d.strip()}" for d in re.split(r"[\n,;]+", docs) if d.strip())
                else:
                    docs_text = (
                        "• Identity Proof (Aadhaar Card / Voter ID)\n"
                        "• Address / Domicile Certificate\n"
                        "• Bank Account Passbook (Aadhaar linked)\n"
                        "• Income / Caste Certificate (if applicable)"
                    )

                portal = active_sch.get("application_url") or "https://www.india.gov.in"
                reply = (
                    f"### 📝 Required Documents Checklist for **{active_sch.get('title')}**\n\n"
                    f"Please ensure you have verified copies of the following documents:\n\n"
                    f"{docs_text}\n\n"
                    f"🔗 **Official Application Portal:** [{portal}]({portal})\n\n"
                    f"*(Always submit documents only on the official government portal. Applying is 100% free.)*"
                )
                action_tag = "docs_guide"
                repository.save_chat_message(session_id, "user", msg_clean, action_tag)
                repository.save_chat_message(session_id, "assistant", reply, action_tag, {"scheme_id": active_sch["id"]})

                return {
                    "session_id": session_id,
                    "reply": reply,
                    "extracted_state": active_sch.get("state") or current_profile.get("state"),
                    "extracted_age": current_profile.get("age"),
                    "extracted_category": active_sch.get("category"),
                    "extracted_caste": current_profile.get("caste"),
                    "schemes": [active_sch],
                    "total_found": 1,
                    "action_taken": action_tag,
                    "suggestions": [
                        "How to apply step-by-step",
                        "🎯 Check my eligibility",
                        "🏛️ Explore other schemes in my state"
                    ]
                }

        # 6. Check for "how do I apply" / application steps query (Rule 3)
        if any(w in msg_lower for w in ["how to apply", "how do i apply", "apply online", "application process", "steps to apply", "process to apply"]):
            target_scheme = repository.find_scheme_by_title_or_query(msg_clean) or self._get_active_scheme_from_session(session_id, repository)

            if target_scheme:
                steps_raw = target_scheme.get("application_steps_list") or target_scheme.get("application_process") or target_scheme.get("application_steps")
                docs_raw = target_scheme.get("documents_required") or "Aadhaar Card, Bank Passbook, Identity Proof, Income Certificate (if applicable)."
                portal = target_scheme.get("application_url") or "https://myscheme.gov.in"

                step_lines = []
                if isinstance(steps_raw, list) and steps_raw:
                    for idx, st in enumerate(steps_raw, 1):
                        step_lines.append(f"{idx}. {st.strip()}")
                elif isinstance(steps_raw, str) and steps_raw.strip():
                    raw_split = re.split(r"(?:Step\s*[0-9]+:?|(?<=\.)\s+(?=[0-9]+\.))", steps_raw)
                    filtered_steps = [st.strip() for st in raw_split if len(st.strip()) > 5]
                    if filtered_steps:
                        for idx, st in enumerate(filtered_steps, 1):
                            step_lines.append(f"{idx}. {st}")
                    else:
                        step_lines.append(f"1. {steps_raw.strip()}")
                else:
                    step_lines = [
                        "1. Visit the official government portal linked below.",
                        "2. Register or log in using your Aadhaar or mobile number.",
                        "3. Complete the online citizen application form with verified profile details.",
                        "4. Upload the required documents.",
                        "5. Submit and record your application reference ID."
                    ]

                reply = (
                    f"### 📝 How to Apply for **{target_scheme['title']}** (Rule 3)\n\n"
                    f"**Key Documents Required:**\n"
                    f"• {docs_raw}\n\n"
                    f"**Step-by-Step Application Instructions:**\n" +
                    "\n".join(step_lines) +
                    f"\n\n🔗 **Official Application Portal:** [{portal}]({portal})\n\n"
                    f"*(Reminder: Government welfare schemes are 100% free of cost. Never pay unauthorized agents.)*"
                )
                action_tag = "apply_guide"
                repository.save_chat_message(session_id, "user", msg_clean, action_tag)
                repository.save_chat_message(session_id, "assistant", reply, action_tag, {"scheme_id": target_scheme["id"]})

                return {
                    "session_id": session_id,
                    "reply": reply,
                    "extracted_state": target_scheme.get("state") or current_profile.get("state"),
                    "extracted_age": current_profile.get("age"),
                    "extracted_category": target_scheme.get("category"),
                    "extracted_caste": current_profile.get("caste"),
                    "schemes": [target_scheme],
                    "total_found": 1,
                    "action_taken": action_tag,
                    "suggestions": [
                        "🎯 Check my eligibility for this scheme",
                        "📝 Required documents checklist",
                        "🏛️ Explore other schemes in my state"
                    ]
                }

        # 4. Extract new facts and merge into accumulated session profile
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

        # 5. Clarification Gate: If profile still lacks a state, ask one clarifying question and stop
        state = merged_profile.get("state")
        if not state:
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
                "suggestions": [
                    "Maharashtra",
                    "Uttar Pradesh",
                    "Karnataka",
                    "All India (Central)"
                ]
            }

        # 6. Search verified catalog with accumulated profile
        keywords = extracted_intent.get("keywords") or []
        subject = extracted_intent.get("subject")
        primary_query = keywords[0] if keywords else (subject or None)
        age = merged_profile.get("age")
        gender = merged_profile.get("gender")
        category = merged_profile.get("category")
        caste = merged_profile.get("caste")

        schemes, total = repository.get_schemes(
            query=primary_query,
            state=state if state and state.lower() != "all india" else None,
            age=age,
            gender=gender if gender != "All" else None,
            category=category if category != "All" else None,
            limit=4,
        )

        if total == 0:
            # Broaden search with query or category
            schemes, total = repository.get_schemes(
                query=primary_query or caste or category,
                age=age,
                gender=gender if gender != "All" else None,
                limit=4,
            )

        # 7. Generate grounded response using verified DB facts
        reply = self.generate_grounded_response(
            query=msg_clean,
            extracted=merged_profile,
            schemes=schemes,
            total_found=total,
            language=language,
        )

        action_tag = "matched" if total > 0 else "no_match"

        # 8. Persist turn in message log
        repository.save_chat_message(session_id, "user", msg_clean, action_tag)
        repository.save_chat_message(
            session_id,
            "assistant",
            reply,
            action_tag,
            {"total_found": total, "matched_ids": [s["id"] for s in schemes]}
        )

        # Dynamic suggestions
        suggestions = []
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
            "total_found": total,
            "action_taken": action_tag,
            "suggestions": suggestions[:4]
        }

