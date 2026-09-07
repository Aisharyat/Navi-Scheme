import sys
from pathlib import Path

# Add project root and API directory to sys.path
_ROOT = Path(__file__).resolve().parent.parent
_API_DIR = _ROOT / "apps" / "api"
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_API_DIR))

from packages.domain.models import EligibilityRule, EligibilityRuleSet
from packages.matching.engine import (
    evaluate_rule,
    evaluate_rule_set,
    assign_confidence,
    calculate_match_score,
    calculate_profile_completeness,
    rank_matches,
    explain_non_match,
)
from packages.ai.explain import (
    validate_ai_output,
    create_structured_fallback,
    MANDATORY_DISCLAIMER_EN,
    MANDATORY_DISCLAIMER_HI,
)
from src.repositories.scheme_repository import SchemeRepository
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


# ============================================================================
# 1. Matching Engine Unit Tests (§4 of Engineering Spec)
# ============================================================================

def test_evaluate_rule_operators():
    # eq
    r_eq = EligibilityRule(field="occupation", operator="eq", value="farmer")
    assert evaluate_rule(r_eq, {"occupation": "farmer"}) == "satisfied"
    assert evaluate_rule(r_eq, {"occupation": "student"}) == "violated"
    assert evaluate_rule(r_eq, {}) == "unknown"

    # in
    r_in = EligibilityRule(field="social_category", operator="in", value=["sc", "st", "obc"])
    assert evaluate_rule(r_in, {"social_category": "sc"}) == "satisfied"
    assert evaluate_rule(r_in, {"social_category": "general"}) == "violated"

    # lte & gte
    r_lte = EligibilityRule(field="age", operator="lte", value=10)
    assert evaluate_rule(r_lte, {"age": 8}) == "satisfied"
    assert evaluate_rule(r_lte, {"age": 15}) == "violated"

    r_gte = EligibilityRule(field="age", operator="gte", value=60)
    assert evaluate_rule(r_gte, {"age": 65}) == "satisfied"
    assert evaluate_rule(r_gte, {"age": 45}) == "violated"

    # between
    r_bet = EligibilityRule(field="age", operator="between", value=[18, 40])
    assert evaluate_rule(r_bet, {"age": 25}) == "satisfied"
    assert evaluate_rule(r_bet, {"age": 50}) == "violated"

    # state normalization ('All India' matches any state)
    r_state = EligibilityRule(field="state", operator="in", value=["All India"])
    assert evaluate_rule(r_state, {"state": "Maharashtra"}) == "satisfied"


def test_evaluate_rule_set_and_or():
    rule_set_and = {
        "logic": "AND",
        "rules": [
            {"field": "occupation", "operator": "eq", "value": "farmer", "required": True},
            {"field": "age", "operator": "gte", "value": 18, "required": True}
        ]
    }
    # Both satisfied
    res1 = evaluate_rule_set(rule_set_and, {"occupation": "farmer", "age": 30})
    assert res1["satisfied"] is True
    assert res1["violated"] is False
    assert assign_confidence(res1) == "high"

    # One violated
    res2 = evaluate_rule_set(rule_set_and, {"occupation": "student", "age": 30})
    assert res2["satisfied"] is False
    assert res2["violated"] is True
    assert assign_confidence(res2) == "not_eligible"

    # One unknown
    res3 = evaluate_rule_set(rule_set_and, {"occupation": "farmer"})
    assert res3["satisfied"] is False
    assert res3["violated"] is False
    assert assign_confidence(res3) == "medium"


def test_completeness_and_explainability():
    score = calculate_profile_completeness({
        "state": "Maharashtra",
        "age": 25,
        "gender": "male",
        "occupation": "student",
        "income_bracket": "1l_3l",
        "social_category": "obc"
    })
    assert score == 100

    rule_set = {
        "logic": "AND",
        "rules": [
            {"field": "age", "operator": "lte", "value": 10, "required": True}
        ]
    }
    non_match = explain_non_match(rule_set, {"age": 25})
    assert len(non_match["violated_criteria"]) == 1
    assert non_match["violated_criteria"][0]["field"] == "age"


# ============================================================================
# 2. AI Explanation Layer Guardrails Tests (§5 of Engineering Spec)
# ============================================================================

def test_ai_output_guardrails():
    scheme_facts = {
        "title": "PM Kisan",
        "application_url": "https://pmkisan.gov.in",
        "source_urls": ["https://pmkisan.gov.in", "https://agricoop.gov.in"]
    }

    # Valid output with correct URL
    valid_text = "Apply directly at https://pmkisan.gov.in to receive benefits."
    assert validate_ai_output(valid_text, scheme_facts) is True

    # Invalid output with unauthorized URL
    invalid_url_text = "Click here on https://fake-scam-portal.com to apply."
    assert validate_ai_output(invalid_url_text, scheme_facts) is False

    # Structured fallback test
    fallback = create_structured_fallback(scheme_facts, [{"satisfied": True, "rule_description": "Farmer with land"}], "en")
    assert MANDATORY_DISCLAIMER_EN in fallback.disclaimer
    assert "PM Kisan" in fallback.plain_language_summary


# ============================================================================
# 3. API Route Integration Tests (§6 of Engineering Spec)
# ============================================================================

def test_api_taxonomies():
    resp = client.get("/api/taxonomies")
    assert resp.status_code == 200
    data = resp.json()
    assert "states" in data
    assert "occupations" in data
    assert "categories" in data


def test_api_schemes_list_and_filter():
    resp = client.get("/api/schemes?category=Agriculture")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any("Kisan" in s["title"] for s in data["schemes"])


def test_api_eligibility_matching_endpoint():
    resp = client.post("/api/eligibility/match", json={
        "state": "Maharashtra",
        "age": 25,
        "gender": "female",
        "occupation": "homemaker",
        "income_bracket": "1l_3l",
        "sensitive_fields_consented": True
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_matches"] >= 1
    assert "profile_completeness_score" in data


def test_api_scheme_explain_endpoint():
    resp = client.post("/api/schemes/sukanya-samriddhi-yojana/explain", json={"language": "en"})
    assert resp.status_code == 200
    data = resp.json()
    assert "plain_language_summary" in data
    assert "disclaimer" in data


def test_api_chat_endpoint_grounding_and_scam_warning():
    # Regular query
    resp = client.post("/api/chat", json={"message": "I am a 20 year old student looking for scholarship"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["reply"]) > 0

    # Scam alert query
    resp_scam = client.post("/api/chat", json={"message": "Agent asking money commission to apply for my scheme"})
    assert resp_scam.status_code == 200
    assert "100% free" in resp_scam.json()["reply"] or "free of cost" in resp_scam.json()["reply"]


def test_api_admin_analytics():
    # Login as admin to get token
    login_resp = client.post("/api/admin/auth/login", json={
        "email": "admin@navischeme.gov.in",
        "password": "Admin@123"
    })
    token = login_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    resp = client.get("/api/admin/analytics", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "coverage" in data
    assert "accuracy" in data
    assert "engagement" in data
    assert "freshness" in data


def test_frontend_serving():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Navi Scheme" in resp.text
