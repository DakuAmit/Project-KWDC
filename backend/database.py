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
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def ensure_db_schema_extensions():
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            # Drivers table extensions
            conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS license_category VARCHAR(50) DEFAULT 'Category B (Delivery Van / Pickup)';"))
            conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS license_photo_front_url VARCHAR(500);"))
            conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS license_photo_back_url VARCHAR(500);"))
            conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS blood_group VARCHAR(10);"))
            conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS emergency_contact_name VARCHAR(255);"))
            conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS emergency_contact_phone VARCHAR(50);"))
            conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS has_clean_traffic_record BOOLEAN DEFAULT TRUE;"))
    except Exception as e:
        print("[DATABASE SCHEMA EXTENSION NOTICE]", e)

def init_db_if_needed():
    try:
        import backend.models as models
        import bcrypt
        Base.metadata.create_all(bind=engine)
        ensure_db_schema_extensions()
        db = SessionLocal()
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
                is_verified=True
            )
            db.add(admin)
            db.commit()
            print("[DATABASE INIT] Master Admin created: admin@kwdc.com.np / Admin@123")
        db.close()
    except Exception as e:
        print("[DATABASE INIT NOTICE]", e)

# Auto-initialize
init_db_if_needed()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
