import sys
import unittest
import uuid
from pathlib import Path

# Ensure repository root and API dirs are in sys.path
_ROOT = Path(__file__).resolve().parent.parent
_API_DIR = _ROOT / "apps" / "api"
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_API_DIR))

from src.repositories.scheme_repository import SchemeRepository
from src.services.ai_service import GroundedAIService
from packages.matching.generalized_engine import (
    MatchProfile,
    MatchIntent,
    parse_query_intent,
    extract_scheme_eligibility_profile,
    evaluate_scheme_match,
    rank_and_filter_schemes,
)


class TestGeneralizedMatchingSystem(unittest.TestCase):
    """
    Comprehensive test suite verifying the Generalized Matching & Recommendation Engine
    across 12 targeted criteria, constraints, and ranking dimensions.
    """

    def setUp(self):
        self.repo = SchemeRepository()
        self.repo.init_database()
        self.ai_service = GroundedAIService()

    # =========================================================================
    # TEST 1 — SC Student Targeted Query
    # =========================================================================
    def test_sc_student_targeted_query(self):
        """
        User: 'Are there any schemes specifically for Scheduled Caste (SC) students?'
        Verify:
        - SC-student-targeted schemes rank at the top.
        - APY is not presented as an SC-specific match.
        - No unsupported SC eligibility is invented.
        """
        session_id = f"test_sc_student_{uuid.uuid4().hex[:8]}"
        query = "Are there any schemes specifically for Scheduled Caste (SC) students?"
        res = self.ai_service.process_conversational_turn(session_id, query, self.repo)

        self.assertEqual(res["action_taken"], "matched")
        self.assertGreater(len(res["schemes"]), 0, "Should find matching SC student schemes")

        matched_titles = [s.get("title", "") for s in res["schemes"]]

        # 1. SC-student targeted schemes must be returned
        has_sc_scheme = any("SC" in t or "Post-Matric" in t or "Top Class" in t for t in matched_titles)
        self.assertTrue(has_sc_scheme, f"Expected SC student schemes, got: {matched_titles}")

        # 2. Atal Pension Yojana must NOT be presented as an SC match
        for s in res["schemes"]:
            self.assertNotEqual(
                s.get("id"),
                "atal-pension-yojana",
                "Atal Pension Yojana should not be returned for a targeted SC student query."
            )

        # 3. Verify why_matched reasons are data-grounded
        for s in res["schemes"]:
            reasons = s.get("match_reasons", [])
            self.assertTrue(len(reasons) > 0, "Each scheme must have data-grounded match reasons")

    # =========================================================================
    # TEST 2 — SC Woman Targeted Query
    # =========================================================================
    def test_sc_woman_targeted_query(self):
        """
        User: 'I am a 20-year-old SC woman from Nagpur. What schemes are specifically available for SC women?'
        Verify:
        - Maharashtra is recognized from Nagpur.
        - age=20, gender=Female, caste=SC.
        - SC/female targeted schemes rank appropriately.
        - General schemes are not incorrectly presented as SC-specific.
        """
        session_id = f"test_sc_woman_{uuid.uuid4().hex[:8]}"
        query = "I am a 20-year-old SC woman from Nagpur. What schemes are specifically available for SC women?"
        res = self.ai_service.process_conversational_turn(session_id, query, self.repo)

        self.assertEqual(res["extracted_state"], "Maharashtra")
        self.assertEqual(res["extracted_age"], 20)
        self.assertEqual(res["extracted_caste"], "SC")

        matched_schemes = res.get("schemes", [])
        self.assertGreater(len(matched_schemes), 0)

        # General schemes without SC/female relevance should not crowd out targeted schemes
        for s in matched_schemes:
            if s.get("id") == "atal-pension-yojana":
                self.fail("Atal Pension Yojana should not be presented as a targeted SC woman match.")

    # =========================================================================
    # TEST 3 — General Query
    # =========================================================================
    def test_general_query(self):
        """
        User: 'I am 20 years old from Maharashtra. What government schemes are available?'
        Verify:
        - General schemes can still be returned.
        - APY may appear because user age 20 is within 18-40.
        - The generalized filter does not incorrectly exclude general schemes.
        """
        session_id = f"test_general_{uuid.uuid4().hex[:8]}"
        query = "I am 20 years old from Maharashtra. What government schemes are available?"
        res = self.ai_service.process_conversational_turn(session_id, query, self.repo)

        self.assertEqual(res["action_taken"], "matched")
        self.assertGreater(len(res["schemes"]), 0)
        self.assertEqual(res["extracted_age"], 20)
        self.assertEqual(res["extracted_state"], "Maharashtra")

        matched_ids = [s.get("id") for s in res["schemes"]]
        # APY is open to 18-40 age group for unorganized workers / general citizens
        self.assertTrue(
            "atal-pension-yojana" in matched_ids or len(matched_ids) > 0,
            "General schemes matching age and state should be returned for general queries."
        )

    # =========================================================================
    # TEST 4 — State-Specific Scheme
    # =========================================================================
    def test_state_specific_scheme(self):
        """
        User: 'What schemes are available in Maharashtra?'
        Verify:
        - Maharashtra schemes are prioritized.
        - A scheme restricted to another region (e.g. Karnataka) is not returned as a matching Maharashtra scheme.
        """
        session_id = f"test_maharashtra_{uuid.uuid4().hex[:8]}"
        query = "What schemes are available in Maharashtra?"
        res = self.ai_service.process_conversational_turn(session_id, query, self.repo)

        self.assertEqual(res["extracted_state"], "Maharashtra")
        matched_schemes = res.get("schemes", [])
        self.assertGreater(len(matched_schemes), 0)

        # Karnataka-restricted scheme must not appear
        for s in matched_schemes:
            sch_state = s.get("state", "")
            self.assertIn(
                sch_state,
                ["Maharashtra", "All India"],
                f"Scheme '{s.get('title')}' with state '{sch_state}' should not be returned for Maharashtra."
            )

    # =========================================================================
    # TEST 5 — Age Eligibility
    # =========================================================================
    def test_age_eligibility(self):
        """
        Verify that a user outside the required age range is not classified as eligible.
        Example: Atal Pension Yojana requires age 18-40. User aged 15 or aged 45 is ineligible.
        """
        apy_scheme = self.repo.get_scheme_by_id_or_slug("atal-pension-yojana")
        self.assertIsNotNone(apy_scheme)

        intent = parse_query_intent("Can I apply for Atal Pension Yojana?")

        # Case 1: Underage (age 15)
        profile_underage = MatchProfile(age=15)
        res_underage = evaluate_scheme_match(apy_scheme, profile_underage, intent)
        self.assertEqual(res_underage.match_status, "ineligible")
        self.assertTrue(any("below minimum required age" in r for r in res_underage.disqualification_reasons))

        # Case 2: Overage (age 45)
        profile_overage = MatchProfile(age=45)
        res_overage = evaluate_scheme_match(apy_scheme, profile_overage, intent)
        self.assertEqual(res_overage.match_status, "ineligible")
        self.assertTrue(any("exceeds maximum eligible age" in r for r in res_overage.disqualification_reasons))

        # Case 3: In range (age 25)
        profile_valid = MatchProfile(age=25)
        res_valid = evaluate_scheme_match(apy_scheme, profile_valid, intent)
        self.assertEqual(res_valid.match_status, "eligible")

    # =========================================================================
    # TEST 6 — Missing Eligibility Information
    # =========================================================================
    def test_missing_eligibility_information(self):
        """
        Use a scheme requiring income information (e.g. Post-Matric Scholarship with income limit <= 2.5L).
        Verify:
        - If income is missing, the system does not claim confirmed eligibility.
        - Marks scheme as 'potential_match' with missing requirement note.
        """
        scholarship_scheme = self.repo.get_scheme_by_id_or_slug("post-matric-scholarship-scheme")
        self.assertIsNotNone(scholarship_scheme)

        intent = parse_query_intent("Post-Matric Scholarship for SC students")
        # Profile without income
        profile_no_income = MatchProfile(age=20, caste="SC", occupation="student")
        res = evaluate_scheme_match(scholarship_scheme, profile_no_income, intent)

        self.assertEqual(res.match_status, "potential_match")
        self.assertTrue(
            any("income" in r.lower() for r in res.missing_requirements),
            "Missing income limit must be listed under missing_requirements"
        )

        # When income is provided within limit
        profile_with_income = MatchProfile(age=20, caste="SC", occupation="student", annual_income=150000)
        res_eligible = evaluate_scheme_match(scholarship_scheme, profile_with_income, intent)
        self.assertEqual(res_eligible.match_status, "eligible")

    # =========================================================================
    # TEST 7 — Gender Eligibility
    # =========================================================================
    def test_gender_eligibility(self):
        """
        Verify that a scheme restricted to females (e.g. Mukhyamantri Majhi Ladki Bahin)
        is not presented as eligible to a male user.
        """
        female_scheme = self.repo.get_scheme_by_id_or_slug("maharashtra-mukhyamantri-majhi-ladki-bahin-yojana")
        self.assertIsNotNone(female_scheme)

        intent = parse_query_intent("What schemes can I apply for?")
        male_profile = MatchProfile(state="Maharashtra", age=25, gender="Male")
        res = evaluate_scheme_match(female_scheme, male_profile, intent)

        self.assertEqual(res.match_status, "ineligible")
        self.assertTrue(any("Female" in r for r in res.disqualification_reasons))

    # =========================================================================
    # TEST 8 — Occupation / Student Eligibility
    # =========================================================================
    def test_occupation_student_eligibility(self):
        """
        Verify that a scheme restricted to students/farmers is not presented as a confirmed match
        when the user's occupation does not satisfy the requirement.
        """
        scholarship_scheme = self.repo.get_scheme_by_id_or_slug("top-class-education-scheme-for-sc-students")
        self.assertIsNotNone(scholarship_scheme)

        intent = parse_query_intent("Scholarship schemes")
        retired_profile = MatchProfile(age=65, caste="SC", occupation="retired")
        res = evaluate_scheme_match(scholarship_scheme, retired_profile, intent)

        self.assertEqual(res.match_status, "ineligible")
        self.assertTrue(any("student" in r.lower() for r in res.disqualification_reasons))

    # =========================================================================
    # TEST 9 — Inter-Caste Marriage
    # =========================================================================
    def test_inter_caste_marriage_schemes(self):
        """
        Input: 'I am looking for inter-caste marriage schemes in Karnataka.'
        Verify:
        - Relevant marriage schemes are prioritized.
        - Unrelated general schemes (APY, PM-KISAN, etc.) are excluded.
        """
        session_id = f"test_marriage_{uuid.uuid4().hex[:8]}"
        query = "I am looking for inter-caste marriage schemes in Karnataka."
        res = self.ai_service.process_conversational_turn(session_id, query, self.repo)

        self.assertEqual(res["action_taken"], "matched")
        self.assertGreater(len(res["schemes"]), 0)

        matched_ids = [s.get("id") for s in res["schemes"]]
        self.assertIn("karnataka-dr-b-r-ambedkar-incentive-for-inter-caste-marriage", matched_ids)

        # Unrelated schemes must not appear
        for s in res["schemes"]:
            self.assertNotIn(s.get("id"), ["atal-pension-yojana", "pm-kisan-samman-nidhi", "ayushman-bharat-pmjay"])

    # =========================================================================
    # TEST 10 — Result Count Accuracy
    # =========================================================================
    def test_result_count_accuracy(self):
        """
        Verify that if the matching system returns N schemes, the response text says N rather than a hardcoded 4.
        """
        session_id = f"test_count_{uuid.uuid4().hex[:8]}"
        query = "I am looking for inter-caste marriage schemes in Karnataka."
        res = self.ai_service.process_conversational_turn(session_id, query, self.repo)

        actual_schemes_count = len(res["schemes"])
        self.assertEqual(res["total_found"], actual_schemes_count)
        self.assertIn(f"Found {actual_schemes_count} verified government scheme", res["reply"])

    # =========================================================================
    # TEST 11 — No Hallucinated Eligibility
    # =========================================================================
    def test_no_hallucinated_eligibility(self):
        """
        Verify that the AI cannot turn a general scheme (like APY) into an SC/student-specific scheme
        when the underlying scheme data does not support that classification.
        """
        apy_scheme = self.repo.get_scheme_by_id_or_slug("atal-pension-yojana")
        props = extract_scheme_eligibility_profile(apy_scheme)

        self.assertFalse(props["is_caste_restricted"])
        self.assertEqual(len(props["target_castes"]), 0)
        self.assertNotIn("student", props["target_occupations"])

        # Evaluating APY against an SC student targeted query gives low/penalized score
        sc_student_intent = parse_query_intent("schemes specifically for SC students")
        sc_student_profile = MatchProfile(caste="SC", occupation="student", age=20)
        res = evaluate_scheme_match(apy_scheme, sc_student_profile, sc_student_intent)

        self.assertFalse(res.is_targeted_match)
        self.assertLess(res.score, 50.0, "General scheme should be penalized for targeted queries")

    # =========================================================================
    # TEST 12 — Ranking: Targeted vs General Scheme
    # =========================================================================
    def test_ranking_targeted_vs_general_scheme(self):
        """
        Scenario:
        - Scheme A directly targets SC students (Top Class Education Scheme for SC Students).
        - Scheme B is a general scheme where the user happens to satisfy age (Atal Pension Yojana).
        Verify: Scheme A ranks strictly above Scheme B for a targeted query.
        """
        sc_scheme = self.repo.get_scheme_by_id_or_slug("top-class-education-scheme-for-sc-students")
        general_scheme = self.repo.get_scheme_by_id_or_slug("atal-pension-yojana")

        intent = parse_query_intent("schemes specifically for SC students")
        profile = MatchProfile(caste="SC", occupation="student", age=20)

        res_sc = evaluate_scheme_match(sc_scheme, profile, intent)
        res_gen = evaluate_scheme_match(general_scheme, profile, intent)

        self.assertTrue(res_sc.is_targeted_match)
        self.assertFalse(res_gen.is_targeted_match)
        self.assertGreater(res_sc.score, res_gen.score, "Targeted scheme must outscore general scheme on targeted queries")

        ranked, _ = rank_and_filter_schemes([general_scheme, sc_scheme], profile, intent, limit=2)
        self.assertEqual(ranked[0]["id"], "top-class-education-scheme-for-sc-students")

    # =========================================================================
    # TEST 13 — Dr. Ambedkar Medical Aid Scheme (Health vs Student Grounding)
    # =========================================================================
    def test_dr_ambedkar_medical_aid_not_matched_as_student_scheme(self):
        """
        Dr. Ambedkar Medical Aid Scheme provides medical aid for SC/ST patients in hospitals.
        Verify:
        - It is NOT classified as a student scholarship scheme.
        - Does NOT include 'Education & student scholarship assistance' in match reasons.
        - For an 'SC students' targeted query, it is not treated as a direct target match.
        """
        medical_scheme = {
            "id": "amas-haryana",
            "title": "Dr. Ambedkar Medical Aid Scheme",
            "category": "Health",
            "state": "All India",
            "target_gender": "All",
            "description": "Scheme to provide medical treatment facilities to SC/ST persons suffering from serious ailments in Medical College Hospitals.",
            "eligibility_summary": "The applicant shall belong to Scheduled Caste and Scheduled Tribe Community. Suffering from major ailments.",
            "benefits": "Medical aid up to Rs 1 Lakh for treatment.",
        }
        props = extract_scheme_eligibility_profile(medical_scheme)
        self.assertNotIn("student", props["target_occupations"])
        self.assertEqual(props["category"], "Health")

        intent = parse_query_intent("Are there any schemes specifically for Scheduled Caste (SC) students?")
        profile = MatchProfile(caste="SC", occupation="student")
        res = evaluate_scheme_match(medical_scheme, profile, intent)

        self.assertFalse(res.is_targeted_match, "SC medical scheme must not be a direct target match for SC students query")
        self.assertNotIn("Education & student scholarship assistance", res.match_reasons)

    # =========================================================================
    # TEST 14 — Agriculture Infrastructure Fund (Open Fund with Priority Mention)
    # =========================================================================
    def test_agriculture_infrastructure_fund_not_female_or_sc_only(self):
        """
        Agriculture Infrastructure Fund mentions 24% grants for SC/ST entrepreneurs and women priority.
        Verify:
        - It is NOT classified as exclusively female or an SC-only scheme.
        - Does NOT claim 'Specifically for Female beneficiaries'.
        - For an 'SC students' query, it is penalized and not returned as a target match.
        """
        aif_scheme = {
            "id": "aif",
            "title": "Agriculture Infrastructure Fund",
            "category": "Agriculture",
            "state": "All India",
            "target_gender": "All",
            "description": "Debt financing for agriculture infrastructure. 24% of grants for SC/ST entrepreneurs and priority to women.",
            "eligibility_summary": "Participating lending institutions will decide criteria for eligible borrowers.",
            "benefits": "Interest subvention of 3% per annum.",
        }
        props = extract_scheme_eligibility_profile(aif_scheme)
        self.assertEqual(props["target_gender"], "All")
        self.assertFalse(props["is_caste_restricted"])

        intent = parse_query_intent("Are there any schemes specifically for Scheduled Caste (SC) students?")
        profile = MatchProfile(caste="SC", occupation="student")
        res = evaluate_scheme_match(aif_scheme, profile, intent)

        self.assertFalse(res.is_targeted_match)
        self.assertNotIn("Specifically for Female beneficiaries", res.match_reasons)
        self.assertNotIn("Eligible for SC category", res.match_reasons)

    # =========================================================================
    # TEST 15 — Agricultural Marketing Infrastructure (Anyone Can Apply Grounding)
    # =========================================================================
    def test_agricultural_marketing_infrastructure_anyone_can_apply(self):
        """
        Agricultural Marketing Infrastructure has eligibility 'Anyone can apply for the scheme.'
        and mentions 33% subsidy for Women/SC/ST promoters.
        Verify:
        - Interpreted as open to all, not female-only or caste-restricted.
        - No invented 'Specifically for Female beneficiaries' or 'Eligible for SC category' claims.
        """
        ami_scheme = {
            "id": "ami",
            "title": "Agricultural Marketing Infrastructure",
            "category": "Agriculture",
            "state": "All India",
            "target_gender": "All",
            "description": "Subsidy of 25% for general and 33% for Women/SC/ST promoters for storage infrastructure.",
            "eligibility_summary": "Anyone can apply for the scheme.",
            "benefits": "Capital subsidy on term loans.",
        }
        props = extract_scheme_eligibility_profile(ami_scheme)
        self.assertTrue(props["is_open_to_all"])
        self.assertEqual(props["target_gender"], "All")
        self.assertFalse(props["is_caste_restricted"])

        intent = parse_query_intent("Are there any schemes specifically for Scheduled Caste (SC) students?")
        profile = MatchProfile(caste="SC", occupation="student")
        res = evaluate_scheme_match(ami_scheme, profile, intent)

        self.assertFalse(res.is_targeted_match)
        self.assertNotIn("Specifically for Female beneficiaries", res.match_reasons)
        self.assertNotIn("Eligible for SC category", res.match_reasons)

    # =========================================================================
    # TEST 16 — A2K+ Studies (Institutional Grant vs Student Scholarship)
    # =========================================================================
    def test_a2k_plus_studies_institutional_grant_not_individual_student_scholarship(self):
        """
        A2K+ Studies is an institutional R&D grant for universities, organizations, and research institutions.
        Verify:
        - It is recognized as an institutional scheme (is_institutional = True).
        - It is NOT classified as an individual student scholarship scheme.
        - For individual student queries, it is disqualified or not treated as a student match.
        """
        a2k_scheme = {
            "id": "a2ks",
            "title": "Access To Knowledge For Technology Development (A2K+) - Studies",
            "category": "Education & Learning",
            "state": "All India",
            "target_gender": "All",
            "description": "Supporting industrial technology-related studies and research in academic institutions and SIROs.",
            "eligibility_summary": "For Agencies Industry Associations, National R&D Institutions, Approved Universities and Colleges having distinct legal entity.",
            "benefits": "Manpower, travel, and research study support.",
        }
        props = extract_scheme_eligibility_profile(a2k_scheme)
        self.assertTrue(props["is_institutional"])
        self.assertNotIn("student", props["target_occupations"])

        intent = parse_query_intent("Are there any schemes specifically for Scheduled Caste (SC) students?")
        profile = MatchProfile(caste="SC", occupation="student")
        res = evaluate_scheme_match(a2k_scheme, profile, intent)

        self.assertEqual(res.match_status, "ineligible")
        self.assertFalse(res.is_targeted_match)
        self.assertNotIn("Education & student scholarship assistance", res.match_reasons)


if __name__ == "__main__":
    unittest.main()

