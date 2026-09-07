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


class TestAdminSchemeLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Authenticate as admin to obtain JWT
        login_res = client.post(
            "/api/admin/auth/login",
            json={"email": "admin@navischeme.gov.in", "password": "Admin@123"}
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        cls.headers = {"Authorization": f"Bearer {token}"}

    def test_scheme_full_lifecycle(self):
        unique_suffix = uuid.uuid4().hex[:6]
        scheme_payload = {
            "name": f"Solar Rooftop Subsidy {unique_suffix}",
            "title": f"Solar Rooftop Subsidy {unique_suffix}",
            "issuing_level": "central",
            "issuing_body": "Ministry of New and Renewable Energy",
            "ministry": "Ministry of New and Renewable Energy",
            "state": "Maharashtra",
            "sector": "housing",
            "category": "Housing",
            "target_gender": "All",
            "min_age": 18,
            "max_age": 80,
            "description": "Clean energy rooftop scheme",
            "benefits": "₹30,000 direct subsidy for solar installation",
            "eligibility_summary": "Residential building owners with rooftop access",
            "eligibility_rules": {
                "logic": "AND",
                "rules": [
                    {"field": "age", "operator": "gte", "value": 18, "required": True}
                ]
            },
            "documents_required": ["Aadhaar Card", "Electricity Bill"],
            "application_steps": ["Register on solar portal", "Upload bills", "Get subsidy"],
            "application_url": "https://solarrooftop.gov.in",
        }

        # 1. CREATE scheme -> status is 'under_review'
        create_res = client.post("/api/admin/schemes", json=scheme_payload, headers=self.headers)
        self.assertEqual(create_res.status_code, 200)
        created = create_res.json()
        scheme_id = created["id"]
        self.assertEqual(created["status"], "under_review")

        # 2. EDIT scheme via PATCH /api/admin/schemes/{id}
        patch_res = client.patch(
            f"/api/admin/schemes/{scheme_id}",
            json={"benefits": "₹45,000 direct solar rooftop subsidy"},
            headers=self.headers,
        )
        self.assertEqual(patch_res.status_code, 200)
        updated = patch_res.json()["scheme"]
        self.assertIn("45,000", updated["benefits"])

        # 3. PUBLISH scheme -> status becomes 'active'
        pub_res = client.post(f"/api/admin/schemes/{scheme_id}/publish", headers=self.headers)
        self.assertEqual(pub_res.status_code, 200)
        self.assertEqual(pub_res.json()["status"], "ok")

        # Confirm scheme is listed in active catalog
        get_res = client.get(f"/api/schemes/{scheme_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["status"], "active")

        # 4. UNPUBLISH scheme -> reverts status to 'under_review'
        unpub_res = client.post(f"/api/admin/schemes/{scheme_id}/unpublish", headers=self.headers)
        self.assertEqual(unpub_res.status_code, 200)
        self.assertEqual(unpub_res.json()["status"], "ok")

        # 5. ARCHIVE scheme -> sets status to 'archived'
        arch_res = client.post(f"/api/admin/schemes/{scheme_id}/archive", headers=self.headers)
        self.assertEqual(arch_res.status_code, 200)
        self.assertEqual(arch_res.json()["status"], "ok")

        # 6. Test state and category query filters on list_admin_schemes
        filter_res = client.get(
            "/api/admin/schemes?state=Maharashtra&category=Housing",
            headers=self.headers,
        )
        self.assertEqual(filter_res.status_code, 200)
        filter_data = filter_res.json()
        self.assertIn("schemes", filter_data)
        self.assertIn("total", filter_data)


if __name__ == "__main__":
    unittest.main()

