import re
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import or_, and_, select
from sqlalchemy.orm import Session

from src.models.scheme import SchemeModel, Base, SchemeResponse, SchemeCreateRequest, SchemeUpdateRequest
from src.repositories.alloydb import get_engine


# Canonical Seed Schemes for Central & State Welfare
DEFAULT_SEED_SCHEMES = [
    {
        "slug": "sukanya-samriddhi-yojana",
        "title": "Sukanya Samriddhi Yojana (SSY)",
        "short_description": "High-interest savings account for girl children under 10 years.",
        "description": "A government-backed savings scheme targeted at the parents of girl children under the Beti Bachao Beti Padhao campaign, offering high tax-free interest and maturity benefits for higher education and marriage.",
        "ministry": "Ministry of Finance",
        "state": "All India",
        "country": "India",
        "category": "Women & Child",
        "target_gender": "Female",
        "min_age": 0,
        "max_age": 10,
        "income_limit": None,
        "benefits": "8.2% annual compounded interest, triple tax exemption (80C, interest, maturity).",
        "eligibility_summary": "Girl child must be an Indian citizen, below 10 years of age. Max 2 accounts per family.",
        "documents_required": "Girl child birth certificate, Identity proof of guardian (Aadhaar/PAN), Address proof.",
        "application_url": "https://www.indiapost.gov.in/Financial/Pages/Content/SSY.aspx",
        "application_process": "Visit any Post Office or authorized commercial bank branch with required KYC documents and initial deposit.",
    },
    {
        "slug": "post-matric-scholarship-scheme",
        "title": "Post-Matric Scholarship for SC/ST/OBC/EBC",
        "short_description": "Financial assistance for students pursuing post-matriculation or post-secondary education.",
        "description": "Centrally sponsored scholarship providing maintenance allowance, reimbursement of compulsory non-refundable fees, study tour charges, and book grants for students enrolled in recognized higher education courses.",
        "ministry": "Ministry of Social Justice and Empowerment",
        "state": "All India",
        "country": "India",
        "category": "Education",
        "target_gender": "All",
        "min_age": 15,
        "max_age": 35,
        "income_limit": 250000,
        "benefits": "100% course fee reimbursement plus monthly maintenance stipend (up to ₹13,500/yr).",
        "eligibility_summary": "Enrolled in class 11, 12, ITI, Diploma, Graduation, or Post-Graduation. Family annual income <= ₹2.5 Lakh.",
        "documents_required": "Caste certificate, Income certificate, Previous marksheet, College fee receipt, Aadhaar card, Bank passbook.",
        "application_url": "https://scholarships.gov.in",
        "application_process": "Register on National Scholarship Portal (NSP), submit student KYC, select scheme, and get institute verification.",
    },
    {
        "slug": "ayushman-bharat-pmjay",
        "title": "Ayushman Bharat - PM Jan Arogya Yojana (PM-JAY)",
        "short_description": "Cashless health insurance coverage of up to ₹5 Lakh per family per year.",
        "description": "World's largest government-funded health assurance scheme providing secondary and tertiary hospital care coverage across empanelled public and private hospitals across India.",
        "ministry": "Ministry of Health and Family Welfare",
        "state": "All India",
        "country": "India",
        "category": "Health",
        "target_gender": "All",
        "min_age": 0,
        "max_age": 120,
        "income_limit": 300000,
        "benefits": "Cashless in-patient hospitalization up to ₹5,00,000 per family annually covering 1,949+ medical procedures.",
        "eligibility_summary": "Families listed in SECC 2011 database or eligible under state ration card / RSBY criteria. Senior citizens aged 70+ now eligible regardless of income.",
        "documents_required": "Aadhaar Card, Ration Card, Active Mobile number.",
        "application_url": "https://beneficiary.nha.gov.in",
        "application_process": "Check eligibility online on NHA portal or visit nearest CSC/Empanelled Hospital for Ayushman Card generation.",
    },
    {
        "slug": "pradhan-mantri-awas-yojana-urban-rural",
        "title": "Pradhan Mantri Awas Yojana (PMAY)",
        "short_description": "Financial subsidy and assistance to build or purchase a pucca permanent house.",
        "description": "Flagship housing scheme providing interest subsidies and direct financial assistance to Economically Weaker Sections (EWS), Low Income Groups (LIG), and Middle Income Groups (MIG) for constructing pucca houses.",
        "ministry": "Ministry of Housing and Urban Affairs",
        "state": "All India",
        "country": "India",
        "category": "Housing",
        "target_gender": "All",
        "min_age": 18,
        "max_age": 70,
        "income_limit": 600000,
        "benefits": "Direct grant of ₹1.2 Lakh to ₹2.67 Lakh interest subsidy on home loan under Credit Linked Subsidy.",
        "eligibility_summary": "Beneficiary family must not own a pucca house anywhere in India. Female ownership or co-ownership mandatory.",
        "documents_required": "Aadhaar, Income proof, Property papers / land records, Bank statement, Affidavit of no pucca house.",
        "application_url": "https://pmaymis.gov.in",
        "application_process": "Apply via CSC centre or online on PMAYMIS portal under Citizen Assessment.",
    },
    {
        "slug": "atal-pension-yojana",
        "title": "Atal Pension Yojana (APY)",
        "short_description": "Guaranteed monthly pension of ₹1,000 to ₹5,000 after reaching 60 years of age.",
        "description": "A voluntary government co-contributed retirement scheme for unorganized sector workers providing guaranteed monthly pension lifelong upon turning 60 years of age.",
        "ministry": "Ministry of Finance",
        "state": "All India",
        "country": "India",
        "category": "Pension",
        "target_gender": "All",
        "min_age": 18,
        "max_age": 40,
        "income_limit": None,
        "benefits": "Guaranteed monthly pension (₹1,000, ₹2,000, ₹3,000, ₹4,000, or ₹5,000) for life. Return of corpus to nominee upon death.",
        "eligibility_summary": "Indian citizen aged between 18 and 40 years holding a savings bank or post office account. Must not be income taxpayer.",
        "documents_required": "Savings Bank Account details, Aadhaar Card, Nominee details.",
        "application_url": "https://enps.nsdl.com",
        "application_process": "Visit your bank branch or enroll directly via NetBanking / eNPS portal.",
    },
    {
        "slug": "pm-kisan-samman-nidhi",
        "title": "PM Kisan Samman Nidhi (PM-KISAN)",
        "short_description": "Direct income support of ₹6,000 per year in three equal installments to farmer families.",
        "description": "Central sector scheme providing income support of ₹6,000/year directly transferred into bank accounts of all landholding farmer families across India.",
        "ministry": "Ministry of Agriculture and Farmers Welfare",
        "state": "All India",
        "country": "India",
        "category": "Agriculture",
        "target_gender": "All",
        "min_age": 18,
        "max_age": 85,
        "income_limit": None,
        "benefits": "₹6,000 annually paid in 3 quarterly installments of ₹2,000 directly via DBT into bank account.",
        "eligibility_summary": "Small and marginal farmers with cultivable landholding in their name. Institutional landholders excluded.",
        "documents_required": "Land record ownership documents (7/12, Khasra/Khatauni), Aadhaar, Bank passbook with eKYC.",
        "application_url": "https://pmkisan.gov.in",
        "application_process": "Self-register on PM-KISAN portal under 'Farmers Corner' or visit local CSC center.",
    },
    {
        "slug": "maharashtra-sanjay-gandhi-niradhar",
        "title": "Sanjay Gandhi Niradhar Anudan Yojana (Maharashtra)",
        "short_description": "Monthly financial pension for destitute persons, elderly, widows, and disabled in Maharashtra.",
        "description": "Maharashtra state government welfare initiative offering monthly subsistence financial assistance to destitute senior citizens, widows, orphan children, and persons with >40% disability.",
        "ministry": "Social Justice & Special Assistance Dept, Maharashtra",
        "state": "Maharashtra",
        "country": "India",
        "category": "Social Welfare",
        "target_gender": "All",
        "min_age": 18,
        "max_age": 100,
        "income_limit": 21000,
        "benefits": "₹1,500 monthly financial pension transferred directly into beneficiary bank account.",
        "eligibility_summary": "Resident of Maharashtra for at least 15 years. Annual family income <= ₹21,000. Destitute, widow, or disabled.",
        "documents_required": "Maharashtra Domicile certificate, Age proof, Income certificate, Disability/Death certificate (if applicable).",
        "application_url": "https://aaplesarkar.mahaonline.gov.in",
        "application_process": "Apply online at Aaple Sarkar portal or submit physical application to Taluka Tehsildar office.",
    },
    {
        "slug": "ladli-behna-yojana-mp",
        "title": "Mukhyamantri Ladli Behna Yojana (Madhya Pradesh)",
        "short_description": "Direct monthly financial allowance of ₹1,250 for eligible women in Madhya Pradesh.",
        "description": "State welfare scheme aimed at women empowerment, nutritional health, and economic self-reliance for married, widowed, and destitute women in Madhya Pradesh.",
        "ministry": "Women and Child Development, MP",
        "state": "Madhya Pradesh",
        "country": "India",
        "category": "Women & Child",
        "target_gender": "Female",
        "min_age": 21,
        "max_age": 60,
        "income_limit": 250000,
        "benefits": "₹1,250 deposited every month on the 10th directly into the woman's bank account.",
        "eligibility_summary": "Resident of Madhya Pradesh, age 21 to 60 years. Family income <= ₹2.5 Lakh/yr, family landholding <= 5 acres.",
        "documents_required": "Samagra ID, Aadhaar Card, DBT-linked Bank Account, Mobile number.",
        "application_url": "https://cmladlibehna.mp.gov.in",
        "application_process": "Gram Panchayat and Ward camps fill application forms on the portal with biometric/eKYC.",
    },
    {
        "slug": "up-shadi-anudan-yojana",
        "title": "Shadi Anudan Yojana (Uttar Pradesh)",
        "short_description": "Financial assistance of ₹51,000 for daughter's marriage to poor families in UP.",
        "description": "Uttar Pradesh government scheme supporting underprivileged SC, ST, OBC, Minority, and General BPL families with grant assistance for daughter's marriage ceremony expenses.",
        "ministry": "Social Welfare Department, Uttar Pradesh",
        "state": "Uttar Pradesh",
        "country": "India",
        "category": "Social Welfare",
        "target_gender": "Female",
        "min_age": 18,
        "max_age": 50,
        "income_limit": 46080,
        "benefits": "One-time financial grant of ₹51,000 per daughter (up to 2 daughters per family).",
        "eligibility_summary": "Daughter must be 18+ years, groom 21+ years. Annual family income <= ₹46,080 (rural) or ₹56,460 (urban).",
        "documents_required": "Daughter & Groom age proof, Marriage invitation card, Income certificate, Caste certificate, Bank passbook.",
        "application_url": "https://shadianudan.upsdc.gov.in",
        "application_process": "Apply on the UP Shadi Anudan portal within 90 days before or 90 days after marriage date.",
    },
    {
        "slug": "karnataka-yuva-nidhi-scheme",
        "title": "Yuva Nidhi Scheme (Karnataka)",
        "short_description": "Monthly unemployment stipend for educated youth in Karnataka.",
        "description": "Karnataka government initiative providing monthly financial aid to fresh graduates and diploma holders who have remained unemployed for 6 months after graduation.",
        "ministry": "Department of Skill Development, Karnataka",
        "state": "Karnataka",
        "country": "India",
        "category": "Education",
        "target_gender": "All",
        "min_age": 20,
        "max_age": 30,
        "income_limit": None,
        "benefits": "₹3,000/month for degree holders, ₹1,500/month for diploma holders for up to 2 years.",
        "eligibility_summary": "Resident of Karnataka with degree/diploma passed in 2023 or later, unemployed for 6+ months, not in higher study.",
        "documents_required": "Karnataka Domicile, Degree/Diploma Certificate, Aadhaar Card, Bank Account.",
        "application_url": "https://sevasindhugs.karnataka.gov.in",
        "application_process": "Register via Seva Sindhu portal using Aadhaar and university degree credentials.",
    },
]


