import math
from typing import Dict, Any, List, Optional, Tuple
from packages.domain.models import (
    EligibilityRule,
    EligibilityRuleSet,
    MatchedCriterion,
    EligibilityMatch,
    CitizenProfile,
    ConfidenceLevel,
)


def format_rule_description(rule: EligibilityRule) -> str:
    """Generate human-readable criteria description."""
    field_labels = {
        "state": "Residency in",
        "age": "Age",
        "gender": "Gender",
        "occupation": "Occupation",
        "income_bracket": "Annual Household Income",
        "social_category": "Social Category",
        "disability_status": "Person with Disability (PwD)",
        "marital_status": "Marital Status",
        "land_owned_hectares": "Agricultural Landholding",
        "education_level": "Education Level",
        "has_ration_card": "Ration Card Holder",
        "has_aadhaar_linked_bank": "Aadhaar Linked Bank Account",
    }
    label = field_labels.get(rule.field, rule.field.replace("_", " ").title())
    op = rule.operator
    val = rule.value

    if op == "eq":
        return f"{label} is {val}"
    elif op == "neq":
        return f"{label} is not {val}"
    elif op == "in":
        if isinstance(val, list):
            return f"{label} in ({', '.join(str(v) for v in val)})"
        return f"{label} in {val}"
    elif op == "not_in":
        return f"{label} not in ({', '.join(str(v) for v in val) if isinstance(val, list) else val})"
    elif op == "lte":
        return f"{label} ≤ {val}"
    elif op == "gte":
        return f"{label} ≥ {val}"
    elif op == "between":
        if isinstance(val, (list, tuple)) and len(val) == 2:
            return f"{label} between {val[0]} and {val[1]}"
        return f"{label} in range {val}"
    elif op == "exists":
        return f"{label} must be present"
    return f"{label} {op} {val}"


def evaluate_rule(rule: EligibilityRule, profile: Dict[str, Any]) -> str:
    """
    Evaluates a single rule against a profile.
    Returns: 'satisfied', 'violated', or 'unknown'
    """
    field_val = profile.get(rule.field)

    # Normalize special cases
    if field_val is None or field_val == "" or field_val == "prefer_not_to_say":
        return "unknown"

    op = rule.operator
    target = rule.value

    # Normalize state match: 'All India' matches any state
    if rule.field == "state":
        target_list = target if isinstance(target, list) else [target]
        normalized_targets = [str(s).lower() for s in target_list]
        if "all india" in normalized_targets or "all" in normalized_targets:
            return "satisfied"
        return "satisfied" if str(field_val).lower() in normalized_targets else "violated"

    # Normalize gender match: 'All' matches any gender
    if rule.field == "gender":
        target_list = target if isinstance(target, list) else [target]
        normalized_targets = [str(g).lower() for g in target_list]
        if "all" in normalized_targets:
            return "satisfied"
        return "satisfied" if str(field_val).lower() in normalized_targets else "violated"

    try:
        if op == "eq":
            return "satisfied" if str(field_val).lower() == str(target).lower() else "violated"
        elif op == "neq":
            return "satisfied" if str(field_val).lower() != str(target).lower() else "violated"
        elif op == "in":
            target_list = [str(x).lower() for x in target] if isinstance(target, list) else [str(target).lower()]
            return "satisfied" if str(field_val).lower() in target_list else "violated"
        elif op == "not_in":
            target_list = [str(x).lower() for x in target] if isinstance(target, list) else [str(target).lower()]
            return "satisfied" if str(field_val).lower() not in target_list else "violated"
        elif op == "lte":
            return "satisfied" if float(field_val) <= float(target) else "violated"
        elif op == "gte":
            return "satisfied" if float(field_val) >= float(target) else "violated"
        elif op == "between":
            if isinstance(target, (list, tuple)) and len(target) == 2:
                return "satisfied" if float(target[0]) <= float(field_val) <= float(target[1]) else "violated"
            return "violated"
        elif op == "exists":
            return "satisfied" if field_val is not None else "violated"
    except (ValueError, TypeError):
        return "violated"

    return "violated"


