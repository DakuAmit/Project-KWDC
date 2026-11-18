import os
import logging
from typing import Optional, List, Union
import httpx

from app.core.config import settings

logger = logging.getLogger("kwdc.email")

class EmailService:
    RESEND_API_URL = "https://api.resend.com/emails"

    @classmethod
    def send_email(
        cls,
        to: Union[str, List[str]],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> dict:
        """
        Sends transactional email via Resend REST API using httpx.
        Falls back gracefully with logging if RESEND_API_KEY is not configured yet.
        """
        recipients = [to] if isinstance(to, str) else to
        api_key = settings.RESEND_API_KEY.strip()

        if not api_key:
            logger.warning(
                f"⚠️ [EmailService] RESEND_API_KEY is not configured. "
                f"Simulating email dispatch to: {recipients} | Subject: '{subject}'"
            )
            return {
                "id": "simulated_dev_id",
                "status": "simulated",
                "to": recipients,
                "subject": subject
            }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": recipients,
            "subject": subject,
            "html": html_content
        }
        if text_content:
            payload["text"] = text_content

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(cls.RESEND_API_URL, headers=headers, json=payload)
                if response.status_code in [200, 201]:
                    data = response.json()
                    logger.info(f"✅ [EmailService] Email sent successfully via Resend. ID: {data.get('id')}")
                    return data
                else:
                    logger.error(
                        f"❌ [EmailService] Resend API error ({response.status_code}): {response.text}"
                    )
                    return {"error": response.text, "status_code": response.status_code}
        except Exception as e:
            logger.error(f"❌ [EmailService] Network exception while contacting Resend: {str(e)}")
            return {"error": str(e)}

    @classmethod
    def send_verification_email(cls, to_email: str, name: str, token: str, base_url: str = "") -> dict:
        origin = base_url or settings.FRONTEND_URL or "https://project-kwdc.vercel.app"
        verify_url = f"{origin}/verify-email?token={token}"

        subject = "Verify Your KTM-WDC Account"
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; margin: 0; padding: 24px; }}
                .container {{ max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #f97316, #ea580c); padding: 32px; text-align: center; color: #ffffff; }}
                .content {{ padding: 32px; color: #334155; line-height: 1.6; font-size: 15px; }}
                .btn {{ display: inline-block; background: #f97316; color: #ffffff !important; font-weight: 600; padding: 12px 28px; border-radius: 10px; text-decoration: none; margin: 20px 0; }}
                .footer {{ background: #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #64748b; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 24px; letter-spacing: -0.5px;">KTM-WDC</h1>
                    <p style="margin: 4px 0 0 0; opacity: 0.9; font-size: 14px;">Nepal Commercial Logistics Platform</p>
                </div>
                <div class="content">
                    <h2 style="color: #0f172a; margin-top: 0;">Welcome, {name}!</h2>
                    <p>Thank you for registering on KTM-WDC. Please verify your email address to activate your logistics dashboard, bookings, and freight telemetry services.</p>
                    <div style="text-align: center;">
                        <a href="{verify_url}" class="btn" target="_blank">Verify Email Address</a>
                    </div>
                    <p style="font-size: 13px; color: #64748b;">Or paste this link into your browser:</p>
                    <p style="font-size: 12px; color: #f97316; word-break: break-all;">{verify_url}</p>
                </div>
                <div class="footer">
                    Kathmandu Warehousing & Distribution Center &bull; Kathmandu, Nepal<br>
                    Secured with Resend &bull; &copy; 2026 KTM-WDC
                </div>
            </div>
        </body>
        </html>
        """
        return cls.send_email(to_email, subject, html)

    @classmethod
    def send_password_reset_email(cls, to_email: str, name: str, token: str, base_url: str = "") -> dict:
        origin = base_url or settings.FRONTEND_URL or "https://project-kwdc.vercel.app"
        reset_url = f"{origin}/reset-password?token={token}"

        subject = "Reset Your KTM-WDC Password"
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; margin: 0; padding: 24px; }}
                .container {{ max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; }}
                .header {{ background: #0f172a; padding: 32px; text-align: center; color: #ffffff; }}
                .content {{ padding: 32px; color: #334155; line-height: 1.6; font-size: 15px; }}
                .btn {{ display: inline-block; background: #f97316; color: #ffffff !important; font-weight: 600; padding: 12px 28px; border-radius: 10px; text-decoration: none; margin: 20px 0; }}
                .footer {{ background: #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #64748b; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 24px; color: #f97316;">KTM-WDC</h1>
                    <p style="margin: 4px 0 0 0; opacity: 0.9; font-size: 14px;">Password Recovery Request</p>
                </div>
                <div class="content">
                    <h2 style="color: #0f172a; margin-top: 0;">Hello, {name}</h2>
                    <p>We received a request to reset your password for your KTM-WDC portal account. Click the button below to choose a new password.</p>
                    <div style="text-align: center;">
                        <a href="{reset_url}" class="btn" target="_blank">Reset My Password</a>
                    </div>
                    <p style="font-size: 13px; color: #64748b;">This password reset link is valid for <strong>1 hour</strong>. If you did not make this request, you can safely ignore this email.</p>
                    <p style="font-size: 12px; color: #f97316; word-break: break-all;">{reset_url}</p>
                </div>
                <div class="footer">
                    Kathmandu Warehousing & Distribution Center &bull; Kathmandu, Nepal<br>
                    Secured with Resend &bull; &copy; 2026 KTM-WDC
                </div>
            </div>
        </body>
        </html>
        """
        return cls.send_email(to_email, subject, html)

    @classmethod
    def send_password_changed_notification(cls, to_email: str, name: str) -> dict:
        subject = "Security Notice: Your KTM-WDC Password Was Changed"
        html = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f8fafc; padding: 24px;">
            <div style="max-width: 500px; margin: 0 auto; background: white; border-radius: 12px; padding: 24px; border: 1px solid #e2e8f0;">
                <h2 style="color: #0f172a; margin-top: 0;">Password Changed Successfully</h2>
                <p>Hello {name}, your KTM-WDC portal password was successfully updated just now.</p>
                <p>If you did not perform this change, please contact KTM-WDC Security immediately.</p>
                <p style="color: #64748b; font-size: 12px;">Kathmandu Warehousing & Distribution Center</p>
            </div>
        </body>
        </html>
        """
        return cls.send_email(to_email, subject, html)
