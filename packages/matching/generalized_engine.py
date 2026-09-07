import json
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Tuple


@dataclass
class MatchProfile:
    state: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = "All"
    caste: Optional[str] = None
    occupation: Optional[str] = None
    category: Optional[str] = None
    annual_income: Optional[float] = None
    marital_status: Optional[str] = None
    disability_status: Optional[bool] = None
    is_proxy_profile: bool = False


@dataclass
class MatchIntent:
    raw_query: str
    is_targeted: bool = False                # True if user explicitly requested a specific group/demographic/topic
    target_caste: Optional[str] = None       # e.g. "SC", "ST", "OBC", "EWS", "Minority"
    target_occupation: Optional[str] = None  # e.g. "student", "farmer", "self_employed", "unemployed", "retired"
    target_gender: Optional[str] = None      # e.g. "Female", "Male"
    target_category: Optional[str] = None    # e.g. "Education", "Agriculture", "Women & Child", "Pension", "Health", "Housing", "Social Welfare"
    target_subject: Optional[str] = None     # e.g. "marriage", "inter_caste_marriage", "disability", "scholarship", "loan"
    target_state: Optional[str] = None       # e.g. "Maharashtra", "Karnataka"
    keywords: List[str] = field(default_factory=list)


@dataclass
class SchemeMatchResult:
    scheme: Dict[str, Any]
    match_status: str                        # "eligible" | "potential_match" | "ineligible"
    score: float                             # Numerical score for ranking
    is_targeted_match: bool                  # True if directly matches specific targeted intent
    match_reasons: List[str] = field(default_factory=list)
    missing_requirements: List[str] = field(default_factory=list)
    disqualification_reasons: List[str] = field(default_factory=list)


