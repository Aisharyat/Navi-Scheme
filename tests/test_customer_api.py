import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Add apps/api to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from src.main import app

client = TestClient(app)


import time

def test_customer_flow():
    test_email = f"citizen_{int(time.time())}@example.com"
    test_password = "CitizenPassword@123"

    print("\n--- 1. Testing Citizen Registration ---")
    reg_payload = {
        "email": test_email,
        "password": test_password,
        "full_name": "Rahul Sharma",
        "state": "Maharashtra",
        "age": 22,
        "gender": "Male",
        "annual_income": 180000,
        "category": "Education",
        "occupation": "Student",
    }

    reg_res = client.post("/api/user/auth/register", json=reg_payload)
    if reg_res.status_code != 201:
        # Might already exist from previous test run
        print(f"[INFO] Registration note ({reg_res.status_code}): {reg_res.text}")
    else:
        reg_data = reg_res.json()
        assert "access_token" in reg_data
        assert reg_data["role"] == "customer"
        print("[PASS] Citizen registration successful with profile preferences")

    print("\n--- 2. Testing Duplicate Email Registration Rejected ---")
    dup_res = client.post("/api/user/auth/register", json=reg_payload)
    assert dup_res.status_code == 400, f"Expected 400, got {dup_res.status_code}"
    print("[PASS] Duplicate registration correctly rejected with 400")

    print("\n--- 3. Testing Citizen Login ---")
    login_res = client.post(
        "/api/user/auth/login",
        json={"email": test_email, "password": test_password}
    )
    assert login_res.status_code == 200, f"Expected 200, got {login_res.status_code}: {login_res.text}"
    token_data = login_res.json()
    assert token_data["role"] == "customer"
    assert "access_token" in token_data
    token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("[PASS] Citizen login successful, JWT token issued")

    print("\n--- 4. Testing Get Citizen Profile ---")
    profile_res = client.get("/api/user/profile", headers=headers)
    assert profile_res.status_code == 200
    profile = profile_res.json()
    print("PROFILE RECEIVED IN TEST:", profile)
    assert profile["email"] == test_email
    assert profile["full_name"] == "Rahul Sharma"
    assert profile["role"] == "customer"
    assert profile["state"] == "Maharashtra"
    assert profile["age"] == 22
    assert profile["category"] == "Education"
    print(f"[PASS] Citizen profile fetched: {profile['full_name']} ({profile['state']}, {profile['age']} yrs)")

    print("\n--- 5. Testing Update Citizen Profile ---")
    update_res = client.put(
        "/api/user/profile",
        json={"age": 24, "state": "Karnataka", "category": "Housing"},
        headers=headers,
    )
    assert update_res.status_code == 200
    updated_profile = update_res.json()
    assert updated_profile["age"] == 24
    assert updated_profile["state"] == "Karnataka"
    assert updated_profile["category"] == "Housing"
    print("[PASS] Citizen profile update verified (State: Karnataka, Age: 24, Category: Housing)")

    print("\n--- 6. Testing Personalized Recommendations ---")
    rec_res = client.get("/api/user/recommended-schemes", headers=headers)
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    assert "schemes" in rec_data
    assert rec_data["citizen_profile"]["state"] == "Karnataka"
    assert rec_data["citizen_profile"]["age"] == 24
    print(f"[PASS] Personalized recommendations returned {rec_data['total_matched']} matching schemes for Karnataka/Age 24")

    print("\n--- 7. Testing Unauthenticated Access Blocked ---")
    unauth_res = client.get("/api/user/profile")
    assert unauth_res.status_code in (401, 403)
    print("[PASS] Unauthenticated citizen endpoint access blocked")

    print("\n=== ALL CITIZEN API TESTS PASSED SUCCESSFULLY! ===")


if __name__ == "__main__":
    test_customer_flow()
