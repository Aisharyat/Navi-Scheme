import json
import re
from typing import Optional, List, Dict, Any

from src.config.settings import get_settings

try:
    from google import genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


class GroundedAIService:
    def __init__(self):
        self.settings = get_settings()
        self._client = None
        self._init_client()

    def _init_client(self):
        """Initialize Google GenAI client if API key is provided."""
        if _GENAI_AVAILABLE and self.settings.gemini_api_key:
            try:
                self._client = genai.Client(api_key=self.settings.gemini_api_key)
            except Exception as e:
                print(f"[WARN] Could not initialize Gemini client: {e}")
                self._client = None

    def extract_intent_and_caste(self, text_input: str) -> Dict[str, Any]:
        """
        Extract caste, state, age, gender, category, and eligibility criteria
        using Gemini AI with deterministic regex fallback.
        """
        # 1. Try Gemini entity extraction first if available
        if self._client:
            try:
                prompt = (
                    "Extract citizen profile parameters from the following user query for government scheme eligibility in India.\n"
                    f"User query: \"{text_input}\"\n\n"
                    "Return ONLY a valid JSON object with the following keys:\n"
                    "- \"state\": string or null (e.g. \"Maharashtra\", \"Karnataka\", \"Uttar Pradesh\", \"All India\")\n"
                    "- \"age\": integer or null (e.g. 20, 65)\n"
                    "- \"gender\": \"Male\", \"Female\", or \"All\"\n"
                    "- \"caste\": \"SC\", \"ST\", \"OBC\", \"EWS\", \"General\", \"Minority\", or null\n"
                    "- \"category\": \"Education\", \"Health\", \"Housing\", \"Agriculture\", \"Pension\", \"Women & Child\", \"Social Welfare\", or null\n"
                    "- \"keywords\": list of key query strings (e.g. [\"scholarship\", \"college\"])\n"
                )

                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                )

                response = self._client.models.generate_content(
                    model=self.settings.gemini_model or "gemini-3.6-flash",
                    contents=prompt,
                    config=config,
                )

                if response and response.text:
                    parsed = json.loads(response.text.strip())
                    return {
                        "state": parsed.get("state"),
                        "age": parsed.get("age"),
                        "gender": parsed.get("gender") or "All",
                        "caste": parsed.get("caste"),
                        "category": parsed.get("category"),
                        "keywords": parsed.get("keywords") or [],
                        "raw_text": text_input,
                        "source": "gemini",
                    }
            except Exception as e:
                print(f"[INFO] Gemini entity extraction fallback (status: {e})")

        # 2. Robust Local Deterministic Extractor (Zero Quota Dependency)
        return self._local_rule_extraction(text_input)

    def _local_rule_extraction(self, text_input: str) -> Dict[str, Any]:
        """Comprehensive local Indian government entity & caste extractor."""
        text_lower = text_input.lower()

        state = None
        age = None
        gender = "All"
        caste = None
        category = None
        keywords = []

        # 1. Caste / Social Category Detection
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

        # 2. Age Detection
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

        # 3. State Detection
        known_states = [
            "maharashtra", "uttar pradesh", "madhya pradesh", "karnataka", "bihar",
            "tamil nadu", "rajasthan", "gujarat", "west bengal", "delhi", "kerala",
            "punjab", "haryana", "andhra pradesh", "telangana", "odisha", "assam", "all india"
        ]
        for st in known_states:
            if st in text_lower:
                state = "All India" if st == "all india" else st.title()
                break

        # 4. Specific Subject & Category Detection
        subject = None
        if any(w in text_lower for w in ["inter caste", "intercaste", "marriage", "shadi", "vivah", "shaadi", "nikah", "bride", "groom"]):
            category = "Social Welfare"
            subject = "marriage"
            if "inter" in text_lower or "caste" in text_lower:
                keywords.append("inter-caste")
            keywords.append("marriage")
        elif any(w in text_lower for w in ["education", "scholarship", "fellowship", "study", "college", "school", "degree", "diploma", "padhai", "post matric", "pre matric"]):
            category = "Education"
            subject = "scholarship"
            keywords.append("scholarship")
        elif any(w in text_lower for w in ["health", "hospital", "medical", "treatment", "bimar", "ayushman", "arogya", "swasthya"]):
            category = "Health"
            subject = "health"
        elif any(w in text_lower for w in ["house", "housing", "awas", "home", "ghar", "makan"]):
            category = "Housing"
            subject = "housing"
        elif any(w in text_lower for w in ["pension", "old age", "senior", "retirement", "vriddha", "niradhar"]):
            category = "Pension"
            subject = "pension"
        elif any(w in text_lower for w in ["farmer", "kisan", "krishi", "agriculture", "crop", "kheti", "pm kisan"]):
            category = "Agriculture"
            subject = "agriculture"
        elif any(w in text_lower for w in ["daughter", "girl", "woman", "women", "mahila", "ladli", "sukanya", "beti", "ladki bahin"]):
            category = "Women & Child"
            subject = "women"
        elif any(w in text_lower for w in ["ration", "bpl", "poverty", "subsid", "welfare", "social", "samaj kalyan", "anudan"]):
            category = "Social Welfare"
            subject = "welfare"

        # 5. Gender Detection
        if any(w in text_lower for w in ["daughter", "girl", "woman", "women", "female", "she", "her", "mahila", "ladki"]):
            gender = "Female"
        elif any(w in text_lower for w in ["son", "boy", "man", "male", "he", "his", "ladka"]):
            gender = "Male"

        return {
            "state": state,
            "age": age,
            "gender": gender,
            "caste": caste,
            "category": category,
            "subject": subject,
            "keywords": keywords,
            "raw_text": text_input,
            "source": "local_grounded",
        }

    def generate_grounded_response(
        self,
        query: str,
        extracted: Dict[str, Any],
        schemes: List[Dict[str, Any]],
        total_found: int,
    ) -> str:
        """
        Generate a strictly grounded conversational response based on verified DB schemes.
        Anti-Hallucination guarantee: Gemini is constrained to summarize ONLY the verified DB records.
        """
        caste = extracted.get("caste")
        state = extracted.get("state")
        age = extracted.get("age")
        category = extracted.get("category")

        # 1. Try Grounded Generation via Gemini if available
        if self._client and schemes:
            try:
                schemes_context = []
                for s in schemes[:3]:
                    schemes_context.append(
                        f"Scheme Name: {s.get('title')}\n"
                        f"State: {s.get('state')}\n"
                        f"Category: {s.get('category')}\n"
                        f"Key Benefits: {s.get('benefits')}\n"
                        f"Eligibility Rules: {s.get('eligibility_summary')}\n"
                        f"Required Documents: {s.get('documents_required')}\n"
                        f"Official Application Portal: {s.get('application_url')}\n"
                    )
                context_str = "\n---\n".join(schemes_context)

                system_instruction = (
                    "You are 'Navi Scheme AI', an official Indian Government Welfare Assistant.\n"
                    "CRITICAL ANTI-HALLUCINATION RULES:\n"
                    "1. ONLY state facts and eligibility directly present in the provided context below.\n"
                    "2. If caste/category (e.g. SC, ST, OBC, EWS, General) is mentioned by the citizen, explain how the scheme applies to their category.\n"
                    "3. Do NOT make up any fake numbers, unverified schemes, or nonexistent portals.\n"
                    "4. Keep the answer clear, helpful, bulleted, and professional in tone."
                )

                user_prompt = (
                    f"User Query: \"{query}\"\n"
                    f"Citizen Context: Caste={caste or 'Not specified'}, State={state or 'All India'}, Age={age or 'Any'}, Category={category or 'All'}\n\n"
                    f"Verified Schemes Found in Database:\n{context_str}\n\n"
                    "Provide a grounded, concise summary guiding the citizen on which schemes they can apply for and why."
                )

                response = self._client.models.generate_content(
                    model=self.settings.gemini_model or "gemini-3.6-flash",
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.2,
                    ),
                )

                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                print(f"[INFO] Gemini grounded summary fallback: {e}")

        # 2. Deterministic Factual Grounding Fallback
        caste_tag = f" ({caste} Category)" if caste else ""
        criteria_parts = []
        if caste:
            criteria_parts.append(f"Caste/Category: **{caste}**")
        if category:
            criteria_parts.append(f"Area: **{category}**")
        if state:
            criteria_parts.append(f"State: **{state}**")
        if age is not None:
            criteria_parts.append(f"Age: **{age} yrs**")

        criteria_str = f" for {', '.join(criteria_parts)}" if criteria_parts else ""

        if total_found > 0:
            lines = [
                f"✅ **Found {len(schemes)} verified government welfare scheme(s)**{criteria_str}:",
                "",
            ]
            for s in schemes[:3]:
                title = s.get("title", "Scheme")
                benefits = s.get("benefits", "")
                eligibility = s.get("eligibility_summary", "")
                portal = s.get("application_url", "")
                
                lines.append(f"### 🏛️ {title}")
                if benefits:
                    lines.append(f"- **Key Benefit:** {benefits}")
                if eligibility:
                    lines.append(f"- **Eligibility:** {eligibility}")
                if portal:
                    lines.append(f"- **Official Portal:** [{portal}]({portal})")
                lines.append("")

            if caste in ["SC", "ST", "OBC", "EWS"]:
                lines.append(f"💡 *Note for {caste} applicants: Ensure you have a valid {caste} Caste/Category Certificate and Income Certificate issued by the competent State Authority (Tehsildar/SDM).*")

            return "\n".join(lines)
        else:
            return (
                f"🔍 I searched for government welfare schemes{criteria_str}, but no exact match was found in the database.\n\n"
                f"💡 **Suggested next steps:**\n"
                f"- For **{caste or 'reserved category'}** scholarships, check the **National Scholarship Portal (scholarships.gov.in)** or your State Social Welfare Department.\n"
                f"- Try broadening your search by setting the State to *All India* or selecting a different age bracket."
            )

