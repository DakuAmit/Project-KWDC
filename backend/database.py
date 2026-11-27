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
    connect_args = (
        {"check_same_thread": False}
        if "sqlite" in db_url
        else {"prepare_threshold": None, "connect_timeout": 8}
    )
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
        from sqlalchemy import text, inspect
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        def add_col_if_missing(table_name: str, col_name: str, col_def: str):
            if table_name not in existing_tables:
                return
            cols = [c["name"] for c in inspector.get_columns(table_name)]
            if col_name not in cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def};"))

        add_col_if_missing("drivers", "license_category", "VARCHAR(255) DEFAULT 'Category B (Van / Pickup / Light 4-Wheeler)'")
        add_col_if_missing("drivers", "id_document_type", "VARCHAR(50) DEFAULT 'CITIZENSHIP'")
        add_col_if_missing("drivers", "license_photo_front_url", "VARCHAR(500)")
        add_col_if_missing("drivers", "license_photo_back_url", "VARCHAR(500)")
        add_col_if_missing("drivers", "id_doc_front_url", "VARCHAR(500)")
        add_col_if_missing("drivers", "id_doc_back_url", "VARCHAR(500)")
        add_col_if_missing("drivers", "blood_group", "VARCHAR(10)")
        add_col_if_missing("drivers", "emergency_contact_name", "VARCHAR(255)")
        add_col_if_missing("drivers", "emergency_contact_phone", "VARCHAR(50)")
        add_col_if_missing("drivers", "has_clean_traffic_record", "BOOLEAN DEFAULT 1" if is_sqlite else "BOOLEAN DEFAULT TRUE")
        add_col_if_missing("drivers", "is_standby", "BOOLEAN DEFAULT 0" if is_sqlite else "BOOLEAN DEFAULT FALSE")
        add_col_if_missing("drivers", "login_pin", "VARCHAR(255) DEFAULT '1234'")

        if not is_sqlite and "drivers" in existing_tables:
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE drivers ALTER COLUMN license_category TYPE VARCHAR(255);"))
            except Exception:
                pass

        add_col_if_missing("users", "fleet_operator_type", "VARCHAR(50)")

        add_col_if_missing("dispatch_orders", "reassigned_from_vehicle_id", "INTEGER")
        add_col_if_missing("dispatch_orders", "reassigned_from_driver_id", "INTEGER")
        add_col_if_missing("dispatch_orders", "reassignment_reason", "VARCHAR(500)")
        add_col_if_missing("dispatch_orders", "delivery_otp", "VARCHAR(6)")
        add_col_if_missing("dispatch_orders", "delivered_at", "TIMESTAMP")
        add_col_if_missing("dispatch_orders", "benchmark_fare_npr", "FLOAT")
        add_col_if_missing("dispatch_orders", "client_offered_fare_npr", "FLOAT")
        add_col_if_missing("dispatch_orders", "cargo_weight_kg", "FLOAT DEFAULT 1000.0")

        add_col_if_missing("warehouse_requests", "booking_duration_type", "VARCHAR(20) DEFAULT 'MONTHLY'")
        add_col_if_missing("warehouse_requests", "duration_value", "INTEGER DEFAULT 3")
        add_col_if_missing("warehouse_requests", "duration_days", "INTEGER DEFAULT 90")
        add_col_if_missing("warehouse_requests", "client_intended_use", "VARCHAR(255) DEFAULT 'Commercial Freight'")
        add_col_if_missing("warehouse_requests", "advance_payment_status", "VARCHAR(50) DEFAULT 'PAYMENT_DUE'")
        add_col_if_missing("warehouse_requests", "overdue_since", "TIMESTAMP")
        add_col_if_missing("warehouse_requests", "default_countdown_deadline", "TIMESTAMP")
        add_col_if_missing("warehouse_requests", "is_gate_frozen", "BOOLEAN DEFAULT 0" if is_sqlite else "BOOLEAN DEFAULT FALSE")
        add_col_if_missing("warehouse_requests", "is_forfeited", "BOOLEAN DEFAULT 0" if is_sqlite else "BOOLEAN DEFAULT FALSE")
        add_col_if_missing("warehouse_requests", "last_reminder_sent_at", "TIMESTAMP")
        add_col_if_missing("warehouse_requests", "last_reminder_stage", "VARCHAR(50)")
        add_col_if_missing("warehouses", "client_rate_per_sqft", "FLOAT")

        add_col_if_missing("heavy_equipments", "registration_no", "VARCHAR(100)")
        add_col_if_missing("heavy_equipments", "hourly_rate_npr", "FLOAT DEFAULT 1500.0")
        add_col_if_missing("heavy_equipments", "operator_included", "BOOLEAN DEFAULT 1" if is_sqlite else "BOOLEAN DEFAULT TRUE")
        add_col_if_missing("heavy_equipments", "photo_url", "VARCHAR(500)")
        add_col_if_missing("heavy_equipments", "is_approved", "BOOLEAN DEFAULT 0" if is_sqlite else "BOOLEAN DEFAULT FALSE")

        add_col_if_missing("equipment_jobs", "site_address", "VARCHAR(255) DEFAULT 'Kathmandu Valley Facility'")
        add_col_if_missing("equipment_jobs", "notes", "VARCHAR(500)")
        add_col_if_missing("equipment_jobs", "base_cost_npr", "FLOAT DEFAULT 0.0")
        add_col_if_missing("equipment_jobs", "platform_fee_npr", "FLOAT DEFAULT 0.0")
        add_col_if_missing("equipment_jobs", "vat_13_percent", "FLOAT DEFAULT 0.0")

        add_col_if_missing("dispatch_orders", "commission_settled", "BOOLEAN DEFAULT 0" if is_sqlite else "BOOLEAN DEFAULT FALSE")
        add_col_if_missing("dispatch_orders", "commission_settled_at", "TIMESTAMP")

        add_col_if_missing("stock_items", "booking_id", "INTEGER")
        add_col_if_missing("stock_items", "reserved_quantity", "INTEGER DEFAULT 0")
        add_col_if_missing("stock_items", "dispatched_quantity", "INTEGER DEFAULT 0")
        add_col_if_missing("stock_items", "verification_status", "VARCHAR(40) DEFAULT 'PENDING_DOCK_VERIFICATION'")
        add_col_if_missing("stock_items", "bay_rack_location", "VARCHAR(100) DEFAULT 'Zone A / Bay-1'")

        add_col_if_missing("gate_passes", "stock_item_id", "INTEGER")
        add_col_if_missing("gate_passes", "booking_id", "INTEGER")

        add_col_if_missing("users", "equipment_operator_type", "VARCHAR(50)")
        add_col_if_missing("equipment_jobs", "operator_id", "INTEGER")
        add_col_if_missing("equipment_jobs", "commission_settled", "BOOLEAN DEFAULT 0" if is_sqlite else "BOOLEAN DEFAULT FALSE")
        add_col_if_missing("stock_insurance_policies", "payment_status", "VARCHAR(50) DEFAULT 'UNPAID'")
        add_col_if_missing("stock_insurance_policies", "payment_ref", "VARCHAR(120)")
        add_col_if_missing("warehouses", "video_urls", "TEXT")
        add_col_if_missing("stock_items", "packing_list_doc_url", "VARCHAR(500)")
        add_col_if_missing("media_assets", "category", "VARCHAR(60) DEFAULT 'GENERAL'")
        add_col_if_missing("media_assets", "file_size_bytes", "INTEGER DEFAULT 0")
        add_col_if_missing("media_assets", "storage_provider", "VARCHAR(40) DEFAULT 'POSTGRES_FALLBACK'")
        add_col_if_missing("media_assets", "cloud_url", "VARCHAR(500)")
        add_col_if_missing("media_assets", "storage_path", "VARCHAR(500)")
        if not is_sqlite:
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE media_assets ALTER COLUMN data_base64 DROP NOT NULL"))
            except Exception:
                pass
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

        # Optional Demo/Audit Users (only seeded if SEED_AUDIT_USERS=true)
        if os.getenv("SEED_AUDIT_USERS", "false").lower() == "true":
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

        # 6. Default Platform Configuration (Margin & Tariff Base Formula)
        cfg = db.query(models.PlatformConfig).filter(models.PlatformConfig.config_key == "DEFAULT_CONFIG").first()
        if not cfg:
            cfg = models.PlatformConfig(
                config_key="DEFAULT_CONFIG",
                platform_margin_percent=10.0,
                flag_drop_van_pickup=1200.0,
                flag_drop_mini_truck=1800.0,
                flag_drop_heavy_truck=3200.0,
                flag_drop_container_trailer=5000.0,
                rate_per_km_van_pickup=65.0,
                rate_per_km_mini_truck=85.0,
                rate_per_km_heavy_truck=125.0,
                rate_per_km_container_trailer=175.0,
                weight_rate_per_tonne=150.0,
                vat_rate_percent=13.0,
                fuel_multiplier=1.0
            )
            db.add(cfg)

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
