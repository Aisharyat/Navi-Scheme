import sys
import os
import csv
import re
from pathlib import Path
from typing import Dict, Any, List

# Add apps/api to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))

from src.models.scheme import SchemeModel, Base
from src.repositories.alloydb import get_engine
from sqlalchemy.orm import Session


def slugify(text: str) -> str:
    """Generate a clean URL slug from scheme title."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def get_field_val(row: Dict[str, Any], possible_keys: List[str], default=None):
    """Find value in row matching any of the possible key variations (case-insensitive)."""
    normalized_row = {k.strip().lower().replace(" ", "_").replace("-", "_"): v for k, v in row.items() if k}
    for key in possible_keys:
        norm_key = key.strip().lower().replace(" ", "_").replace("-", "_")
        if norm_key in normalized_row and normalized_row[norm_key] is not None:
            val = str(normalized_row[norm_key]).strip()
            if val:
                return val
    return default


def parse_int_safe(val):
    if val is None:
        return None
    try:
        # Extract digits
        match = re.search(r"\d+", str(val))
        return int(match.group(0)) if match else None
    except Exception:
        return None


def import_csv(csv_path: str):
    path = Path(csv_path)
    if not path.exists():
        print(f"[ERROR] File not found: {csv_path}", file=sys.stderr)
        return False

    print(f"==================================================")
    print(f"       Importing CSV to Local Database            ")
    print(f"==================================================")
    print(f"CSV File: {path.resolve()}")

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    imported_count = 0
    updated_count = 0

    with open(path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("[ERROR] CSV file appears to be empty or has no header row.", file=sys.stderr)
            return False

        print(f"Detected columns: {', '.join(reader.fieldnames)}")

        with Session(engine) as session:
            for idx, row in enumerate(reader, 1):
                title = get_field_val(row, ["title", "scheme_name", "scheme", "name", "scheme_title"])
                if not title:
                    continue

                slug = get_field_val(row, ["slug", "code", "id"]) or slugify(title)
                short_desc = get_field_val(row, ["short_description", "summary", "description", "details", "about", "objective"]) or title
                desc = get_field_val(row, ["description", "detailed_description", "details", "about", "objective"]) or short_desc
                category = get_field_val(row, ["category", "sector", "type", "domain", "field"]) or "General Welfare"
                state = get_field_val(row, ["state", "state_name", "region", "location"]) or "All India"
                country = get_field_val(row, ["country", "nation"]) or "India"
                ministry = get_field_val(row, ["ministry", "department", "nodal_agency", "agency", "dept"]) or "Government of India"
                gender = get_field_val(row, ["target_gender", "gender", "beneficiary_gender"]) or "All"
                min_age = parse_int_safe(get_field_val(row, ["min_age", "minimum_age", "age_min", "age_from"]))
                max_age = parse_int_safe(get_field_val(row, ["max_age", "maximum_age", "age_max", "age_to"]))
                income_limit = parse_int_safe(get_field_val(row, ["income_limit", "income_ceiling", "income", "max_income"]))
                benefits = get_field_val(row, ["benefits", "benefit", "financial_assistance", "grant", "subsidy", "benefit_details"]) or "Financial and social assistance as per government guidelines."
                eligibility = get_field_val(row, ["eligibility_summary", "eligibility", "criteria", "eligibility_criteria", "who_can_apply"]) or f"Eligible residents of {state}."
                docs = get_field_val(row, ["documents_required", "documents", "docs", "required_documents", "checklist"]) or "Aadhaar Card, Bank Passbook, Identity & Address Proof."
                app_url = get_field_val(row, ["application_url", "url", "link", "official_website", "website", "apply_url", "portal"])
                app_proc = get_field_val(row, ["application_process", "how_to_apply", "process", "application_steps", "steps"]) or "Apply online via the official portal or visit nearest CSC/Gram Panchayat."

                # Check if scheme already exists in DB
                existing = session.query(SchemeModel).filter(SchemeModel.slug == slug).first()
                if existing:
                    existing.title = title
                    existing.short_description = short_desc
                    existing.description = desc
                    existing.category = category
                    existing.state = state
                    existing.country = country
                    existing.ministry = ministry
                    existing.target_gender = gender
                    existing.min_age = min_age
                    existing.max_age = max_age
                    existing.income_limit = income_limit
                    existing.benefits = benefits
                    existing.eligibility_summary = eligibility
                    existing.documents_required = docs
                    existing.application_url = app_url
                    existing.application_process = app_proc
                    updated_count += 1
                else:
                    new_scheme = SchemeModel(
                        slug=slug,
                        title=title,
                        short_description=short_desc,
                        description=desc,
                        category=category,
                        state=state,
                        country=country,
                        ministry=ministry,
                        target_gender=gender,
                        min_age=min_age,
                        max_age=max_age,
                        income_limit=income_limit,
                        benefits=benefits,
                        eligibility_summary=eligibility,
                        documents_required=docs,
                        application_url=app_url,
                        application_process=app_proc,
                        is_active=True
                    )
                    session.add(new_scheme)
                    imported_count += 1

            session.commit()

        print(f"\n[SUCCESS] Import complete!")
        print(f"  - New schemes inserted: {imported_count}")
        print(f"  - Existing schemes updated: {updated_count}")
        print(f"  - Total records in database: {imported_count + updated_count}")
        print(f"==================================================")
        return True


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_csv = sys.argv[1]
    else:
        # Check standard default locations
        candidates = [
            os.path.join("data", "schemes.csv"),
            os.path.join("data", "seeds", "schemes.csv"),
            "schemes.csv",
        ]
        target_csv = next((c for c in candidates if os.path.exists(c)), None)

    if not target_csv:
        print("Usage: python scripts/import_schemes_csv.py <path_to_your_file.csv>")
        print("\nOr place your CSV file in 'data/schemes.csv' or the root directory.")
        sys.exit(1)

    import_csv(target_csv)
