from typing import Optional
from sqlalchemy.orm import Session

from src.config.settings import get_settings
from src.models.scheme import Base
from src.models.user import UserModel
from src.middleware.security import hash_password, verify_password
from src.repositories.alloydb import get_engine


class UserRepository:
    def __init__(self):
        self._initialized = False

    def init_database(self) -> None:
        """Create users table in AlloyDB if not already present."""
        try:
            engine = get_engine()
            Base.metadata.create_all(bind=engine)
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
                return session.query(UserModel).filter(
                    UserModel.email == email.lower().strip()
                ).first()
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

