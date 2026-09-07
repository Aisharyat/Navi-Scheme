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

client = TestClient(app)


class TestAuthFlows(unittest.TestCase):
    def test_complete_auth_flows(self):
        unique_id = uuid.uuid4().hex[:6]
        test_email = f"auth_user_{unique_id}@example.com"
        initial_password = "InitialPassword@123"
        reset_new_password = "ResetPassword@456"
        changed_password = "ChangedPassword@789"

        # 1. Register a test citizen
        reg_res = client.post(
            "/api/user/auth/register",
            json={
                "email": test_email,
                "password": initial_password,
                "full_name": f"User {unique_id}",
                "state": "Maharashtra",
                "age": 28,
            }
        )
        self.assertEqual(reg_res.status_code, 201)
        initial_token = reg_res.json()["access_token"]

        # 2. Forgot Password Flow -> Request Reset Token
        forgot_res = client.post(
            "/api/user/auth/forgot-password",
            json={"email": test_email}
        )
        self.assertEqual(forgot_res.status_code, 200)
        reset_token = forgot_res.json().get("reset_token")
        self.assertIsNotNone(reset_token)

        # 3. Reset Password Flow -> Consume Token & Set New Password
        reset_res = client.post(
            "/api/user/auth/reset-password",
            json={"token": reset_token, "new_password": reset_new_password}
        )
        self.assertEqual(reset_res.status_code, 200)
        self.assertIn("successfully reset", reset_res.json()["message"].lower())

        # 4. Assert consumed reset token cannot be reused
        reuse_res = client.post(
            "/api/user/auth/reset-password",
            json={"token": reset_token, "new_password": "ShouldFailPassword@000"}
        )
        self.assertEqual(reuse_res.status_code, 400)

        # 5. Login with new password
        login_res = client.post(
            "/api/user/auth/login",
            json={"email": test_email, "password": reset_new_password}
        )
        self.assertEqual(login_res.status_code, 200)
        logged_in_token = login_res.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {logged_in_token}"}

        # 6. Change Password Flow (Authenticated)
        change_res = client.post(
            "/api/user/auth/change-password",
            json={"old_password": reset_new_password, "new_password": changed_password},
            headers=auth_headers,
        )
        self.assertEqual(change_res.status_code, 200)
        self.assertIn("changed successfully", change_res.json()["message"].lower())

        # Bad old password rejection
        bad_change = client.post(
            "/api/user/auth/change-password",
            json={"old_password": "WrongOldPassword@111", "new_password": "AnotherPassword@222"},
            headers=auth_headers,
        )
        self.assertEqual(bad_change.status_code, 400)

        # 7. Logout & Token Revocation Mechanism
        logout_res = client.post("/api/user/auth/logout", headers=auth_headers)
        self.assertEqual(logout_res.status_code, 200)

        # 8. Assert revoked token can no longer authenticate
        profile_res = client.get("/api/user/profile", headers=auth_headers)
        self.assertEqual(profile_res.status_code, 401)


if __name__ == "__main__":
    unittest.main()

