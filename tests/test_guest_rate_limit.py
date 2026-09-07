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
from src.config.settings import get_settings

client = TestClient(app)


class TestGuestRateLimit(unittest.TestCase):
    def test_guest_rate_limit_exceeded(self):
        settings = get_settings()
        limit = settings.guest_chat_limit  # default 5
        session_id = f"test_guest_limit_{uuid.uuid4().hex[:8]}"

        # Send 'limit' messages as unauthenticated guest
        for i in range(1, limit + 1):
            resp = client.post(
                "/api/chat",
                json={"session_id": session_id, "message": f"Hello turn {i}"}
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["messages_used"], i)
            self.assertEqual(data["free_messages_limit"], limit)
            if i < limit:
                self.assertFalse(data["requires_auth"])

        # Send (limit + 1)th message -> must hit rate limit cap
        resp_blocked = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "One more message after limit"}
        )
        self.assertEqual(resp_blocked.status_code, 200)
        data_blocked = resp_blocked.json()
        self.assertEqual(data_blocked["action_taken"], "auth_required")
        self.assertTrue(data_blocked["requires_auth"])
        self.assertEqual(data_blocked["free_messages_limit"], limit)
        self.assertIn("reached your", data_blocked["reply"].lower())
        self.assertIn("free messages limit", data_blocked["reply"].lower())
        self.assertEqual(len(data_blocked["schemes"]), 0)


if __name__ == "__main__":
    unittest.main()

