import sys
import os

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("apps/api"))

from apps.api.src.services.ai_service import GroundedAIService
from apps.api.src.repositories.scheme_repository import SchemeRepository

def run():
    repo = SchemeRepository()
    ai = GroundedAIService()
    session_id = "test_multi_turn_session_99"

    print("=" * 60)
    print("STEP 1: User asks about AICTE Grant scheme")
    r1 = ai.process_conversational_turn(session_id, "AICTE - Grant For Augmenting Infrastructure In North Eastern Region", repo)
    print("REPLY 1:\n", r1["reply"])

    print("\n" + "=" * 60)
    print("STEP 2: User clicks '🎯 Check eligibility with my profile'")
    r2 = ai.process_conversational_turn(session_id, "🎯 Check eligibility with my profile", repo)
    print("REPLY 2:\n", r2["reply"])

    print("\n" + "=" * 60)
    print("STEP 3: User clicks '📝 Documents required'")
    r3 = ai.process_conversational_turn(session_id, "📝 Documents required", repo)
    print("REPLY 3:\n", r3["reply"])

    print("\n" + "=" * 60)
    print("STEP 4: User asks for loan EMI without interest rate")
    r4 = ai.process_conversational_turn(session_id, "Calculate EMI for 50000 for 2 years", repo)
    print("REPLY 4:\n", r4["reply"])

    print("\n" + "=" * 60)
    print("STEP 5: User responds with interest rate '7.5%'")
    r5 = ai.process_conversational_turn(session_id, "7.5%", repo)
    print("REPLY 5:\n", r5["reply"])

    print("\n" + "=" * 60)
    print("STEP 6: User asks directly with rate: 'Calculate EMI for 1 Lakh for 3 years at 8% interest'")
    r6 = ai.process_conversational_turn(session_id, "Calculate EMI for 1 Lakh for 3 years at 8% interest", repo)
    print("REPLY 6:\n", r6["reply"])

if __name__ == "__main__":
    run()
