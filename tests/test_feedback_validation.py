import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure repository paths are on sys.path
_ROOT = Path(__file__).resolve().parent.parent
_API_DIR = _ROOT / "apps" / "api"
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_API_DIR))

from src.main import app

client = TestClient(app)


class TestFeedbackValidation(unittest.TestCase):
    def test_valid_feedback_types(self):
        for valid_type in ["match_feedback", "report_issue", "outcome"]:
            with self.subTest(feedback_type=valid_type):
                resp = client.post(
                    "/api/feedback",
                    json={
                        "scheme_id": "pm-kisan-samman-nidhi",
                        "type": valid_type,
                        "content": f"Test feedback content for {valid_type}"
                    }
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json()["status"], "ok")

    def test_invalid_feedback_type_rejected(self):
        resp = client.post(
            "/api/feedback",
            json={
                "scheme_id": "pm-kisan-samman-nidhi",
                "type": "invalid_feedback_type",
                "content": "Should fail with 422"
            }
        )
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()

