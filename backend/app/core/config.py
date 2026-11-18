import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="allow")

    PROJECT_NAME: str = "KTM-WDC (Kathmandu Warehousing & Distribution Center)"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "kwdc-production-super-secret-key-change-in-production-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    SESSION_COOKIE_NAME: str = "kwdc_session"

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./kwdc.db")
    KWDC_DEMO_PASSWORD: str = os.getenv("KWDC_DEMO_PASSWORD", "KwdcNew2026!")

    # Resend Email Configuration
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL: str = os.getenv("RESEND_FROM_EMAIL", "KTM-WDC <onboarding@resend.dev>")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "")

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