def parse_query_intent(query: str, current_profile: Optional[Dict[str, Any]] = None) -> MatchIntent:
    """
    Parses user query into structured MatchIntent, identifying whether the query is
    targeted or general discovery.
    """
    q_clean = query.strip()
    q_lower = q_clean.lower()
    profile = current_profile or {}

    is_targeted = False
    target_caste = None
    target_occupation = None
    target_gender = None
    target_category = None
    target_subject = None
    target_state = None
    keywords = []

    # 1. Targeted phrasing markers
    has_targeted_marker = bool(re.search(
        r"\b(specifically\s+for|available\s+for|schemes?\s+for|only\s+for|meant\s+for|focused\s+on|special\s+for|for\s+(?:sc|st|obc|ews|women|girls|students|farmers|senior|inter[-\s]?caste))\b",
        q_lower
    ))

    # 2. Caste target
    if re.search(r"\b(sc|scheduled caste|scheduled castes|dalit|anusuchit jati)\b", q_lower):
        target_caste = "SC"
        keywords.append("SC")
        is_targeted = True
    elif re.search(r"\b(st|scheduled tribe|scheduled tribes|adivasi|anusuchit janjati|tribal)\b", q_lower):
        target_caste = "ST"
        keywords.append("ST")
        is_targeted = True
    elif re.search(r"\b(obc|other backward class|other backward classes|pichhda|pichda|non-creamy layer)\b", q_lower):
        target_caste = "OBC"
        keywords.append("OBC")
        is_targeted = True
    elif re.search(r"\b(ews|economically weaker section)\b", q_lower):
        target_caste = "EWS"
        keywords.append("EWS")
        is_targeted = True
    elif re.search(r"\b(minority|minorities|muslim|christian|sikh|jain|buddhist|parsi)\b", q_lower):
        target_caste = "Minority"
        keywords.append("Minority")
        is_targeted = True

    # 3. Occupation / Beneficiary target
    if re.search(r"\b(student|students|studying|scholarship|scholarships|college|school|higher education|matric|degree|diploma)\b", q_lower):
        target_occupation = "student"
        target_category = "Education"
        keywords.append("student")
        is_targeted = True
    elif re.search(r"\b(farmer|farmers|kisan|krishi|farming|crop|cultivator)\b", q_lower):
        target_occupation = "farmer"
        target_category = "Agriculture"
        keywords.append("farmer")
        is_targeted = True
    elif re.search(r"\b(street vendor|street vendors|vendor|hawker|svanidhi)\b", q_lower):
        target_occupation = "self_employed"
        target_category = "Social Welfare"
        is_targeted = True
    elif re.search(r"\b(senior citizen|senior citizens|pensioner|old age|vriddha|elderly)\b", q_lower):
        target_occupation = "retired"
        target_category = "Pension"
        is_targeted = True
    elif re.search(r"\b(unemployed|job seeker|berozgar|youth employment)\b", q_lower):
        target_occupation = "unemployed"
        target_category = "Employment"
        is_targeted = True

    # 4. Gender target
    if re.search(r"\b(woman|women|female|girl|girls|daughter|mahila|kanya|ladki|matru|widow)\b", q_lower):
        target_gender = "Female"
        if not target_category:
            target_category = "Women & Child"
        is_targeted = True
    elif re.search(r"\b(man|men|male|boy|boys|son)\b", q_lower):
        target_gender = "Male"

    # 5. Subject / Topic target
    if re.search(r"\b(inter[-\s]?caste\s+marriage|intercaste\s+marriage|inter[-\s]?caste|marriage\s+scheme|marriage\s+incentive|vivah|shaadi|shadi)\b", q_lower):
        target_subject = "inter_caste_marriage"
        target_category = "Social Welfare"
        keywords.append("inter_caste_marriage")
        is_targeted = True
    elif re.search(r"\b(disabilit|pwd|divyang|handicap|blind|deaf|locomotor)\b", q_lower):
        target_subject = "disability"
        target_category = "Social Welfare"
        is_targeted = True
    elif re.search(r"\b(health|hospital|medical|treatment|ayushman|arogya|swasthya)\b", q_lower):
        target_subject = "health"
        target_category = "Health"
    elif re.search(r"\b(house|housing|awas|home loan subsidy|makan|ghar)\b", q_lower):
        target_subject = "housing"
        target_category = "Housing"
    elif re.search(r"\b(pension|retirement|guaranteed pension)\b", q_lower):
        target_subject = "pension"
        target_category = "Pension"

    # 6. State target
    known_states = [
        "maharashtra", "uttar pradesh", "madhya pradesh", "karnataka", "bihar",
        "tamil nadu", "rajasthan", "gujarat", "west bengal", "delhi", "kerala",
        "punjab", "haryana", "andhra pradesh", "telangana", "odisha", "assam",
        "jharkhand", "chhattisgarh", "uttarakhand", "himachal pradesh", "goa",
        "jammu & kashmir", "jammu and kashmir", "ladakh", "sikkim", "tripura",
        "meghalaya", "manipur", "mizoram", "nagaland", "all india"
    ]
    for st in known_states:
        if re.search(rf"\b{re.escape(st)}\b", q_lower):
            target_state = "All India" if st == "all india" else st.title()
            break

    # If prompt contains "specifically" or targeted phrasing, enforce is_targeted
    if has_targeted_marker:
        is_targeted = True

    # General queries like "I am 20 years old from Maharashtra. What government schemes are available?"
    if re.search(r"\b(what\s+(?:government\s+)?schemes\s+are\s+available|find\s+schemes|general\s+schemes|schemes\s+for\s+me)\b", q_lower):
        if not has_targeted_marker and not target_caste and not target_subject:
            is_targeted = False

    return MatchIntent(
        raw_query=q_clean,
        is_targeted=is_targeted,
        target_caste=target_caste,
        target_occupation=target_occupation,
        target_gender=target_gender,
        target_category=target_category,
        target_subject=target_subject,
        target_state=target_state,
        keywords=keywords,
    )


