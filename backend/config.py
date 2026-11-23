"""
Kathmandu Warehousing & Distribution Center (KTM-WDC)
Platform Configuration
"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

def get_default_db_url():
    if os.environ.get("VERCEL"):
        return "sqlite:////tmp/kwdc.db"
    return "sqlite:///./kwdc.db"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    APP_NAME: str = "Kathmandu Warehousing & Distribution Center (KTM-WDC)"
    APP_ENV: str = "development"
    SECRET_KEY: str = "kwdc-secret-key-production-change-me-nepal-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Database
    DATABASE_URL: str = get_default_db_url()

    # Brevo Transactional Email API
    BREVO_API_KEY: Optional[str] = None
    BREVO_SENDER_EMAIL: str = "amitsilwal85@gmail.com"
    BREVO_SENDER_NAME: str = "KTM-WDC"

    # Fiscal & IRD Nepal Parameters
    VAT_RATE: float = 0.13
    MIN_ADMIN_MARGIN: float = 0.10
    MAX_ADMIN_MARGIN: float = 0.15
    SPACE_BLOCK_PERCENT: float = 0.10
    KWDC_IDLE_HOLDING_LIABILITY: float = 0.0

settings = Settings()
