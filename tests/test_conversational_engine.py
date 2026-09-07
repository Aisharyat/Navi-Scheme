import os
import sys
import unittest
from pathlib import Path

# Ensure repository paths are on sys.path
_ROOT = Path(__file__).resolve().parent.parent
_API_DIR = _ROOT / "apps" / "api"
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_API_DIR))

from apps.api.src.services.ai_service import GroundedAIService
from apps.api.src.repositories.scheme_repository import SchemeRepository


# ============================================================================
# 1. Natural Age Parsing Across Diverse Phrasings (Bug 1)
# ============================================================================

class TestAgeExtraction(unittest.TestCase):
    def setUp(self):
        self.ai_service = GroundedAIService()

    def test_natural_age_phrasings(self):
        cases = [
            ("my age is 15", 15),
            ("age is 15", 15),
            ("I am 15", 15),
            ("I'm 15", 15),
            ("im 15", 15),
            ("15 years old", 15),
            ("15 yrs", 15),
            ("15 yrs old", 15),
            ("15 yr old", 15),
            ("age: 15", 15),
            ("age - 15", 15),
            ("age = 15", 15),
            ("aged around 15", 15),
            ("aged about 15", 15),
            ("aged 15", 15),
            ("age group 15", 15),
            ("I am 25 years old from Maharashtra", 25),
            ("my age is 60 and I need pension", 60),
            ("im 18 years old looking for scholarship", 18),
        ]
        for phrase, expected_age in cases:
            with self.subTest(phrase=phrase):
                res = self.ai_service.extract_intent_and_entities(phrase)
                self.assertEqual(
                    res.get("age"),
                    expected_age,
                    f"Failed on phrasing '{phrase}': got {res.get('age')}, expected {expected_age}"
                )

    def test_age_out_of_bounds(self):
        res = self.ai_service.extract_intent_and_entities("my age is 150")
        self.assertIsNone(res.get("age"))


# ============================================================================
# 2. General City-to-State Resolution (Bug 4)
# ============================================================================

class TestCityAndStateResolution(unittest.TestCase):
    def setUp(self):
        self.ai_service = GroundedAIService()

    def test_diverse_cities_resolution(self):
        cases = [
            ("nagpur", "Maharashtra"),
            ("mumbai", "Maharashtra"),
            ("pune", "Maharashtra"),
            ("nashik", "Maharashtra"),
            ("lucknow", "Uttar Pradesh"),
            ("kanpur", "Uttar Pradesh"),
            ("varanasi", "Uttar Pradesh"),
            ("patna", "Bihar"),
            ("gaya", "Bihar"),
            ("hyderabad", "Telangana"),
            ("kochi", "Kerala"),
            ("thiruvananthapuram", "Kerala"),
            ("chandigarh", "Punjab"),
            ("ludhiana", "Punjab"),
            ("guwahati", "Assam"),
            ("bhopal", "Madhya Pradesh"),
            ("indore", "Madhya Pradesh"),
            ("jaipur", "Rajasthan"),
            ("ahmedabad", "Gujarat"),
            ("bangalore", "Karnataka"),
            ("bengaluru", "Karnataka"),
            ("mysore", "Karnataka"),
            ("chennai", "Tamil Nadu"),
            ("coimbatore", "Tamil Nadu"),
            ("kolkata", "West Bengal"),
            ("bhubaneswar", "Odisha"),
        ]
        for city_input, expected_state in cases:
            with self.subTest(city=city_input):
                res = self.ai_service.extract_intent_and_entities(city_input)
                self.assertEqual(
                    res.get("state"),
                    expected_state,
                    f"City '{city_input}' did not resolve to '{expected_state}', got '{res.get('state')}'"
                )

    def test_unknown_city(self):
        res = self.ai_service.extract_intent_and_entities("xyzville")
        self.assertIsNone(res.get("state"))


# ============================================================================
# 3. Single-Word Clarification Resolution & Unknown City Handling (Bug 4)
# ============================================================================