class SchemeRepository:
    def __init__(self):
        self._table_initialized = False

    def init_database(self) -> None:
        """Create tables in AlloyDB and seed default schemes if empty."""
        try:
            engine = get_engine()
            Base.metadata.create_all(bind=engine)
            
            with Session(engine) as session:
                existing_count = session.query(SchemeModel).count()
                if existing_count == 0:
                    for item in DEFAULT_SEED_SCHEMES:
                        scheme = SchemeModel(**item)
                        session.add(scheme)
                    session.commit()
            self._table_initialized = True
        except Exception as e:
            # Fallback will serve from memory if DB write is restricted
            print(f"[WARN] Database table sync encountered: {e}")

    def get_schemes(
        self,
        query: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = "India",
        age: Optional[int] = None,
        gender: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Fetch schemes from database matching criteria, or fallback to seed records."""
        # Try database first
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                stmt = select(SchemeModel).where(SchemeModel.is_active == True)

                # State filter: Match requested state OR "All India"
                if state and state.strip().lower() not in ("all", "all india", "national", "any"):
                    stmt = stmt.where(or_(
                        SchemeModel.state.ilike(f"%{state.strip()}%"),
                        SchemeModel.state.ilike("%all india%")
                    ))

                # Age filter
                if age is not None:
                    stmt = stmt.where(or_(
                        and_(SchemeModel.min_age <= age, SchemeModel.max_age >= age),
                        and_(SchemeModel.min_age <= age, SchemeModel.max_age == None),
                        and_(SchemeModel.min_age == None, SchemeModel.max_age >= age),
                        and_(SchemeModel.min_age == None, SchemeModel.max_age == None),
                    ))

                # Category filter
                if category and category.strip().lower() not in ("all", "any"):
                    stmt = stmt.where(SchemeModel.category.ilike(f"%{category.strip()}%"))

                # Gender filter
                if gender and gender.strip().lower() in ("female", "woman", "girl"):
                    stmt = stmt.where(or_(SchemeModel.target_gender == "All", SchemeModel.target_gender == "Female"))
                elif gender and gender.strip().lower() in ("male", "man", "boy"):
                    stmt = stmt.where(or_(SchemeModel.target_gender == "All", SchemeModel.target_gender == "Male"))

                # Search query filter
                if query and query.strip():
                    q = f"%{query.strip()}%"
                    stmt = stmt.where(or_(
                        SchemeModel.title.ilike(q),
                        SchemeModel.short_description.ilike(q),
                        SchemeModel.description.ilike(q),
                        SchemeModel.category.ilike(q),
                        SchemeModel.benefits.ilike(q),
                    ))

                all_matches = session.execute(stmt).scalars().all()
                total = len(all_matches)
                paginated = all_matches[offset: offset + limit]
                return [self._to_dict(m, age, state) for m in paginated], total

        except Exception as e:
            print(f"[INFO] Using in-memory dataset for query (DB note: {e})")
            return self._filter_in_memory(query, state, age, gender, category, limit, offset)

    def _to_dict(self, model: SchemeModel, age: Optional[int], state: Optional[str]) -> Dict[str, Any]:
        data = {
            "id": model.id,
            "slug": model.slug,
            "title": model.title,
            "short_description": model.short_description,
            "description": model.description,
            "ministry": model.ministry,
            "state": model.state,
            "country": model.country,
            "category": model.category,
            "target_gender": model.target_gender,
            "min_age": model.min_age,
            "max_age": model.max_age,
            "income_limit": model.income_limit,
            "benefits": model.benefits,
            "eligibility_summary": model.eligibility_summary,
            "documents_required": model.documents_required,
            "application_url": model.application_url,
            "application_process": model.application_process,
            "is_active": getattr(model, "is_active", True),
            "match_reasons": self._generate_reasons(model, age, state),
        }
        return data

    def _generate_reasons(self, scheme: Any, age: Optional[int], state: Optional[str]) -> List[str]:
        reasons = []
        if state and (state.lower() in scheme.state.lower() or scheme.state.lower() == "all india"):
            reasons.append(f"Available in {scheme.state}")
        if age is not None:
            if scheme.min_age is not None and scheme.max_age is not None:
                reasons.append(f"Eligible for age {age} (Criteria: {scheme.min_age}-{scheme.max_age} yrs)")
            elif scheme.min_age is not None:
                reasons.append(f"Eligible for age {age} (Min age: {scheme.min_age} yrs)")
            elif scheme.max_age is not None:
                reasons.append(f"Eligible for age {age} (Max age: {scheme.max_age} yrs)")
        if scheme.category:
            reasons.append(f"Category: {scheme.category}")
        return reasons

    def _filter_in_memory(
        self,
        query: Optional[str],
        state: Optional[str],
        age: Optional[int],
        gender: Optional[str],
        category: Optional[str],
        limit: int,
        offset: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        results = []
        for idx, item in enumerate(DEFAULT_SEED_SCHEMES, 1):
            # State match
            if state and state.strip().lower() not in ("all", "all india", "national", "any"):
                st = state.strip().lower()
                scheme_st = item["state"].lower()
                if st not in scheme_st and "all india" not in scheme_st:
                    continue

            # Age match
            if age is not None:
                min_a = item.get("min_age")
                max_a = item.get("max_age")
                if min_a is not None and age < min_a:
                    continue
                if max_a is not None and age > max_a:
                    continue

            # Category match
            if category and category.strip().lower() not in ("all", "any"):
                if category.strip().lower() not in item["category"].lower():
                    continue

            # Query match
            if query and query.strip():
                q = query.strip().lower()
                content = f"{item['title']} {item['short_description']} {item['category']} {item['benefits']}".lower()
                if q not in content:
                    continue

            item_copy = dict(item)
            item_copy["id"] = idx
            item_copy["match_reasons"] = self._generate_reasons(type("Obj", (), item_copy), age, state)
            results.append(item_copy)

        return results[offset: offset + limit], len(results)

    def extract_intent(self, text_input: str) -> Dict[str, Any]:
        """Extract state, age, gender, category from natural language query."""
        state = None
        age = None
        gender = None
        category = None

        text_lower = text_input.lower()

        # Age detection (e.g., "22 years old", "age 25", "18 yrs", "daughter is 8", "girl child 6 years")
        age_patterns = [
            r"\b(?:age|aged|am)\s*([0-9]{1,2})\b",
            r"\b([0-9]{1,2})\s*(?:years?|yrs?|yr)\s*(?:old)?\b",
            r"\b([0-9]{1,2})\s*(?:saal|sal)\b",
        ]
        for pat in age_patterns:
            match = re.search(pat, text_lower)
            if match:
                try:
                    age = int(match.group(1))
                    break
                except ValueError:
                    pass

        # State detection
        known_states = [
            "maharashtra", "uttar pradesh", "madhya pradesh", "karnataka", "bihar",
            "tamil nadu", "rajasthan", "gujarat", "west bengal", "delhi", "kerala",
            "punjab", "haryana", "andhra pradesh", "telangana", "odisha", "assam"
        ]
        for st in known_states:
            if st in text_lower:
                state = st.title()
                break

        # Category detection
        if any(w in text_lower for w in ["education", "scholarship", "study", "college", "school", "degree", "diploma", "padhai"]):
            category = "Education"
        elif any(w in text_lower for w in ["health", "hospital", "medical", "treatment", "bimar", "ayushman"]):
            category = "Health"
        elif any(w in text_lower for w in ["house", "housing", "awas", "home", "ghar", "makan"]):
            category = "Housing"
        elif any(w in text_lower for w in ["pension", "old age", "senior", "retirement", "vriddha"]):
            category = "Pension"
        elif any(w in text_lower for w in ["farmer", "kisan", "krishi", "agriculture", "crop", "kheti"]):
            category = "Agriculture"
        elif any(w in text_lower for w in ["daughter", "girl", "woman", "women", "mahila", "ladli", "shadi", "marriage", "sukanya"]):
            category = "Women & Child"

        # Gender detection
        if any(w in text_lower for w in ["daughter", "girl", "woman", "women", "female", "she", "her", "mahila", "ladki"]):
            gender = "Female"
        elif any(w in text_lower for w in ["son", "boy", "man", "male", "he", "his", "ladka"]):
            gender = "Male"

        return {
            "state": state,
            "age": age,
            "gender": gender,
            "category": category,
            "raw_text": text_input
        }

    def get_scheme_by_id_or_slug(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific scheme by ID or slug/title."""
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                if identifier.isdigit():
                    model = session.query(SchemeModel).filter(SchemeModel.id == int(identifier)).first()
                else:
                    model = session.query(SchemeModel).filter(
                        or_(
                            SchemeModel.slug == identifier.strip().lower(),
                            SchemeModel.title.ilike(f"%{identifier.strip()}%")
                        )
                    ).first()
                if model:
                    return self._to_dict(model, None, None)
        except Exception as e:
            print(f"[WARN] Error fetching scheme from DB: {e}")

        # Fallback to seed
        ident_lower = identifier.strip().lower()
        for idx, s in enumerate(DEFAULT_SEED_SCHEMES, 1):
            if str(idx) == identifier or s["slug"] == ident_lower or ident_lower in s["title"].lower():
                copy_s = dict(s)
                copy_s["id"] = idx
                return copy_s
        return None

    # =========================================================
    # Admin Management Methods
    # =========================================================

    def _slugify(self, title: str) -> str:
        """Helper to create a URL-friendly slug from title."""
        slug = re.sub(r"[^\w\s-]", "", title.lower())
        slug = re.sub(r"[-\s]+", "-", slug).strip("-")
        return slug or f"scheme-{int(datetime.utcnow().timestamp())}"

    def create_scheme(self, payload: SchemeCreateRequest) -> Dict[str, Any]:
        """Create a new scheme in AlloyDB."""
        slug = payload.slug.strip().lower() if payload.slug else self._slugify(payload.title)
        
        # Ensure unique slug
        scheme_data = payload.model_dump()
        scheme_data["slug"] = slug

        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                # Check for slug collision
                existing = session.query(SchemeModel).filter(SchemeModel.slug == slug).first()
                if existing:
                    # Append unique timestamp suffix
                    import time
                    slug = f"{slug}-{int(time.time())}"
                    scheme_data["slug"] = slug

                model = SchemeModel(**scheme_data)
                session.add(model)
                session.commit()
                session.refresh(model)
                return self._to_dict(model, None, None)
        except Exception as e:
            print(f"[WARN] Error creating scheme in AlloyDB: {e}")
            # In-memory fallback
            scheme_data["id"] = len(DEFAULT_SEED_SCHEMES) + 1
            DEFAULT_SEED_SCHEMES.insert(0, scheme_data)
            return scheme_data

    def update_scheme(self, scheme_id: int, payload: SchemeUpdateRequest) -> Optional[Dict[str, Any]]:
        """Update an existing scheme in AlloyDB."""
        update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
        
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                model = session.query(SchemeModel).filter(SchemeModel.id == scheme_id).first()
                if not model:
                    return None
                
                for key, val in update_data.items():
                    setattr(model, key, val)
                
                session.commit()
                session.refresh(model)
                return self._to_dict(model, None, None)
        except Exception as e:
            print(f"[WARN] Error updating scheme in AlloyDB: {e}")
            for idx, s in enumerate(DEFAULT_SEED_SCHEMES, 1):
                if idx == scheme_id or s.get("id") == scheme_id:
                    s.update(update_data)
                    s["id"] = scheme_id
                    return s
            return None

    def delete_scheme(self, scheme_id: int) -> bool:
        """Delete a scheme from AlloyDB (or mark inactive)."""
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                model = session.query(SchemeModel).filter(SchemeModel.id == scheme_id).first()
                if not model:
                    return False
                session.delete(model)
                session.commit()
                return True
        except Exception as e:
            print(f"[WARN] Error deleting scheme in AlloyDB: {e}")
            for i, s in enumerate(DEFAULT_SEED_SCHEMES):
                if (i + 1) == scheme_id or s.get("id") == scheme_id:
                    DEFAULT_SEED_SCHEMES.pop(i)
                    return True
            return False

    def toggle_scheme_status(self, scheme_id: int) -> Optional[Dict[str, Any]]:
        """Toggle active / inactive status of a scheme."""
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                model = session.query(SchemeModel).filter(SchemeModel.id == scheme_id).first()
                if not model:
                    return None
                model.is_active = not model.is_active
                session.commit()
                session.refresh(model)
                return self._to_dict(model, None, None)
        except Exception as e:
            print(f"[WARN] Error toggling scheme status: {e}")
            for idx, s in enumerate(DEFAULT_SEED_SCHEMES, 1):
                if idx == scheme_id or s.get("id") == scheme_id:
                    s["is_active"] = not s.get("is_active", True)
                    s["id"] = scheme_id
                    return s
            return None

    def get_admin_schemes(
        self,
        query: Optional[str] = None,
        state: Optional[str] = None,
        category: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Admin list endpoint returning all schemes including inactive ones."""
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                stmt = select(SchemeModel)

                if is_active is not None:
                    stmt = stmt.where(SchemeModel.is_active == is_active)

                if state and state.strip().lower() not in ("all", "all india", "national", "any"):
                    stmt = stmt.where(SchemeModel.state.ilike(f"%{state.strip()}%"))

                if category and category.strip().lower() not in ("all", "any"):
                    stmt = stmt.where(SchemeModel.category.ilike(f"%{category.strip()}%"))

                if query and query.strip():
                    q = f"%{query.strip()}%"
                    stmt = stmt.where(or_(
                        SchemeModel.title.ilike(q),
                        SchemeModel.slug.ilike(q),
                        SchemeModel.short_description.ilike(q),
                        SchemeModel.ministry.ilike(q),
                        SchemeModel.category.ilike(q),
                    ))

                stmt = stmt.order_by(SchemeModel.id.desc())
                all_matches = session.execute(stmt).scalars().all()
                total = len(all_matches)
                paginated = all_matches[offset: offset + limit]
                return [self._to_dict(m, None, None) for m in paginated], total

        except Exception as e:
            print(f"[WARN] Admin schemes fallback to in-memory dataset: {e}")
            filtered = []
            for idx, s in enumerate(DEFAULT_SEED_SCHEMES, 1):
                if is_active is not None and s.get("is_active", True) != is_active:
                    continue
                if state and state.lower() not in ("all", "all india", "any") and state.lower() not in s["state"].lower():
                    continue
                if category and category.lower() not in ("all", "any") and category.lower() not in s["category"].lower():
                    continue
                if query and query.strip():
                    q = query.strip().lower()
                    text_blob = f"{s['title']} {s['slug']} {s.get('ministry', '')} {s['category']}".lower()
                    if q not in text_blob:
                        continue
                item = dict(s)
                item["id"] = idx
                filtered.append(item)
            return filtered[offset: offset + limit], len(filtered)

    def get_admin_stats(self) -> Dict[str, Any]:
        """Aggregate metrics for the Admin Dashboard."""
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                total = session.query(SchemeModel).count()
                active = session.query(SchemeModel).filter(SchemeModel.is_active == True).count()
                inactive = total - active
                
                categories = [r[0] for r in session.query(SchemeModel.category).distinct() if r[0]]
                states = [r[0] for r in session.query(SchemeModel.state).distinct() if r[0]]

                return {
                    "total_schemes": total,
                    "active_schemes": active,
                    "inactive_schemes": inactive,
                    "total_categories": len(categories),
                    "total_states": len(states),
                    "categories": sorted(categories),
                    "states": sorted(states),
                }
        except Exception as e:
            print(f"[WARN] Error fetching admin stats from DB: {e}")
            total = len(DEFAULT_SEED_SCHEMES)
            categories = list({s["category"] for s in DEFAULT_SEED_SCHEMES if "category" in s})
            states = list({s["state"] for s in DEFAULT_SEED_SCHEMES if "state" in s})
            return {
                "total_schemes": total,
                "active_schemes": total,
                "inactive_schemes": 0,
                "total_categories": len(categories),
                "total_states": len(states),
                "categories": sorted(categories),
                "states": sorted(states),
            }


