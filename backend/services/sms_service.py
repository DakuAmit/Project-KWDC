"""
Kathmandu Warehousing & Distribution Center (KTM-WDC)
Transactional SMS Service
Supports:
  1. Sparrow SMS (Nepal production & testing via SPARROW_SMS_TOKEN)
  2. Twilio REST API (Free trial testing via TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER)
  3. Zero-cost Sandbox Outbox Log (persisted to SmsOutboxLog + readable in Admin Console) when no paid key is set.
"""
from typing import Optional
import requests
from sqlalchemy.orm import Session
from backend.config import settings
from backend.models import SmsOutboxLog


def get_sms_provider_mode() -> str:
    if settings.SPARROW_SMS_TOKEN:
        return "SPARROW_SMS"
    if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER:
        return "TWILIO"
    return "SANDBOX_OUTBOX"


def _normalize_nepal_phone(phone: str) -> str:
    cleaned = (phone or "").strip().replace(" ", "").replace("-", "")
    if cleaned.startswith("+977"):
        return cleaned[4:]
    if cleaned.startswith("977") and len(cleaned) >= 13:
        return cleaned[3:]
    return cleaned


def send_sms(
    db: Optional[Session],
    phone_number: str,
    message: str,
    purpose: str = "OTP",
) -> dict:
    """
    Dispatches an SMS via Sparrow SMS or Twilio if configured, otherwise logs
    the message into the Sandbox Outbox DB table so QA & testing work immediately.
    """
    provider = get_sms_provider_mode()
    status_val = "QUEUED_SANDBOX"
    ext_ref = None

    if provider == "SPARROW_SMS":
        try:
            resp = requests.post(
                "https://api.sparrowsms.com/v2/sms/",
                data={
                    "token": settings.SPARROW_SMS_TOKEN,
                    "from": settings.SPARROW_SMS_FROM,
                    "to": _normalize_nepal_phone(phone_number),
                    "text": message,
                },
                timeout=10,
            )
            if resp.status_code in (200, 201):
                status_val = "SENT"
                ext_ref = resp.text[:180]
            else:
                status_val = f"FAILED_{resp.status_code}"
                ext_ref = resp.text[:180]
        except Exception as exc:
            status_val = "ERROR"
            ext_ref = str(exc)[:180]

    elif provider == "TWILIO":
        try:
            to_e164 = phone_number.strip()
            if not to_e164.startswith("+"):
                to_e164 = f"+977{_normalize_nepal_phone(to_e164)}"
            resp = requests.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                data={
                    "From": settings.TWILIO_FROM_NUMBER,
                    "To": to_e164,
                    "Body": message,
                },
                timeout=10,
            )
            if resp.status_code in (200, 201):
                status_val = "SENT"
                ext_ref = (resp.json() or {}).get("sid")
            else:
                status_val = f"FAILED_{resp.status_code}"
                ext_ref = resp.text[:180]
        except Exception as exc:
            status_val = "ERROR"
            ext_ref = str(exc)[:180]
    else:
        print(f"[SMS SANDBOX OUTBOX] To: {phone_number} | {purpose} | {message}")

    log_id = None
    if db is not None:
        try:
            entry = SmsOutboxLog(
                phone_number=phone_number,
                message=message,
                purpose=purpose,
                provider=provider,
                status=status_val,
                external_ref=ext_ref,
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            log_id = entry.id
        except Exception as exc:
            db.rollback()
            print(f"[SMS OUTBOX LOG WARNING] {exc}")

    return {
        "dispatched": status_val in ("SENT", "QUEUED_SANDBOX"),
        "provider": provider,
        "status": status_val,
        "log_id": log_id,
    }
