"""
Kathmandu Warehousing & Distribution Center (KTM-WDC)
Transactional Email Service via Brevo (Sendinblue) API
"""
import requests
from typing import Optional, Dict, Any
from backend.config import settings

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

def send_email_via_brevo(
    to_email: str,
    to_name: str,
    subject: str,
    html_content: str
) -> bool:
    """
    Dispatches a transactional email using Brevo REST API v3.
    """
    if not settings.BREVO_API_KEY or "your-brevo" in settings.BREVO_API_KEY:
        print(f"[EMAIL MOCK] To: {to_email} | Subject: {subject}")
        return True

    headers = {
        "accept": "application/json",
        "api-key": settings.BREVO_API_KEY,
        "content-type": "application/json"
    }

    payload = {
        "sender": {
            "name": settings.BREVO_SENDER_NAME,
            "email": settings.BREVO_SENDER_EMAIL
        },
        "to": [
            {
                "email": to_email,
                "name": to_name
            }
        ],
        "subject": subject,
        "htmlContent": html_content
    }

    try:
        response = requests.post(BREVO_API_URL, json=payload, headers=headers, timeout=10)
        if response.status_code in (200, 201, 202):
            print(f"[BREVO EMAIL SUCCESS] Sent to {to_email}: {subject}")
            return True
        else:
            print(f"[BREVO EMAIL ERROR {response.status_code}] {response.text}")
            return False
    except Exception as e:
        print(f"[BREVO EXCEPTION] Failed to send email: {e}")
        return False

def send_contract_approval_email(owner_email: str = None, owner_name: str = "Property Owner", warehouse_title: str = "Commercial Facility", contract_text: str = None, **kwargs):
    """
    Dispatches the Master Commercial Lease Agreement to the Property Owner
    once approved by SuperAdmin.
    """
    target_email = owner_email or kwargs.get("to_email")
    if not target_email:
        return False
    contract_content = contract_text or kwargs.get("contract_url") or "Master Commercial Lease Agreement on file."
    formatted_contract = contract_content.replace("\n", "<br>")
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 650px; margin: auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 8px; color: #1e293b;">
        <div style="background-color: #0f172a; padding: 15px 20px; border-radius: 6px; color: white; text-align: center;">
            <h2 style="margin: 0; font-size: 20px;">KTM-WDC Master Commercial Storage Agreement</h2>
            <p style="margin: 5px 0 0 0; font-size: 13px; color: #94a3b8;">Kathmandu Warehousing & Distribution Center</p>
        </div>
        
        <p style="margin-top: 20px; font-size: 15px;">Dear <strong>{owner_name}</strong>,</p>
        <p style="font-size: 14px; line-height: 1.6;">
            We are pleased to inform you that your property listing <strong>"{warehouse_title}"</strong> has been thoroughly audited and 
            <span style="color: #16a34a; font-weight: bold;">APPROVED</span> for commercial operations by the KTM-WDC Real Estate Directorate.
        </p>

        <div style="background-color: #f8fafc; border-left: 4px solid #2563eb; padding: 15px; margin: 15px 0; font-size: 13px; line-height: 1.5;">
            <strong>Important Operating Covenant:</strong><br>
            KTM-WDC maintains <strong>Rs. 0 holding liability</strong> while spaces are awaiting tenant assignment. Rental cashflow commences on the calendar day an approved commercial lease is activated.
            Your property features are now permanently secured and administrative operations are governed by KWDC Admin.
        </div>

        <h4 style="margin-bottom: 8px;">Executed Master Agreement:</h4>
        <div style="background-color: #1e293b; color: #f1f5f9; padding: 15px; border-radius: 4px; font-family: monospace; font-size: 12px; max-height: 300px; overflow-y: auto;">
            {formatted_contract}
        </div>

        <p style="font-size: 13px; color: #64748b; margin-top: 25px; text-align: center;">
            This is an automated legal communication from KTM-WDC Pvt. Ltd., Kathmandu, Nepal.
        </p>
    </div>
    """
    return send_email_via_brevo(
        to_email=target_email,
        to_name=owner_name,
        subject=f"[KTM-WDC] Master Storage Lease Executed - {warehouse_title}",
        html_content=html
    )

def send_otp_email(to_email: str, to_name: str, otp_code: str):
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h3 style="color: #0f172a; margin-top: 0;">KTM-WDC Account Verification</h3>
        <p>Namaste <strong>{to_name}</strong>,</p>
        <p>Your one-time 6-digit OTP verification code for Kathmandu Warehousing & Distribution Center is:</p>
        <div style="text-align: center; margin: 25px 0;">
            <span style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #2563eb; background-color: #eff6ff; padding: 10px 25px; border-radius: 6px; border: 1px dashed #93c5fd;">
                {otp_code}
            </span>
        </div>
        <p style="font-size: 13px; color: #64748b;">This OTP is valid for 10 minutes. If you did not request this, please disregard this email.</p>
    </div>
    """
    return send_email_via_brevo(
        to_email=to_email,
        to_name=to_name,
        subject=f"Your KTM-WDC OTP Code: {otp_code}",
        html_content=html
    )
