from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config.settings import get_settings
from src.models.scheme import Base
from src.models.user import (
    UserModel,
    CustomerRegisterRequest,
    CustomerProfileUpdateRequest,
)
from src.middleware.security import hash_password, verify_password
from src.repositories.alloydb import get_engine


class UserRepository:
    def __init__(self):
        self._initialized = False

    def init_database(self) -> None:
        """Create users table in AlloyDB if not already present, and migrate missing columns."""
        try:
            engine = get_engine()
            Base.metadata.create_all(bind=engine)
            
            with engine.connect() as conn:
                for col, col_type in [
                    ("state", "VARCHAR(100) DEFAULT 'All India'"),
                    ("age", "INTEGER"),
                    ("gender", "VARCHAR(20) DEFAULT 'All'"),
                    ("annual_income", "INTEGER"),
                    ("category", "VARCHAR(100) DEFAULT 'All'"),
                    ("occupation", "VARCHAR(100)"),
                ]:
                    try:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {col_type}"))
                        conn.commit()
                    except Exception:
                        pass
            self._initialized = True
        except Exception as e:
            print(f"[WARN] User table initialization notice: {e}")

    def seed_default_admin(self) -> None:
        """Ensure the initial default admin account is seeded into AlloyDB."""
        settings = get_settings()
        admin_email = settings.default_admin_email.lower().strip()
        admin_password = settings.default_admin_password
        admin_name = settings.default_admin_name

        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                existing_admin = session.query(UserModel).filter(
                    UserModel.email == admin_email
                ).first()

                if not existing_admin:
                    hashed_pwd = hash_password(admin_password)
                    admin_user = UserModel(
                        email=admin_email,
                        hashed_password=hashed_pwd,
                        full_name=admin_name,
                        role="admin",
                        is_active=True,
                    )
                    session.add(admin_user)
                    session.commit()
                    print(f"[INFO] Successfully seeded default admin user: {admin_email}")
                else:
                    # Ensure active and admin role
                    if existing_admin.role != "admin" or not existing_admin.is_active:
                        existing_admin.role = "admin"
                        existing_admin.is_active = True
                        session.commit()
        except Exception as e:
            print(f"[INFO] Default admin seed notice (AlloyDB status): {e}")

    def get_by_email(self, email: str) -> Optional[UserModel]:
        """Find user by email address."""
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                user = session.query(UserModel).filter(
                    UserModel.email == email.lower().strip()
                ).first()
                if user:
                    session.expunge(user)
                return user
        except Exception as e:
            print(f"[WARN] Error fetching user by email: {e}")
            return None

    def authenticate_admin(self, email: str, password: str) -> Optional[UserModel]:
        """Authenticate admin credentials with database hash or fallback."""
        settings = get_settings()
        clean_email = email.lower().strip()

        # Check in AlloyDB
        user = self.get_by_email(clean_email)
        if user:
            if user.role == "admin" and user.is_active and verify_password(password, user.hashed_password):
                return user
            return None

        # Fallback check against configured default admin if DB was temporarily unreachable
        if (
            clean_email == settings.default_admin_email.lower().strip()
            and password == settings.default_admin_password
        ):
            self.seed_default_admin()
            persisted = self.get_by_email(clean_email)
            if persisted:
                return persisted

            return UserModel(
                id=1,
                email=clean_email,
                full_name=settings.default_admin_name,
                role="admin",
                is_active=True,
                hashed_password=hash_password(password)
            )

        return None

    # =========================================================
    # Customer (Citizen) User Methods
    # =========================================================

    def register_customer(self, payload: CustomerRegisterRequest) -> tuple[Optional[UserModel], Optional[str]]:
        """Register a new customer/citizen account in AlloyDB."""
        clean_email = payload.email.lower().strip()

        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                # Check for existing email
                existing = session.query(UserModel).filter(UserModel.email == clean_email).first()
                if existing:
                    return None, "An account with this email address already exists."

                hashed_pwd = hash_password(payload.password)
                new_user = UserModel(
                    email=clean_email,
                    hashed_password=hashed_pwd,
                    full_name=payload.full_name.strip(),
                    role="customer",
                    state=payload.state or "All India",
                    age=payload.age,
                    gender=payload.gender or "All",
                    annual_income=payload.annual_income,
                    category=payload.category or "All",
                    occupation=payload.occupation,
                    is_active=True,
                )
                session.add(new_user)
                session.commit()
                session.refresh(new_user)
                session.expunge(new_user)
                return new_user, None

        except Exception as e:
            print(f"[WARN] Error registering customer in AlloyDB: {e}")
            return None, f"Database registration failed: {str(e)}"

    def authenticate_customer(self, email: str, password: str) -> Optional[UserModel]:
        """Authenticate citizen credentials against AlloyDB."""
        clean_email = email.lower().strip()
        user = self.get_by_email(clean_email)
        if user and user.is_active and verify_password(password, user.hashed_password):
            return user
        return None

    def get_by_id(self, user_id: int) -> Optional[UserModel]:
        """Fetch user by primary key ID."""
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                user = session.query(UserModel).filter(UserModel.id == user_id).first()
                if user:
                    session.expunge(user)
                return user
        except Exception as e:
            print(f"[WARN] Error fetching user by ID: {e}")
            return None

    def update_profile(self, user_id: int, payload: CustomerProfileUpdateRequest) -> Optional[UserModel]:
        """Update citizen profile parameters."""
        update_data = {k: v for k, v in payload.model_dump().items() if v is not None}

        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                user = session.query(UserModel).filter(UserModel.id == user_id).first()
                if not user:
                    return None

                for key, val in update_data.items():
                    setattr(user, key, val)

                session.commit()
                session.refresh(user)
                session.expunge(user)
                return user
        except Exception as e:
            print(f"[WARN] Error updating profile in AlloyDB: {e}")
            return None


