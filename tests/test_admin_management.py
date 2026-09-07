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


class TestAdminManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Authenticate as default seed admin
        login_res = client.post(
            "/api/admin/auth/login",
            json={"email": "admin@navischeme.gov.in", "password": "Admin@123"}
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        cls.headers = {"Authorization": f"Bearer {token}"}

    def test_admin_management_and_last_admin_protection(self):
        # 1. List current admins
        list_res = client.get("/api/admin/users", headers=self.headers)
        self.assertEqual(list_res.status_code, 200)
        admins = list_res.json()
        self.assertGreaterEqual(len(admins), 1)

        # 2. Create a secondary admin account
        unique_suffix = uuid.uuid4().hex[:6]
        new_admin_email = f"admin_{unique_suffix}@navischeme.gov.in"
        create_res = client.post(
            "/api/admin/users",
            json={
                "email": new_admin_email,
                "password": "AdminSecPassword@123",
                "full_name": f"Secondary Admin {unique_suffix}",
            },
            headers=self.headers,
        )
        self.assertEqual(create_res.status_code, 201)
        created_admin = create_res.json()
        new_admin_id = created_admin["id"]
        self.assertEqual(created_admin["role"], "admin")
        self.assertTrue(created_admin["is_active"])

        # 3. Deactivate the secondary admin
        deact_res = client.patch(
            f"/api/admin/users/{new_admin_id}/deactivate",
            headers=self.headers,
        )
        self.assertEqual(deact_res.status_code, 200)
        self.assertEqual(deact_res.json()["status"], "ok")

        # 4. Attempt to deactivate the sole remaining active admin -> must be blocked
        # Primary admin ID is 1 (or the one currently active)
        primary_admin = next((a for a in admins if a["is_active"]), None)
        self.assertIsNotNone(primary_admin)

        last_admin_deact_res = client.patch(
            f"/api/admin/users/{primary_admin['id']}/deactivate",
            headers=self.headers,
        )
        self.assertEqual(last_admin_deact_res.status_code, 400)
        self.assertIn("last remaining active administrator", last_admin_deact_res.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()

