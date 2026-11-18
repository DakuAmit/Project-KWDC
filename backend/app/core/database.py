from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

# Connection options and URL driver normalization
db_url = settings.DATABASE_URL.strip()

# Supabase direct host (db.xxx.supabase.co) only resolves to IPv6, which is unsupported on AWS Lambda/Vercel serverless.
# Automatically rewrite to Supabase IPv4 Connection Pooler if direct host is configured:
if "db.wnecdwukwnqyeiiseotp.supabase.co" in db_url:
    db_url = db_url.replace("db.wnecdwukwnqyeiiseotp.supabase.co", "aws-1-ap-northeast-1.pooler.supabase.com")
    if "postgres:" in db_url and "postgres.wnecdwukwnqyeiiseotp:" not in db_url:
        db_url = db_url.replace("postgres:", "postgres.wnecdwukwnqyeiiseotp:", 1)

if db_url.startswith("postgresql://"):
    # Normalize postgresql:// to explicit driver to ensure compatibility on serverless runtimes
    try:
        import psycopg
    except ImportError:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

is_sqlite = db_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
engine_kwargs = {"connect_args": connect_args, "echo": False}

if not is_sqlite:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 300

engine = create_engine(
    db_url,
    **engine_kwargs
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
