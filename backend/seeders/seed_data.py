import os
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import SessionLocal, Base, engine
from app.core.security import hash_password
from app.models.user import User
from app.models.finance import MarginTier, Invoice
from app.models.warehouse import Warehouse
from app.models.logistics import Vehicle, DriverRate, DispatchOrder, DeliveryStop
from app.models.equipment import Equipment
from app.models.security_agency import SecurityAgency, SecurityPersonnel, SecurityAssignment
from sqlalchemy import text

def ensure_schema_migrations():
    """Applies any incremental column migrations to existing production tables."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verification_token VARCHAR(255);
                ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_password_token VARCHAR(255);
                ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_password_expires_at TIMESTAMP;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP;
            """))
            conn.commit()
    except Exception as e:
        print(f"Schema migration note: {e}")

def purge_demo_data(db: Session):
    """
    Purges all legacy .test demo accounts and their associated test records.
    """
    demo_users = db.query(User).filter(User.email.like("%.test")).all()
    if demo_users:
        demo_ids = [u.id for u in demo_users]
        print(f"🧹 Purging {len(demo_users)} legacy demo accounts from database...")
        
        # Remove linked demo objects
        db.query(Invoice).filter(Invoice.user_id.in_(demo_ids)).delete(synchronize_session=False)
        db.query(DeliveryStop).delete(synchronize_session=False)
        db.query(DispatchOrder).filter(DispatchOrder.client_id.in_(demo_ids)).delete(synchronize_session=False)
        db.query(SecurityAssignment).delete(synchronize_session=False)
        db.query(SecurityPersonnel).delete(synchronize_session=False)
        db.query(SecurityAgency).filter(SecurityAgency.user_id.in_(demo_ids)).delete(synchronize_session=False)
        db.query(Equipment).filter(Equipment.user_id.in_(demo_ids)).delete(synchronize_session=False)
        db.query(DriverRate).filter(DriverRate.user_id.in_(demo_ids)).delete(synchronize_session=False)
        db.query(Vehicle).filter(Vehicle.user_id.in_(demo_ids)).delete(synchronize_session=False)
        db.query(Warehouse).filter(Warehouse.user_id.in_(demo_ids)).delete(synchronize_session=False)
        
        # Delete demo users
        for u in demo_users:
            db.delete(u)
        db.commit()
        print("✅ Demo data successfully removed. System is clean for real registrations.")

def ensure_superadmin(db: Session):
    """
    Ensures the Superadmin account configured via Vercel Environment Variables
    (ADMIN_EMAIL, ADMIN_PASSWORD) exists and is up to date.
    """
    admin_email = settings.ADMIN_EMAIL.strip().lower()
    admin_password = settings.ADMIN_PASSWORD.strip()

    if not admin_email or not admin_password:
        return

    admin_user = db.query(User).filter(User.email == admin_email).first()
    if not admin_user:
        admin_user = User(
            name=settings.ADMIN_NAME or "System Superadmin",
            email=admin_email,
            password=hash_password(admin_password),
            phone=settings.ADMIN_PHONE or "9800000000",
            role="admin",
            is_admin=True,
            is_active=True,
            user_code="ADM-001",
            email_verified_at=datetime.utcnow()
        )
        db.add(admin_user)
        db.commit()
        print(f"👑 Superadmin created from environment variables: {admin_email}")
    else:
        # Keep admin privileges and synchronize credentials from environment variables
        admin_user.is_admin = True
        admin_user.role = "admin"
        admin_user.password = hash_password(admin_password)
        admin_user.is_active = True
        if settings.ADMIN_NAME:
            admin_user.name = settings.ADMIN_NAME
        if settings.ADMIN_PHONE:
            admin_user.phone = settings.ADMIN_PHONE
        db.commit()
        print(f"👑 Superadmin synchronized from environment variables: {admin_email}")

def seed_essential_system_config(db: Session):
    """
    Seeds essential operational configuration (e.g. official Nepal logistics distance margin tiers)
    required for price calculation algorithms.
    """
    if db.query(MarginTier).count() == 0:
        tiers = [
            MarginTier(
                name="Short Distance (0-10km)",
                min_distance=0,
                max_distance=10,
                service_type="dispatch",
                margin_type="percentage",
                margin_value=10.0,
                is_active=True
            ),
            MarginTier(
                name="Medium Distance (11-50km)",
                min_distance=10,
                max_distance=50,
                service_type="dispatch",
                margin_type="percentage",
                margin_value=12.0,
                is_active=True
            ),
            MarginTier(
                name="Long Distance (51km+)",
                min_distance=50,
                max_distance=None,
                service_type="dispatch",
                margin_type="percentage",
                margin_value=15.0,
                is_active=True
            ),
        ]
        db.add_all(tiers)
        db.commit()
        print("✅ Seeded essential Nepal freight margin tiers (10%, 12%, 15%)")

def seed_database():
    Base.metadata.create_all(bind=engine)
    ensure_schema_migrations()
    db = SessionLocal()
    try:
        # Purge any dummy demo accounts
        purge_demo_data(db)
        
        # Ensure Superadmin configured in environment variables exists
        ensure_superadmin(db)

        # Seed core operational config
        seed_essential_system_config(db)
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
