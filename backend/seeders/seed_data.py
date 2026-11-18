import os
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import SessionLocal, Base, engine
from app.models.user import User
from app.models.finance import MarginTier, Invoice
from app.models.warehouse import Warehouse
from app.models.logistics import Vehicle, DriverRate, DispatchOrder, DeliveryStop
from app.models.equipment import Equipment
from app.models.security_agency import SecurityAgency, SecurityPersonnel, SecurityAssignment

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
    db = SessionLocal()
    try:
        # Purge any dummy demo accounts
        purge_demo_data(db)
        
        # Seed core operational config
        seed_essential_system_config(db)
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
