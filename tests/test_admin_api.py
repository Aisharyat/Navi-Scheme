import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Add apps/api to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from src.main import app

client = TestClient(app)


def test_admin_flow():
    print("\n--- 1. Testing Invalid Admin Login ---")
    bad_login = client.post(
        "/api/admin/auth/login",
        json={"email": "wrong@navischeme.gov.in", "password": "BadPassword"}
    )
    assert bad_login.status_code == 401, f"Expected 401, got {bad_login.status_code}"
    print("[PASS] Invalid login correctly rejected with 401")

    print("\n--- 2. Testing Valid Admin Login ---")
    login_res = client.post(
        "/api/admin/auth/login",
        json={"email": "admin@navischeme.gov.in", "password": "Admin@123"}
    )
    assert login_res.status_code == 200, f"Expected 200, got {login_res.status_code}: {login_res.text}"
    token_data = login_res.json()
    assert "access_token" in token_data, "access_token not found in response"
    assert token_data["role"] == "admin"
    token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("[PASS] Valid login successful, JWT token issued")

    print("\n--- 3. Testing Protected /api/admin/auth/me ---")
    me_res = client.get("/api/admin/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "admin"
    assert me_res.json()["email"] == "admin@navischeme.gov.in"
    print("[PASS] Admin profile verified")

    print("\n--- 4. Testing Admin Stats ---")
    stats_res = client.get("/api/admin/stats", headers=headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_schemes"] >= 10
    assert stats["active_schemes"] >= 1
    assert "categories" in stats
    assert "states" in stats
    print(f"[PASS] Stats verified: Total schemes={stats['total_schemes']}, Active={stats['active_schemes']}")

    print("\n--- 5. Testing Create Scheme (POST /api/admin/schemes) ---")
    new_scheme_payload = {
        "title": "National Green Energy Solar Subsidy Scheme",
        "short_description": "Direct subsidy of up to 40% on residential rooftop solar panel installation.",
        "description": "Ministry of New and Renewable Energy initiative to drive renewable solar power adoption across all states.",
        "ministry": "Ministry of New and Renewable Energy",
        "state": "All India",
        "category": "Housing",
        "target_gender": "All",
        "min_age": 18,
        "max_age": 80,
        "benefits": "Rs 30,000 to 78,000 direct DBT subsidy credited directly to consumer bank account.",
        "eligibility_summary": "Indian citizen owning residential rooftop space with grid-connected electricity connection.",
        "documents_required": "Electricity bill, Property papers, Aadhaar Card, Bank passbook.",
        "application_url": "https://pmsuryaghar.gov.in",
        "application_process": "Apply on PM Surya Ghar portal with consumer number and upload rooftop verification.",
        "is_active": True,
    }

    create_res = client.post("/api/admin/schemes", json=new_scheme_payload, headers=headers)
    assert create_res.status_code == 201, f"Expected 201, got {create_res.status_code}: {create_res.text}"
    created = create_res.json()["scheme"]
    created_id = created["id"]
    print(f"[PASS] Scheme created successfully with ID: {created_id}, slug: {created['slug']}")

    print("\n--- 6. Testing List Schemes with Admin Filter ---")
    list_res = client.get("/api/admin/schemes?q=Green+Energy", headers=headers)
    assert list_res.status_code == 200
    schemes_data = list_res.json()
    assert schemes_data["total"] >= 1
    print(f"[PASS] Admin search returned {schemes_data['total']} matching records")

    print("\n--- 7. Testing Update Scheme (PUT /api/admin/schemes/{id}) ---")
    update_res = client.put(
        f"/api/admin/schemes/{created_id}",
        json={"benefits": "Updated Rs 40,000 to 85,000 direct DBT subsidy."},
        headers=headers,
    )
    assert update_res.status_code == 200
    updated = update_res.json()["scheme"]
    assert "85,000" in updated["benefits"]
    print("[PASS] Scheme update verified")

    print("\n--- 8. Testing Toggle Scheme Status (PATCH /api/admin/schemes/{id}/toggle-status) ---")
    toggle_res = client.patch(f"/api/admin/schemes/{created_id}/toggle-status", headers=headers)
    assert toggle_res.status_code == 200
    assert toggle_res.json()["scheme"]["is_active"] is False
    print("[PASS] Scheme status toggled to Inactive")

    print("\n--- 9. Testing Public API Reflects State ---")
    public_res = client.get("/api/schemes?q=Green+Energy")
    assert public_res.status_code == 200
    # Inactive schemes are excluded from citizen view
    assert public_res.json()["total"] == 0, "Inactive scheme should not appear in public query"
    print("[PASS] Inactive scheme correctly hidden from citizen search")

    print("\n--- 10. Testing Delete Scheme (DELETE /api/admin/schemes/{id}) ---")
    del_res = client.delete(f"/api/admin/schemes/{created_id}", headers=headers)
    assert del_res.status_code == 200
    print("[PASS] Scheme deleted successfully")

    print("\n--- 11. Testing Unauthenticated Request Rejected ---")
    unauth_res = client.post("/api/admin/schemes", json=new_scheme_payload)
    assert unauth_res.status_code in (401, 403), f"Expected 401/403, got {unauth_res.status_code}"
    print("[PASS] Unauthenticated access safely blocked")

    print("\n=== ALL ADMIN API TESTS PASSED SUCCESSFULLY! ===")


if __name__ == "__main__":
    test_admin_flow()

