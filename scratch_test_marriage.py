import sys
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent / "apps" / "api"))
from src.main import app

client = TestClient(app)

print("\n--- Testing 'Inter caste marriage' query ---")
res = client.post("/api/chat", json={"message": "Inter caste marriage", "state": "Maharashtra"})
data = res.json()

print(f"Extracted Caste:    {data.get('extracted_caste')}")
print(f"Extracted State:    {data.get('extracted_state')}")
print(f"Extracted Category: {data.get('extracted_category')}")
print(f"Total Matches:      {data.get('total_found')}")
print(f"\nSchemes Matched in DB:")
for s in data.get('schemes', []):
    print(f" • {s.get('title')} ({s.get('state')}) - {s.get('short_description')}")

print(f"\nAI GROUNDED RESPONSE:\n{data.get('reply')}\n")