def extract_scheme_eligibility_profile(scheme: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts structured eligibility constraints and target beneficiaries from a scheme record.
    Grounded in structured fields, JSON rules, and verified text.
    """
    state = scheme.get("state") or "All India"
    target_gender = scheme.get("target_gender") or "All"
    min_age = scheme.get("min_age") if scheme.get("min_age") is not None else 0
    max_age = scheme.get("max_age") if scheme.get("max_age") is not None else 120
    income_limit = scheme.get("income_limit")
    category = scheme.get("category") or scheme.get("sector") or "Social Welfare"

    title = (scheme.get("title") or scheme.get("name") or "").lower()
    desc = (scheme.get("description") or scheme.get("short_description") or "").lower()
    eligibility_summary = (scheme.get("eligibility_summary") or "").lower()
    full_text = f"{title} {desc} {eligibility_summary}"

    # 1. Open eligibility & Universal access detection
    # Schemes with "anyone can apply", "open-ended", "all individuals", etc.
    is_open_to_all = bool(re.search(
        r"\b(anyone can apply|open to all|all individuals|all citizens|all farmers|all borrowers|all eligible|open ended)\b",
        full_text
    ))

    # 2. Institutional / Organizational Scope Detection
    # Schemes for research agencies, institutions, universities, industry associations, companies rather than individual citizens
    is_institutional = bool(re.search(
        r"\b(for agencies|for institutions|industry associations|r&d institutions|distinct legal entity|proof of number of employees|principal investigator|pi and co-pi|host institute|registration under companies act|societies registration act|registered under indian trusts act|commercial banks|lending institutions)\b",
        full_text
    ))

    # 3. Gender Normalization:
    # If open to all or institutional, cannot be exclusively female
    if is_open_to_all:
        target_gender = "All"
    elif target_gender == "All" and not is_institutional:
        # Check if title or summary indicates exclusive female targeting
        if re.search(r"\b(specifically for women|specifically for female|only for women|only for girls|exclusively for women|exclusively for female|women only|girl children|widow pension|mahila yojana|kanya yojana|matru vandana|maternity benefit)\b", full_text):
            target_gender = "Female"

    # 4. Target Castes
    target_castes: Set[str] = set()
    is_caste_restricted = False

    # Check structured eligibility rules first
    rules_dict = scheme.get("eligibility_rules") or {}
    if isinstance(rules_dict, str):
        try:
            rules_dict = json.loads(rules_dict)
        except Exception:
            rules_dict = {}

    for r in rules_dict.get("rules", []):
        field_name = r.get("field", "")
        val = r.get("value")
        if field_name in ["social_category", "caste"]:
            is_caste_restricted = True
            if isinstance(val, list):
                for v in val:
                    target_castes.add(str(v).upper())
            elif val:
                target_castes.add(str(val).upper())

    # Text-based caste targeting
    # Must NOT be an open scheme where SC/ST is merely mentioned as priority borrower or concessional subsidy
    if not is_open_to_all and not is_caste_restricted:
        if re.search(r"\b(specifically for sc\b|only for sc\b|exclusively for sc\b|meant for sc\b|for sc students?|for scheduled castes?|sc scholarship|sc category only|belonging to scheduled caste|sc community|sc patients?|sc couples?|scheduled caste (?:and|&) scheduled tribe persons?)\b", full_text):
            target_castes.add("SC")
            is_caste_restricted = True
        if re.search(r"\b(specifically for st\b|only for st\b|exclusively for st\b|meant for st\b|for st students?|for scheduled tribes?|st scholarship|st category only|belonging to scheduled tribe|st community|st patients?|st couples?)\b", full_text):
            target_castes.add("ST")
            is_caste_restricted = True
        if re.search(r"\b(specifically for obc\b|only for obc\b|exclusively for obc\b|for obc students?|for other backward class|obc scholarship|belonging to other backward)\b", full_text):
            target_castes.add("OBC")
            is_caste_restricted = True
        if re.search(r"\b(specifically for ews\b|only for ews\b|exclusively for ews\b|for ews students?|economically weaker section)\b", full_text):
            target_castes.add("EWS")
            is_caste_restricted = True

    # 5. Target Occupations
    target_occupations: Set[str] = set()
    is_occupation_restricted = False

    # Individual student targeting (Excludes institutional grants and medical colleges attached to hospitals)
    if not is_institutional:
        if re.search(r"\b(scholarship|scholarships|fellowship|fellowships|stipend|matric|post[-\s]?matric|pre[-\s]?matric|tuition\s+fee|student enrollment|studying in|enrolled in|for students?|sc students?|st students?|higher education scholarship)\b", full_text):
            target_occupations.add("student")
            is_occupation_restricted = True
        elif category.lower() in ["education", "education & learning"] and re.search(r"\b(students?|learners?|tuition|school\s+admission|college\s+admission)\b", full_text):
            target_occupations.add("student")
            is_occupation_restricted = True

    if category.lower() in ["agriculture", "rural & environment"] or re.search(r"\b(farmer|farmers|kisan|cultivator|landholding|krishi)\b", full_text):
        if not is_institutional and not is_open_to_all:
            target_occupations.add("farmer")
            is_occupation_restricted = True

    if re.search(r"\b(street\s+vendors?|hawkers?|peri-urban\s+vendors?)\b", full_text):
        target_occupations.add("self_employed")
        is_occupation_restricted = True

    if category.lower() == "pension" or re.search(r"\b(pension\s+for\s+unorganized|old\s+age\s+pension|senior\s+citizen\s+pension)\b", full_text):
        target_occupations.add("retired")
        target_occupations.add("unorganized_worker")

    # 6. Target Subjects
    target_subjects: Set[str] = set()
    if re.search(r"\b(inter[-\s]?caste\s+marriage|intercaste\s+marriage|social\s+integration\s+through\s+inter[-\s]?caste|marriage\s+incentive)\b", full_text):
        target_subjects.add("inter_caste_marriage")
    if re.search(r"\b(disabilit|pwd|divyang|handicap)\b", full_text):
        target_subjects.add("disability")
    if category.lower() in ["health", "health & wellness"] or re.search(r"\b(hospital|cashless|treatment|medical\s+aid|health\s+insurance|surgery)\b", full_text):
        target_subjects.add("health")
    if re.search(r"\b(pucca\s+house|permanent\s+house|home\s+loan\s+subsidy|shelter|housing\s+scheme)\b", full_text):
        target_subjects.add("housing")
    if re.search(r"\b(monthly\s+pension|guaranteed\s+pension)\b", full_text):
        target_subjects.add("pension")

    # Regional exclusions
    is_regional_restricted = False
    regional_scope = None
    if re.search(r"\b(north\s+eastern\s+region|north\s+east\s+states|ner\s+only)\b", full_text) and state.lower() == "all india":
        is_regional_restricted = True
        regional_scope = "North Eastern Region"

    return {
        "state": state,
        "target_gender": target_gender,
        "min_age": min_age,
        "max_age": max_age,
        "income_limit": income_limit,
        "category": category,
        "target_castes": target_castes,
        "is_caste_restricted": is_caste_restricted,
        "target_occupations": target_occupations,
        "is_occupation_restricted": is_occupation_restricted,
        "target_subjects": target_subjects,
        "is_regional_restricted": is_regional_restricted,
        "regional_scope": regional_scope,
        "is_institutional": is_institutional,
        "is_open_to_all": is_open_to_all,
    }


def evaluate_scheme_match(
    scheme: Dict[str, Any],
    profile: MatchProfile,
    intent: MatchIntent,
) -> SchemeMatchResult:
    """
    Evaluates a single scheme against a citizen profile and query intent.
    Differentiates between HARD eligibility constraints and SOFT relevance signals.
    """
    props = extract_scheme_eligibility_profile(scheme)
    scheme_title = scheme.get("title") or scheme.get("name") or "Scheme"
    scheme_state = props["state"]
    scheme_gender = props["target_gender"]
    scheme_min_age = props["min_age"]
    scheme_max_age = props["max_age"]
    scheme_income_limit = props["income_limit"]
    scheme_category = props["category"]
    target_castes = props["target_castes"]
    target_occupations = props["target_occupations"]
    target_subjects = props["target_subjects"]

    title_desc = f"{scheme.get('title', '')} {scheme.get('description', '')} {scheme.get('eligibility_summary', '')}".lower()

    disqualifications: List[str] = []
    match_reasons: List[str] = []
    missing_requirements: List[str] = []

    # =========================================================================
    # 1. HARD ELIGIBILITY CONSTRAINTS (Must Satisfy or Fail)
    # =========================================================================

    # A. State & Geographic Jurisdiction
    active_user_state = intent.target_state or profile.state
    if active_user_state and active_user_state.lower() != "all india":
        # If scheme is state-specific and does not match user state -> Disqualified
        if scheme_state.lower() != "all india" and scheme_state.lower() != active_user_state.lower():
            disqualifications.append(f"Restricted to {scheme_state} residents (user is in {active_user_state})")

        # If scheme is regionally restricted (e.g. North Eastern Region)
        if props["is_regional_restricted"]:
            ner_states = ["assam", "meghalaya", "tripura", "mizoram", "manipur", "nagaland", "arunachal pradesh", "sikkim"]
            if active_user_state.lower() not in ner_states:
                disqualifications.append(f"Restricted to {props['regional_scope']} (user is in {active_user_state})")

    # If query explicitly asked for a specific state and scheme is a different state -> Disqualified
    if intent.target_state and intent.target_state.lower() != "all india":
        if scheme_state.lower() != "all india" and scheme_state.lower() != intent.target_state.lower():
            disqualifications.append(f"Restricted to {scheme_state} (query requested {intent.target_state})")

    # B. Age Bounds
    if profile.age is not None:
        user_age = profile.age
        if user_age < scheme_min_age:
            disqualifications.append(f"User age {user_age} is below minimum required age ({scheme_min_age} years)")
        elif user_age > scheme_max_age:
            disqualifications.append(f"User age {user_age} exceeds maximum eligible age ({scheme_max_age} years)")

    # C. Gender Restriction
    active_gender = intent.target_gender or profile.gender
    if active_gender and active_gender != "All":
        if scheme_gender != "All" and scheme_gender.lower() != active_gender.lower():
            disqualifications.append(f"Exclusively for {scheme_gender} beneficiaries (user is {active_gender})")

    # D. Income Ceiling
    if profile.annual_income is not None and scheme_income_limit is not None:
        if profile.annual_income > scheme_income_limit:
            disqualifications.append(
                f"Annual income ₹{profile.annual_income:,.0f} exceeds ceiling of ₹{scheme_income_limit:,.0f}"
            )

    # E. Social Category / Caste Constraint
    # If scheme strictly requires SC/ST/OBC and user has provided a conflicting caste -> Disqualified
    if props["is_caste_restricted"] and target_castes:
        if profile.caste:
            user_caste_norm = profile.caste.upper()
            if user_caste_norm not in target_castes:
                disqualifications.append(
                    f"Restricted to {', '.join(sorted(target_castes))} category (user profile is {profile.caste})"
                )

    # F. Occupation / Student / Institutional Requirement
    # If scheme is institutional (for organizations/universities) and user query asks for citizen/student scheme -> Disqualified
    if props["is_institutional"] and (intent.target_occupation == "student" or profile.occupation == "student"):
        disqualifications.append("Institutional grant for organizations/universities (not an individual citizen scholarship)")

    # If scheme strictly requires student and user's known occupation is incompatible -> Disqualified
    if props["is_occupation_restricted"] and "student" in target_occupations:
        if profile.occupation and profile.occupation not in ["student", "unemployed"]:
            if profile.occupation in ["retired", "farmer", "daily_wage_informal"]:
                disqualifications.append(
                    f"Requires active student enrollment (user profile occupation is {profile.occupation})"
                )

    # G. Targeted Subject Requirement (e.g. Inter-caste marriage)
    if intent.target_subject:
        if intent.target_subject == "inter_caste_marriage":
            if "inter_caste_marriage" not in target_subjects:
                disqualifications.append("Not an inter-caste marriage scheme")
        elif intent.target_subject == "disability":
            if "disability" not in target_subjects:
                disqualifications.append("Not a disability/PwD welfare scheme")

    # If any hard constraint was violated, mark as Ineligible
    if disqualifications:
        return SchemeMatchResult(
            scheme=scheme,
            match_status="ineligible",
            score=0.0,
            is_targeted_match=False,
            match_reasons=[],
            missing_requirements=[],
            disqualification_reasons=disqualifications,
        )

    # =========================================================================
    # 2. MISSING INFORMATION DETECTION (Potential Match vs Confirmed Eligible)
    # =========================================================================

    if scheme_income_limit is not None and profile.annual_income is None:
        missing_requirements.append(f"Annual family income must be ≤ ₹{scheme_income_limit:,.0f}")

    if props["is_caste_restricted"] and target_castes and not profile.caste:
        missing_requirements.append(f"Must belong to {', '.join(sorted(target_castes))} category with valid certificate")

    if props["is_occupation_restricted"] and "student" in target_occupations and not profile.occupation:
        missing_requirements.append("Must be an actively enrolled student in a recognized school/college")

    if "farmer" in target_occupations and not profile.occupation:
        missing_requirements.append("Must belong to a cultivable landholding farmer family")

    # Match status
    match_status = "potential_match" if missing_requirements else "eligible"

    # =========================================================================
    # 3. SOFT RELEVANCE SIGNALS & MULTI-FACTOR RANKING SCORE
    # =========================================================================
    score = 50.0 if match_status == "eligible" else 35.0
    is_targeted_match = False

    # State match scoring
    if active_user_state and active_user_state.lower() != "all india":
        if scheme_state.lower() == active_user_state.lower():
            score += 25.0
        elif scheme_state.lower() == "all india":
            score += 15.0
    else:
        if scheme_state.lower() == "all india":
            score += 15.0

    # Age match scoring
    if profile.age is not None:
        score += 10.0

    # Gender match scoring
    if scheme_gender != "All" and (profile.gender == scheme_gender or intent.target_gender == scheme_gender):
        score += 15.0

    # Caste / Social Category match scoring
    if target_castes and props["is_caste_restricted"]:
        if profile.caste and profile.caste.upper() in target_castes:
            score += 25.0
        elif intent.target_caste and intent.target_caste.upper() in target_castes:
            score += 25.0

    # Occupation match scoring
    if "student" in target_occupations and (profile.occupation == "student" or intent.target_occupation == "student"):
        score += 20.0
    elif "farmer" in target_occupations and (profile.occupation == "farmer" or intent.target_occupation == "farmer"):
        score += 20.0

    # Subject match scoring
    if "inter_caste_marriage" in target_subjects and intent.target_subject == "inter_caste_marriage":
        score += 35.0

    # =========================================================================
    # 4. MULTI-DIMENSIONAL TARGET INTENT CONJUNCTION CHECK
    # =========================================================================

    if intent.is_targeted:
        active_target_keys: List[str] = []
        matched_target_keys: List[str] = []

        if intent.target_caste:
            active_target_keys.append("caste")
            if intent.target_caste.upper() in target_castes and props["is_caste_restricted"]:
                matched_target_keys.append("caste")

        if intent.target_occupation:
            active_target_keys.append("occupation")
            if intent.target_occupation in target_occupations:
                matched_target_keys.append("occupation")

        if intent.target_gender:
            active_target_keys.append("gender")
            if scheme_gender.lower() == intent.target_gender.lower():
                matched_target_keys.append("gender")

        if intent.target_subject:
            active_target_keys.append("subject")
            if intent.target_subject in target_subjects:
                matched_target_keys.append("subject")

        if active_target_keys:
            if len(matched_target_keys) == len(active_target_keys):
                # Complete intersection: satisfies ALL requested target criteria!
                is_targeted_match = True
                score += 60.0
            elif len(matched_target_keys) > 0:
                # Partial match: matches some criteria but misses others (e.g. SC medical scheme for SC student query)
                is_targeted_match = False
                score += (15.0 * len(matched_target_keys)) - (25.0 * (len(active_target_keys) - len(matched_target_keys)))
            else:
                # Zero target match
                is_targeted_match = False
                score -= 40.0
    else:
        # For general queries, general schemes matching age/state receive standard scores
        if not props["is_caste_restricted"] and not props["is_occupation_restricted"]:
            score += 10.0
            is_targeted_match = True

    # =========================================================================
    # 5. DETERMINISTIC DATA-GROUNDED MATCH REASONS GENERATION
    # =========================================================================

    # State coverage
    if active_user_state and active_user_state.lower() != "all india":
        if scheme_state.lower() == active_user_state.lower():
            match_reasons.append(f"State coverage: {scheme_state} (State Scheme)")
        elif scheme_state.lower() == "all india":
            match_reasons.append("Central Scheme (All India coverage)")
    else:
        if scheme_state.lower() == "all india":
            match_reasons.append("Central Scheme (All India coverage)")
        else:
            match_reasons.append(f"State coverage: {scheme_state}")

    # Age
    if profile.age is not None and (scheme_min_age > 0 or scheme_max_age < 100):
        match_reasons.append(f"Age {profile.age} years satisfies eligible age range ({scheme_min_age}–{scheme_max_age} years)")

    # Gender - ONLY if scheme is specifically restricted to a gender
    if scheme_gender != "All" and (profile.gender == scheme_gender or intent.target_gender == scheme_gender):
        match_reasons.append(f"Specifically for {scheme_gender} beneficiaries")

    # Caste - ONLY if scheme is caste restricted or specifically targets caste
    if target_castes and props["is_caste_restricted"]:
        caste_label = "/".join(sorted(target_castes))
        if profile.caste and profile.caste.upper() in target_castes:
            match_reasons.append(f"Eligible for {profile.caste} category")
        elif intent.target_caste and intent.target_caste.upper() in target_castes:
            match_reasons.append(f"Targeted for {caste_label} category")

    # Occupation / Student - ONLY if scheme actually targets student/farmer and matches category
    if "student" in target_occupations and (scheme_category.lower() in ["education", "education & learning"] or "scholarship" in title_desc):
        if profile.occupation == "student" or intent.target_occupation == "student":
            match_reasons.append("Education & student scholarship assistance")
    elif "farmer" in target_occupations and scheme_category.lower() in ["agriculture", "rural & environment"]:
        if profile.occupation == "farmer" or intent.target_occupation == "farmer":
            match_reasons.append("Agriculture & farmer financial assistance")
    elif "self_employed" in target_occupations:
        if profile.occupation == "self_employed" or intent.target_occupation == "self_employed":
            match_reasons.append("Working capital & micro-credit for self-employed vendors")

    # Subject - ONLY if scheme category or topic actually matches
    if "inter_caste_marriage" in target_subjects:
        match_reasons.append("Financial incentive for inter-caste marriage integration")
    elif "health" in target_subjects and scheme_category.lower() in ["health", "health & wellness"]:
        match_reasons.append("Healthcare & medical treatment assistance")
    elif "housing" in target_subjects and scheme_category.lower() in ["housing", "social welfare"]:
        match_reasons.append("Housing subsidy for permanent pucca house")
    elif "disability" in target_subjects:
        match_reasons.append("Disability welfare & financial assistance")

    return SchemeMatchResult(
        scheme=scheme,
        match_status=match_status,
        score=max(score, 1.0),
        is_targeted_match=is_targeted_match,
        match_reasons=match_reasons,
        missing_requirements=missing_requirements,
        disqualification_reasons=[],
    )


def rank_and_filter_schemes(
    schemes: List[Dict[str, Any]],
    profile: MatchProfile,
    intent: MatchIntent,
    limit: int = 4,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Evaluates, ranks, and filters candidate schemes according to generalized matching principles.
    Returns:
    - Ranked list of matched scheme dictionaries (with match_score, match_reasons, match_status attached)
    - Total count of eligible / potential matching schemes
    """
    evaluated_results: List[SchemeMatchResult] = []

    for s in schemes:
        res = evaluate_scheme_match(s, profile, intent)
        if res.match_status != "ineligible":
            # If query is targeted, only include schemes that actually match the target
            # or exclude unrelated penalized schemes
            if intent.is_targeted and not res.is_targeted_match and res.score < 50.0:
                continue
            evaluated_results.append(res)

    # Sort by:
    # 1. is_targeted_match (True before False when query is targeted)
    # 2. match_status ("eligible" > "potential_match")
    # 3. score DESC
    status_weight = {"eligible": 2, "potential_match": 1, "ineligible": 0}

    def sort_key(r: SchemeMatchResult):
        target_weight = 1 if (intent.is_targeted and r.is_targeted_match) else 0
        return (
            -target_weight,
            -status_weight.get(r.match_status, 0),
            -r.score,
            r.scheme.get("id", "")
        )

    ranked_results = sorted(evaluated_results, key=sort_key)
    total_matches = len(ranked_results)

    # Attach match explanation metadata to scheme dictionaries
    output_schemes: List[Dict[str, Any]] = []
    for r in ranked_results[:limit]:
        s_copy = dict(r.scheme)
        s_copy["match_score"] = round(r.score, 1)
        s_copy["match_status"] = r.match_status
        s_copy["match_reasons"] = r.match_reasons
        s_copy["missing_requirements"] = r.missing_requirements
        output_schemes.append(s_copy)

    return output_schemes, total_matches


