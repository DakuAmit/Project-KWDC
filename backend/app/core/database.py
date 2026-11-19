import os
import re
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings

# Connection options and URL driver normalization
db_url = settings.DATABASE_URL.strip()

# 1. Supabase direct host (db.xxx.supabase.co) only resolves to IPv6, which is unsupported on AWS Lambda/Vercel serverless.
# Automatically rewrite ANY Supabase direct host to the IPv4 Connection Pooler:
supabase_direct_match = re.search(r'db\.([a-z0-9]+)\.supabase\.co', db_url)
if supabase_direct_match:
    project_ref = supabase_direct_match.group(1)
    db_url = db_url.replace(supabase_direct_match.group(0), "aws-1-ap-northeast-1.pooler.supabase.com")
    # Ensure pooler username includes the project ref prefix: postgres.<project_ref>
    if "postgres:" in db_url and f"postgres.{project_ref}:" not in db_url:
        db_url = re.sub(r'://postgres:', f'://postgres.{project_ref}:', db_url)

# 2. Driver normalization for PostgreSQL
if db_url.startswith("postgresql://"):
    try:
        import psycopg
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    except ImportError:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgres://"):
    try:
        import psycopg
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    except ImportError:
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)

is_sqlite = db_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
engine_kwargs = {"connect_args": connect_args, "echo": False}

if not is_sqlite:
    is_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
    if is_serverless:
        # NullPool is recommended for serverless environments to prevent socket reuse timeouts
        engine_kwargs["poolclass"] = NullPool
    else:
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
