import sys
import unittest
import uuid
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure repository paths are on sys.path
_ROOT = Path(__file__).resolve().parent.parent
_API_DIR = _ROOT / "apps" / "api"
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_API_DIR))

from src.main import app
from src.repositories.scheme_repository import SchemeRepository

client = TestClient(app)


class TestChatSessionReset(unittest.TestCase):
    def setUp(self):
        self.repo = SchemeRepository()

    def test_session_profile_reset_lifecycle(self):
        session_id = f"test_reset_{uuid.uuid4().hex[:8]}"

        # 1. Establish session and set profile entities
        self.repo.get_or_create_session(session_id)
        self.repo.update_session_profile(session_id, {
            "state": "Maharashtra",
            "age": 25,
            "category": "Agriculture",
            "caste": "OBC",
            "annual_income": 150000,
        })

        # Confirm profile is accumulated
        profile_before = self.repo.get_session_profile(session_id)
        self.assertEqual(profile_before.get("state"), "Maharashtra")
        self.assertEqual(profile_before.get("age"), 25)
        self.assertEqual(profile_before.get("category"), "Agriculture")
        self.assertEqual(profile_before.get("caste"), "OBC")

        # 2. Call reset endpoint via POST /api/chat/{session_id}/reset
        reset_resp = client.post(f"/api/chat/{session_id}/reset")
        self.assertEqual(reset_resp.status_code, 200)
        self.assertEqual(reset_resp.json()["status"], "ok")

        # 3. Verify session profile is completely cleared
        profile_after = self.repo.get_session_profile(session_id)
        self.assertIsNone(profile_after.get("state"))
        self.assertIsNone(profile_after.get("age"))
        self.assertIsNone(profile_after.get("category"))
        self.assertIsNone(profile_after.get("caste"))
        self.assertIsNone(profile_after.get("annual_income"))

        # 4. Confirm a vague discovery query now triggers the state clarification gate
        chat_resp = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "find schemes for me"}
        )
        self.assertEqual(chat_resp.status_code, 200)
        chat_data = chat_resp.json()
        self.assertEqual(chat_data["action_taken"], "clarify")
        self.assertIn("Which state or union territory", chat_data["reply"])


if __name__ == "__main__":
    unittest.main()

