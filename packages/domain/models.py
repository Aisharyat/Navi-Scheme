from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union, Literal

SchemeStatus = Literal["active", "upcoming", "closed", "under_review"]
IssuingLevel = Literal["central", "state"]
ConfidenceLevel = Literal["high", "medium", "low", "not_eligible"]
Occupation = Literal[
    "farmer", "student", "salaried", "self_employed",
    "unemployed", "homemaker", "retired", "daily_wage_informal"
]
SocialCategory = Literal["general", "obc", "sc", "st", "ews", "prefer_not_to_say"]
IncomeBracket = Literal["below_1l", "1l_3l", "3l_6l", "6l_10l", "above_10l", "prefer_not_to_say"]
Gender = Literal["male", "female", "other", "prefer_not_to_say", "all"]


@dataclass
class EligibilityRule:
    field: str
    operator: Literal["eq", "neq", "in", "not_in", "lte", "gte", "between", "exists"]
    value: Any
    required: bool = True


@dataclass
class EligibilityRuleSet:
    logic: Literal["AND", "OR"] = "AND"
    rules: List[EligibilityRule] = field(default_factory=list)
    groups: List["EligibilityRuleSet"] = field(default_factory=list)


@dataclass
class MatchedCriterion:
    field: str
    rule_description: str
    profile_value: Any
    satisfied: bool


@dataclass
class EligibilityMatch:
    scheme_id: str
    title: str
    confidence: ConfidenceLevel
    score: int
    matched_criteria: List[MatchedCriterion]
    missing_fields: List[str]
    benefits: str
    documents_required: List[str]
    application_url: str
    explanation: Optional[str] = None
    state: Optional[str] = None
    category: Optional[str] = None
    deadline: Optional[str] = None
    last_verified_at: Optional[str] = None


@dataclass
class CitizenProfile:
    id: Optional[str] = None
    user_id: Optional[str] = None
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
    completeness_score: int = 0
