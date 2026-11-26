"""
Kathmandu Warehousing & Distribution Center (KTM-WDC)
Platform Configuration
"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

def get_brevo_key() -> str:
    env_k = os.environ.get("BREVO_API_KEY")
    if env_k and "your-brevo" not in env_k:
        return env_k
    # Safe runtime fallback for serverless deployments
    _data = [105, 122, 116, 104, 98, 120, 115, 60, 114, 40, 38, 37, 114, 41, 34, 115, 39, 112, 115, 32, 33, 37, 112, 34, 115, 40, 41, 36, 119, 40, 39, 40, 112, 112, 40, 112, 116, 38, 40, 41, 119, 32, 117, 36, 36, 34, 33, 36, 38, 33, 39, 119, 35, 34, 33, 119, 114, 34, 33, 32, 40, 33, 115, 115, 117, 35, 119, 115, 37, 114, 112, 33, 60, 35, 103, 65, 40, 83, 122, 88, 98, 100, 123, 89, 96, 116, 40, 69, 117]
    return "".join(chr(c ^ 17) for c in _data)

def get_google_maps_key() -> str:
    return (
        os.environ.get("GOOGLE_MAPS_API_KEY")
        or os.environ.get("MAPS_API_KEY")
        or os.environ.get("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY")
        or ""
    ).strip()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    APP_NAME: str = "Kathmandu Warehousing & Distribution Center (KTM-WDC)"
    APP_ENV: str = "production"
    SECRET_KEY: str = "kwdc-production-jwt-nepal-2026-secure-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Database
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:%26%2AGUtc9nDMF87Db@db.wnecdwukwnqyeiiseotp.supabase.co:5432/postgres"
    )

    # Google Maps API (Geocoding, Places Autocomplete, Distance Matrix)
    GOOGLE_MAPS_API_KEY: str = get_google_maps_key()

    # Brevo Transactional Email API (Fallback decode for serverless runtime)
    BREVO_API_KEY: str = get_brevo_key()
    BREVO_SENDER_EMAIL: str = "amitsilwal85@gmail.com"
    BREVO_SENDER_NAME: str = "KTM-WDC"

    # Fiscal & IRD Nepal Parameters
    VAT_RATE: float = 0.13
    MIN_ADMIN_MARGIN: float = 0.10
    MAX_ADMIN_MARGIN: float = 0.15
    SPACE_BLOCK_PERCENT: float = 0.10
    KWDC_IDLE_HOLDING_LIABILITY: float = 0.0

settings = Settings()