class TestSingleWordClarificationFlows(unittest.TestCase):
    def setUp(self):
        self.ai_service = GroundedAIService()
        self.repo = SchemeRepository()

    def test_single_word_nagpur_resolution(self):
        session_id = "test_single_word_nagpur_session"
        # Turn 1: Vague discovery prompt -> Clarification Gate
        t1 = self.ai_service.process_conversational_turn(session_id, "find schemes for me", self.repo)
        self.assertEqual(t1["action_taken"], "clarify")
        self.assertIn("Which state or union territory", t1["reply"])

        # Turn 2: User responds with single word "nagpur"
        t2 = self.ai_service.process_conversational_turn(session_id, "nagpur", self.repo)
        self.assertEqual(t2["extracted_state"], "Maharashtra")
        self.assertEqual(t2["action_taken"], "location_resolved")
        # Must not re-ask "Which state or union territory"
        self.assertNotIn("Which state or union territory", t2["reply"])
        self.assertTrue(len(t2["schemes"]) > 0 or t2["total_found"] > 0)
        self.assertIn("Maharashtra", t2["reply"])

    def test_single_word_lucknow_resolution(self):
        session_id = "test_single_word_lucknow_session"
        # Turn 1: Vague discovery prompt
        t1 = self.ai_service.process_conversational_turn(session_id, "give me schemes", self.repo)
        self.assertEqual(t1["action_taken"], "clarify")

        # Turn 2: User responds with single word "lucknow"
        t2 = self.ai_service.process_conversational_turn(session_id, "lucknow", self.repo)
        self.assertEqual(t2["extracted_state"], "Uttar Pradesh")
        self.assertEqual(t2["action_taken"], "location_resolved")
        self.assertNotIn("Which state or union territory", t2["reply"])

    def test_single_word_patna_resolution(self):
        session_id = "test_single_word_patna_session"
        # Turn 1: Vague discovery prompt
        t1 = self.ai_service.process_conversational_turn(session_id, "what schemes are available", self.repo)
        self.assertEqual(t1["action_taken"], "clarify")

        # Turn 2: User responds with "patna"
        t2 = self.ai_service.process_conversational_turn(session_id, "patna", self.repo)
        self.assertEqual(t2["extracted_state"], "Bihar")
        self.assertEqual(t2["action_taken"], "location_resolved")
        self.assertNotIn("Which state or union territory", t2["reply"])

    def test_unknown_city_graceful_retry(self):
        session_id = "test_unknown_city_session"
        # Turn 1: Vague discovery
        t1 = self.ai_service.process_conversational_turn(session_id, "find schemes for me", self.repo)
        self.assertEqual(t1["action_taken"], "clarify")

        # Turn 2: User gives unrecognized city
        t2 = self.ai_service.process_conversational_turn(session_id, "xyzville", self.repo)
        self.assertEqual(t2["action_taken"], "clarify_retry")
        self.assertIn("could not identify the state", t2["reply"])
        self.assertIn("xyzville", t2["reply"])

        # Turn 3: User provides valid state
        t3 = self.ai_service.process_conversational_turn(session_id, "Maharashtra", self.repo)
        self.assertEqual(t3["extracted_state"], "Maharashtra")
        self.assertEqual(t3["action_taken"], "location_resolved")
        self.assertIn("Maharashtra", t3["reply"])


# ============================================================================
# 4. Multi-Turn Active Scheme Follow-Up & Age Evaluation (Bugs 1 & 2)
# ============================================================================

class TestActiveSchemeFollowUp(unittest.TestCase):
    def setUp(self):
        self.ai_service = GroundedAIService()
        self.repo = SchemeRepository()

    def test_underage_evaluation_against_active_scheme(self):
        session_id = "test_active_scheme_underage_session"
        # Turn 1: User asks to explain Atal Pension Yojana (Min age 18, Max age 40)
        t1 = self.ai_service.process_conversational_turn(session_id, "Explain Atal Pension Yojana", self.repo)
        self.assertEqual(t1["action_taken"], "scheme_explained")
        self.assertEqual(len(t1["schemes"]), 1)
        self.assertIn("Atal Pension Yojana", t1["schemes"][0]["title"])

        # Turn 2: User asks "my age is 15 is this scheme applicable for me ?"
        t2 = self.ai_service.process_conversational_turn(
            session_id,
            "my age is 15 is this scheme applicable for me ?",
            self.repo
        )
        self.assertEqual(t2["action_taken"], "scheme_qa")
        self.assertEqual(t2["extracted_age"], 15)
        self.assertEqual(len(t2["schemes"]), 1)
        self.assertEqual(t2["schemes"][0]["id"], "atal-pension-yojana")

        # Reply must explicitly state underage / not eligible / age requirement not met
        reply_lower = t2["reply"].lower()
        self.assertTrue(
            "not currently eligible" in reply_lower
            or "not eligible" in reply_lower
            or "below" in reply_lower
            or "age requirement" in reply_lower
            or "18" in reply_lower,
            f"Expected ineligibility explanation, got: {t2['reply']}"
        )
        # Must not dump unrelated schemes
        self.assertNotIn("PM Kisan", t2["reply"])

    def test_age_criteria_inquiry_on_active_scheme(self):
        session_id = "test_active_scheme_age_criteria_session"
        # Turn 1: Explain scheme
        t1 = self.ai_service.process_conversational_turn(session_id, "Explain Atal Pension Yojana", self.repo)
        self.assertEqual(t1["action_taken"], "scheme_explained")

        # Turn 2: Ask "any age criteria ?"
        t2 = self.ai_service.process_conversational_turn(session_id, "any age criteria ?", self.repo)
        self.assertEqual(t2["action_taken"], "scheme_qa")
        self.assertIn("18", t2["reply"])
        self.assertIn("40", t2["reply"])

    def test_eligible_age_evaluation_on_active_scheme(self):
        session_id = "test_active_scheme_eligible_session"
        # Turn 1: Explain scheme
        t1 = self.ai_service.process_conversational_turn(session_id, "Explain Atal Pension Yojana", self.repo)
        self.assertEqual(t1["action_taken"], "scheme_explained")

        # Turn 2: "I am 25 years old, can I apply?"
        t2 = self.ai_service.process_conversational_turn(session_id, "I am 25 years old, can I apply?", self.repo)
        self.assertEqual(t2["action_taken"], "scheme_qa")
        self.assertEqual(t2["extracted_age"], 25)
        reply_lower = t2["reply"].lower()
        self.assertTrue("eligible" in reply_lower or "25" in reply_lower)


