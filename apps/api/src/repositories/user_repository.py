from typing import Optional, List, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config.settings import get_settings
from src.models.scheme import Base
from src.models.user import (
    UserModel,
    CustomerRegisterRequest,
    CustomerProfileUpdateRequest,
    AdminCreateRequest,
)
from src.middleware.security import hash_password, verify_password
from src.repositories.database import get_engine


class UserRepository:
    def __init__(self):
        self._initialized = False

    def init_database(self) -> None:
        """Create users table in SQLite / Database if not already present, and migrate missing columns."""
        try:
            engine = get_engine()
            Base.metadata.create_all(bind=engine)
            
            with engine.connect() as conn:
                for col, col_type in [
                    ("state", "TEXT DEFAULT 'All India'"),
                    ("age", "INTEGER"),
                    ("gender", "TEXT DEFAULT 'All'"),
                    ("annual_income", "INTEGER"),
                    ("category", "TEXT DEFAULT 'All'"),
                    ("occupation", "TEXT"),
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
        """Ensure the initial default admin account is seeded into SQLite / Database."""
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
            print(f"[INFO] Default admin seed notice: {e}")

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

        # Check in database
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
        """Register a new customer/citizen account in SQLite / Database."""
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
                    state=getattr(payload, "state", "All India") or "All India",
                    age=getattr(payload, "age", None),
                    gender=getattr(payload, "gender", "All") or "All",
                    annual_income=getattr(payload, "annual_income", None),
                    category=getattr(payload, "category", "All") or "All",
                    occupation=getattr(payload, "occupation", None),
                    is_active=True,
                )
                session.add(new_user)
                session.commit()
                session.refresh(new_user)
                session.expunge(new_user)
                return new_user, None

        except Exception as e:
            print(f"[WARN] Error registering customer: {e}")
            return None, f"Database registration failed: {str(e)}"

    def authenticate_customer(self, email: str, password: str) -> Optional[UserModel]:
        """Authenticate citizen credentials against SQLite / Database."""
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
            print(f"[WARN] Error updating profile: {e}")
            return None

    def delete_user(self, user_id: int) -> bool:
        """Permanently delete user and their profile data per DPDP Act request."""
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                user = session.query(UserModel).filter(UserModel.id == user_id).first()
                if user:
                    session.delete(user)
                    session.commit()
                    return True
                return False
        except Exception as e:
            print(f"[WARN] Error deleting user: {e}")
            return False

    # =========================================================
    # Password Reset & Change Password Methods
    # =========================================================

    def reset_password(self, email: str, new_password: str) -> bool:
        """Reset password for a citizen or admin by verified email."""
        clean_email = email.lower().strip()
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                user = session.query(UserModel).filter(UserModel.email == clean_email).first()
                if not user:
                    return False
                user.hashed_password = hash_password(new_password)
                session.commit()
                return True
        except Exception as e:
            print(f"[WARN] Error resetting password: {e}")
            return False

    def change_password(self, user_id: int, old_password: str, new_password: str) -> Tuple[bool, str]:
        """Change password for an authenticated user after verifying current password."""
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                user = session.query(UserModel).filter(UserModel.id == user_id).first()
                if not user:
                    return False, "User account not found."
                if not verify_password(old_password, user.hashed_password):
                    return False, "Incorrect current password."
                user.hashed_password = hash_password(new_password)
                session.commit()
                return True, "Password changed successfully."
        except Exception as e:
            print(f"[WARN] Error changing password: {e}")
            return False, f"Password change failed: {str(e)}"

    # =========================================================
    # Admin User Management Methods
    # =========================================================

    def list_admins(self) -> List[UserModel]:
        """List all administrators in the system."""
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                admins = session.query(UserModel).filter(UserModel.role == "admin").all()
                for a in admins:
                    session.expunge(a)
                return admins
        except Exception as e:
            print(f"[WARN] Error listing admins: {e}")
            return []

    def create_admin(self, payload: AdminCreateRequest) -> Tuple[Optional[UserModel], Optional[str]]:
        """Create a new administrative user account."""
        clean_email = payload.email.lower().strip()
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                existing = session.query(UserModel).filter(UserModel.email == clean_email).first()
                if existing:
                    return None, "An account with this email address already exists."

                hashed_pwd = hash_password(payload.password)
                admin_user = UserModel(
                    email=clean_email,
                    hashed_password=hashed_pwd,
                    full_name=payload.full_name.strip(),
                    role="admin",
                    is_active=True,
                )
                session.add(admin_user)
                session.commit()
                session.refresh(admin_user)
                session.expunge(admin_user)
                return admin_user, None
        except Exception as e:
            print(f"[WARN] Error creating admin: {e}")
            return None, f"Admin creation failed: {str(e)}"

    def count_active_admins(self) -> int:
        """Count total active administrators."""
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                count = session.query(UserModel).filter(
                    UserModel.role == "admin",
                    UserModel.is_active.is_(True)
                ).count()
                return count
        except Exception as e:
            print(f"[WARN] Error counting active admins: {e}")
            return 1

    def deactivate_admin(self, user_id: int) -> Tuple[bool, str]:
        """Deactivate an admin account with last-admin guard."""
        try:
            self.init_database()
            engine = get_engine()
            with Session(engine) as session:
                user = session.query(UserModel).filter(UserModel.id == user_id, UserModel.role == "admin").first()
                if not user:
                    return False, "Admin user not found."

                # If this admin is currently active, ensure they are not the last active admin
                if user.is_active:
                    active_count = session.query(UserModel).filter(
                        UserModel.role == "admin",
                        UserModel.is_active.is_(True)
                    ).count()
                    if active_count <= 1:
                        return False, "Cannot deactivate the last remaining active administrator."

                user.is_active = False
                session.commit()
                return True, "Admin deactivated successfully."
        except Exception as e:
            print(f"[WARN] Error deactivating admin: {e}")
            return False, f"Deactivation failed: {str(e)}"

