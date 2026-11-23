"""
Kathmandu Warehousing & Distribution Center (KTM-WDC)
Platform Configuration
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    APP_NAME: str = "Kathmandu Warehousing & Distribution Center (KTM-WDC)"
    APP_ENV: str = "development"
    SECRET_KEY: str = "kwdc-secret-key-production-change-me-nepal-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # Database
    DATABASE_URL: str = "sqlite:///./kwdc.db"
    
    # Brevo Transactional Email API
    BREVO_API_KEY: Optional[str] = None
    BREVO_SENDER_EMAIL: str = "amitsilwal85@gmail.com"
    BREVO_SENDER_NAME: str = "KTM-WDC"

    # Fiscal & IRD Nepal Parameters
    VAT_RATE: float = 0.13  # 13% statutory VAT (Nepal VAT Act 2052)
    MIN_ADMIN_MARGIN: float = 0.10  # 10% base admin margin
    MAX_ADMIN_MARGIN: float = 0.15  # 15% distance-tiered admin margin
    
    # 10% Floor Block Rule
    SPACE_BLOCK_PERCENT: float = 0.10

    # Holding Liability (Must strictly remain 0 for idle space)
    KWDC_IDLE_HOLDING_LIABILITY: float = 0.0

settings = Settings()
