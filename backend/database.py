"""
Database session and connection engine.
Seamlessly connects to Supabase PostgreSQL in production with pool_pre_ping for serverless,
and provides graceful failover with automatic table & master admin provisioning.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from backend.config import settings

db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://") and "+psycopg" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

def get_engine():
    connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
    try:
        eng = create_engine(db_url, connect_args=connect_args, echo=False, pool_pre_ping=True)
        # Validate connection
        with eng.connect() as conn:
            pass
        return eng
    except Exception as e:
        print(f"[DATABASE NOTICE] Remote PostgreSQL unavailable ({e}). Using SQLite storage fallback.")
        sqlite_url = "sqlite:////tmp/kwdc.db" if os.environ.get("VERCEL") else "sqlite:///./kwdc.db"
        return create_engine(sqlite_url, connect_args={"check_same_thread": False}, echo=False)

engine = get_engine()
is_sqlite = "sqlite" in str(engine.url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db_info() -> dict:
    return {
        "engine": "sqlite" if is_sqlite else "postgresql",
        "label": "SQLite Local Storage (Offline Fallback)" if is_sqlite else "Supabase PostgreSQL 17 (Live)",
        "is_sqlite": is_sqlite
    }

def ensure_db_schema_extensions():
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            # Drivers table extensions
            if is_sqlite:
                # SQLite ALTER TABLE compatibility
                try:
                    conn.execute(text("ALTER TABLE drivers ADD COLUMN license_category VARCHAR(50) DEFAULT 'Category B (Delivery Van / Pickup)';"))
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE drivers ADD COLUMN license_photo_front_url VARCHAR(500);"))
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE drivers ADD COLUMN license_photo_back_url VARCHAR(500);"))
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE drivers ADD COLUMN blood_group VARCHAR(10);"))
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE drivers ADD COLUMN emergency_contact_name VARCHAR(255);"))
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE drivers ADD COLUMN emergency_contact_phone VARCHAR(50);"))
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE drivers ADD COLUMN has_clean_traffic_record BOOLEAN DEFAULT 1;"))
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE drivers ADD COLUMN login_pin VARCHAR(255) DEFAULT '1234';"))
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN fleet_operator_type VARCHAR(50) DEFAULT 'COMMERCIAL_3PL';"))
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE dispatch_orders ADD COLUMN reassigned_from_vehicle_id INTEGER;"))
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE dispatch_orders ADD COLUMN reassigned_from_driver_id INTEGER;"))
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE dispatch_orders ADD COLUMN reassignment_reason VARCHAR(500);"))
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE dispatch_orders ADD COLUMN delivery_otp VARCHAR(6);"))
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE dispatch_orders ADD COLUMN delivered_at TIMESTAMP;"))
                except Exception:
                    pass
            else:
                conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS license_category VARCHAR(50) DEFAULT 'Category B (Delivery Van / Pickup)';"))
                conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS license_photo_front_url VARCHAR(500);"))
                conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS license_photo_back_url VARCHAR(500);"))
                conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS blood_group VARCHAR(10);"))
                conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS emergency_contact_name VARCHAR(255);"))
                conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS emergency_contact_phone VARCHAR(50);"))
                conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS has_clean_traffic_record BOOLEAN DEFAULT TRUE;"))
                conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS login_pin VARCHAR(255) DEFAULT '1234';"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS fleet_operator_type VARCHAR(50) DEFAULT 'COMMERCIAL_3PL';"))
                conn.execute(text("ALTER TABLE dispatch_orders ADD COLUMN IF NOT EXISTS reassigned_from_vehicle_id INTEGER;"))
                conn.execute(text("ALTER TABLE dispatch_orders ADD COLUMN IF NOT EXISTS reassigned_from_driver_id INTEGER;"))
                conn.execute(text("ALTER TABLE dispatch_orders ADD COLUMN IF NOT EXISTS reassignment_reason VARCHAR(500);"))
                conn.execute(text("ALTER TABLE dispatch_orders ADD COLUMN IF NOT EXISTS delivery_otp VARCHAR(6);"))
                conn.execute(text("ALTER TABLE dispatch_orders ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP;"))
    except Exception as e:
        print("[DATABASE SCHEMA EXTENSION NOTICE]", e)

def init_db_if_needed():
    try:
        import backend.models as models
        import bcrypt
        Base.metadata.create_all(bind=engine)
        ensure_db_schema_extensions()
        db = SessionLocal()

        # 1. Master SuperAdmin
        admin = db.query(models.User).filter(models.User.email == "admin@kwdc.com.np").first()
        if not admin:
            hashed = bcrypt.hashpw(b"Admin@123", bcrypt.gensalt()).decode("utf-8")
            admin = models.User(
                email="admin@kwdc.com.np",
                phone_number="+977-9801000001",
                full_name="KTM-WDC Master Admin",
                hashed_password=hashed,
                role=models.UserRole.SUPERADMIN,
                is_active=True,
                is_verified=True,
                kyc_status=models.KycStatus.VERIFIED
            )
            db.add(admin)
            print("[DATABASE INIT] Master Admin created: admin@kwdc.com.np / Admin@123")

        # 2. Seed Property Owner for Audit
        owner = db.query(models.User).filter(models.User.email == "owner_audit@kwdc.com.np").first()
        if not owner:
            hashed = bcrypt.hashpw(b"Owner@123", bcrypt.gensalt()).decode("utf-8")
            owner = models.User(
                email="owner_audit@kwdc.com.np",
                phone_number="+977-9841223344",
                full_name="Ram Bahadur Shrestha",
                hashed_password=hashed,
                role=models.UserRole.PROPERTY_OWNER,
                operating_location="Kathmandu Valley",
                is_active=True,
                is_verified=True,
                kyc_status=models.KycStatus.VERIFIED
            )
            db.add(owner)

        # 3. Seed Commercial Client for Audit
        client = db.query(models.User).filter(models.User.email == "client_audit@kwdc.com.np").first()
        if not client:
            hashed = bcrypt.hashpw(b"Client@123", bcrypt.gensalt()).decode("utf-8")
            client = models.User(
                email="client_audit@kwdc.com.np",
                phone_number="+977-9851098765",
                full_name="Kathmandu FMCG Distributors",
                hashed_password=hashed,
                role=models.UserRole.COMMERCIAL_CLIENT,
                operating_location="Kathmandu Valley",
                is_active=True,
                is_verified=True,
                kyc_status=models.KycStatus.PENDING_SUBMISSION
            )
            db.add(client)

        # 4. Seed Fleet Partner for Audit
        fleet_user = db.query(models.User).filter(models.User.email == "fleet_audit@kwdc.com.np").first()
        if not fleet_user:
            hashed = bcrypt.hashpw(b"Fleet@123", bcrypt.gensalt()).decode("utf-8")
            fleet_user = models.User(
                email="fleet_audit@kwdc.com.np",
                phone_number="+977-9811223344",
                full_name="Nepal Freight Logistics",
                hashed_password=hashed,
                role=models.UserRole.FLEET_PARTNER,
                operating_location="Kathmandu Valley",
                is_active=True,
                is_verified=True,
                kyc_status=models.KycStatus.PENDING_SUBMISSION
            )
            db.add(fleet_user)

        # 5. Seed Warehouse Incharge for Audit
        incharge_user = db.query(models.User).filter(models.User.email == "incharge_audit@kwdc.com.np").first()
        if not incharge_user:
            hashed = bcrypt.hashpw(b"Incharge@123", bcrypt.gensalt()).decode("utf-8")
            incharge_user = models.User(
                email="incharge_audit@kwdc.com.np",
                phone_number="+977-9801122334",
                full_name="Bikram Karki (On-Site Incharge)",
                hashed_password=hashed,
                role=models.UserRole.WAREHOUSE_INCHARGE,
                operating_location="Kathmandu",
                is_active=True,
                is_verified=True,
                kyc_status=models.KycStatus.VERIFIED
            )
            db.add(incharge_user)

        db.commit()
        db.close()
    except Exception as e:
        print("[DATABASE INIT NOTICE]", e)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