def evaluate_rule_set(rule_set: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively evaluate an EligibilityRuleSet.
    Handles nested groups, AND/OR logic.
    """
    logic = rule_set.get("logic", "AND").upper()
    rules_raw = rule_set.get("rules", [])
    groups_raw = rule_set.get("groups", [])

    results: List[MatchedCriterion] = []
    unknown_fields: List[str] = []
    outcomes: List[Dict[str, Any]] = []

    for r_raw in rules_raw:
        if isinstance(r_raw, EligibilityRule):
            r = r_raw
        else:
            r = EligibilityRule(
                field=r_raw.get("field", ""),
                operator=r_raw.get("operator", "eq"),
                value=r_raw.get("value"),
                required=r_raw.get("required", True),
            )

        outcome = evaluate_rule(r, profile)
        desc = format_rule_description(r)
        val = profile.get(r.field)
        criterion = MatchedCriterion(
            field=r.field,
            rule_description=desc,
            profile_value=val,
            satisfied=(outcome == "satisfied"),
        )
        results.append(criterion)

        if outcome == "unknown":
            if r.field not in unknown_fields:
                unknown_fields.append(r.field)

        outcomes.append({"outcome": outcome, "required": r.required, "field": r.field})

    # Evaluate nested groups
    for g_raw in groups_raw:
        sub_res = evaluate_rule_set(g_raw, profile)
        results.extend(sub_res["results"])
        for f in sub_res["unknown_fields"]:
            if f not in unknown_fields:
                unknown_fields.append(f)

        sub_outcome = "satisfied" if sub_res["satisfied"] else ("violated" if sub_res["violated"] else "unknown")
        outcomes.append({"outcome": sub_outcome, "required": True, "field": "group"})

    if logic == "AND":
        violated = any(o["outcome"] == "violated" and o["required"] for o in outcomes)
        satisfied = not violated and all(o["outcome"] == "satisfied" or not o["required"] for o in outcomes)
    else:  # OR
        violated = all(o["outcome"] == "violated" for o in outcomes) if outcomes else False
        satisfied = any(o["outcome"] == "satisfied" for o in outcomes) if outcomes else True

    return {
        "satisfied": satisfied,
        "violated": violated,
        "unknown_fields": unknown_fields,
        "results": results,
        "outcomes": outcomes,
    }


def assign_confidence(eval_res: Dict[str, Any]) -> ConfidenceLevel:
    """Assigns ConfidenceLevel strictly per the engineering specification."""
    if eval_res["violated"]:
        return "not_eligible"
    if eval_res["satisfied"] and len(eval_res["unknown_fields"]) == 0:
        return "high"
    if len(eval_res["unknown_fields"]) <= 2 and not eval_res["violated"]:
        return "medium"
    return "low"


def calculate_match_score(eval_res: Dict[str, Any]) -> int:
    """
    Score (0-100) for ranking:
    (satisfiedRequired / totalRequired) * 70 + (satisfiedOptional / totalOptional) * 30
    """
    outcomes = eval_res.get("outcomes", [])
    if not outcomes:
        return 50

    req_outcomes = [o for o in outcomes if o.get("required", True)]
    opt_outcomes = [o for o in outcomes if not o.get("required", True)]

    req_sat = sum(1 for o in req_outcomes if o["outcome"] == "satisfied")
    req_score = (req_sat / len(req_outcomes) * 70) if req_outcomes else 70

    opt_sat = sum(1 for o in opt_outcomes if o["outcome"] == "satisfied")
    opt_score = (opt_sat / len(opt_outcomes) * 30) if opt_outcomes else 30

    return int(round(req_score + opt_score))


def calculate_profile_completeness(profile: Dict[str, Any]) -> int:
    """Calculate profile completeness score (0-100)."""
    core_fields = [
        "state", "age", "gender", "occupation", "income_bracket", "social_category"
    ]
    answered = sum(1 for f in core_fields if profile.get(f) and profile.get(f) != "prefer_not_to_say")
    return int(round((answered / len(core_fields)) * 100))


def rank_matches(matches: List[EligibilityMatch]) -> List[EligibilityMatch]:
    """
    Sort by:
    1. Confidence weight (high=3, medium=2, low=1) DESC
    2. Score DESC
    3. Deadline ASC (nulls last)
    """
    weight_map = {"high": 3, "medium": 2, "low": 1, "not_eligible": 0}

    def sort_key(m: EligibilityMatch):
        conf_w = weight_map.get(m.confidence, 0)
        score = m.score
        deadline_val = m.deadline or "9999-12-31"
        return (-conf_w, -score, deadline_val)

    eligible_only = [m for m in matches if m.confidence != "not_eligible"]
    return sorted(eligible_only, key=sort_key)


def explain_non_match(rule_set: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Explain why a scheme didn't match a citizen profile."""
    eval_res = evaluate_rule_set(rule_set, profile)
    violated_criteria = [r for r in eval_res["results"] if not r.satisfied]
    return {
        "violated_criteria": [
            {
                "field": r.field,
                "description": r.rule_description,
                "current_value": r.profile_value,
            }
            for r in violated_criteria
        ],
        "missing_fields": eval_res["unknown_fields"],
    }
