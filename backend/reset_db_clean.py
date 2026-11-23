"""
KTM-WDC Database Reset & Clean Script
Empties all tables in Supabase PostgreSQL completely so you start 100% fresh.
Optionally creates one clean Master SuperAdmin account.
"""
from sqlalchemy import text
from passlib.context import CryptContext
from backend.database import engine, Base, SessionLocal
from backend.models import User, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def reset_db_clean(create_admin: bool = True):
    print("Emptying all tables in Supabase PostgreSQL...")
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        conn.commit()
        print("Schema cleared.")

    print("Re-creating all clean schema tables...")
    Base.metadata.create_all(bind=engine)

    if create_admin:
        db = SessionLocal()
        admin = User(
            email="admin@kwdc.com.np",
            phone_number="+977-9801000001",
            full_name="KTM-WDC Master Admin",
            hashed_password=pwd_context.hash("Admin@123"),
            role=UserRole.SUPERADMIN,
            is_active=True,
            is_verified=True
        )
        db.add(admin)
        db.commit()
        db.close()
        print("Master Admin account created: admin@kwdc.com.np / Admin@123")
    
    print("DATABASE IS NOW COMPLETELY FRESH AND EMPTY OF ALL SAMPLE DATA!")

if __name__ == "__main__":
    reset_db_clean(create_admin=True)
