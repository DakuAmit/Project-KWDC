import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    PROJECT_NAME: str = "KTM-WDC (Kathmandu Warehousing & Distribution Center)"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "kwdc-production-super-secret-key-change-in-production-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    SESSION_COOKIE_NAME: str = "kwdc_session"

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./kwdc.db")
    KWDC_DEMO_PASSWORD: str = os.getenv("KWDC_DEMO_PASSWORD", "KwdcNew2026!")

    # AI Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "free")

    # Payment Gateways (Nepal)
    KHALTI_PUBLIC_KEY: str = os.getenv("KHALTI_PUBLIC_KEY", "")
    KHALTI_SECRET_KEY: str = os.getenv("KHALTI_SECRET_KEY", "")
    KHALTI_BASE_URL: str = os.getenv("KHALTI_BASE_URL", "https://khalti.com/api/v2")

    ESEWA_PRODUCT_CODE: str = os.getenv("ESEWA_PRODUCT_CODE", "EPAYTEST")
    ESEWA_SECRET_KEY: str = os.getenv("ESEWA_SECRET_KEY", "8gBm/:&EnhH.1/q")
    ESEWA_BASE_URL: str = os.getenv("ESEWA_BASE_URL", "https://rc-epay.esewa.com.np")

    STRIPE_KEY: str = os.getenv("STRIPE_KEY", "")
    STRIPE_SECRET: str = os.getenv("STRIPE_SECRET", "")

    # Kataho Nepal
    KATAHO_API_URL: str = os.getenv("KATAHO_API_URL", "https://api.kataho.app/v1")
    KATAHO_API_KEY: str = os.getenv("KATAHO_API_KEY", "")

settings = Settings()