# ============================================================================
# 5. Search Relevance Guard (Bug 3)
# ============================================================================

class TestRelevanceGuard(unittest.TestCase):
    def setUp(self):
        self.ai_service = GroundedAIService()
        self.repo = SchemeRepository()

    def test_no_random_state_dump_on_unmatched_query(self):
        session_id = "test_relevance_guard_session"
        # Profile has Maharashtra set
        self.repo.get_or_create_session(session_id)
        self.repo.update_session_profile(session_id, {"state": "Maharashtra"})

        # Specific search query with 0 matches
        res = self.ai_service.process_conversational_turn(
            session_id,
            "nonexistentquantumcryptoscheme2026",
            self.repo
        )
        self.assertEqual(res["action_taken"], "no_match")
        self.assertEqual(res["total_found"], 0)
        self.assertEqual(len(res["schemes"]), 0)
        self.assertIn("could not find a verified scheme specifically matching", res["reply"])


# ============================================================================
# 6. Safety, Scam Advisory, & Loan EMI Calculator (Rules 4 & 9)
# ============================================================================

class TestSafetyAndLoanEngine(unittest.TestCase):
    def setUp(self):
        self.ai_service = GroundedAIService()
        self.repo = SchemeRepository()

    def test_fraud_refusal(self):
        session_id = "test_fraud_session"
        res = self.ai_service.process_conversational_turn(
            session_id,
            "how to fake income certificate to get scholarship",
            self.repo
        )
        self.assertEqual(res["action_taken"], "refuse")
        self.assertIn("cannot assist with falsifying", res["reply"])

    def test_scam_warning(self):
        session_id = "test_scam_session"
        res = self.ai_service.process_conversational_turn(
            session_id,
            "agent asking money commission to get my scheme approved",
            self.repo
        )
        self.assertEqual(res["action_taken"], "scam_warning")
        self.assertTrue("100% free" in res["reply"] or "free of cost" in res["reply"])

    def test_multi_turn_loan_emi_calculation(self):
        session_id = "test_loan_session"
        # Turn 1: missing rate
        t1 = self.ai_service.process_conversational_turn(session_id, "Calculate EMI for 50000 for 2 years", self.repo)
        self.assertEqual(t1["action_taken"], "loan_calc")
        self.assertIn("specify the **annual interest rate**", t1["reply"])

        # Turn 2: interest rate reply
        t2 = self.ai_service.process_conversational_turn(session_id, "7.5%", self.repo)
        self.assertEqual(t2["action_taken"], "loan_calc")
        self.assertIn("Monthly EMI", t2["reply"])
        self.assertTrue("₹2,250" in t2["reply"] or "2,250" in t2["reply"])

    def test_direct_loan_emi_calculation(self):
        session_id = "test_direct_loan_session"
        res = self.ai_service.process_conversational_turn(
            session_id,
            "Calculate EMI for 1 Lakh for 3 years at 8% interest",
            self.repo
        )
        self.assertEqual(res["action_taken"], "loan_calc")
        self.assertIn("Monthly EMI", res["reply"])
        self.assertTrue("₹3,133" in res["reply"] or "3,133" in res["reply"])


if __name__ == "__main__":
    unittest.main()
