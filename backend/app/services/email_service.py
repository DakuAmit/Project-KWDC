import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import Optional, List, Union
import httpx

from app.core.config import settings

logger = logging.getLogger("kwdc.email")

class EmailService:
    RESEND_API_URL = "https://api.resend.com/emails"

    @classmethod
    def send_via_smtp(
        cls,
        recipients: List[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> dict:
        """
        Sends email via standard SMTP (e.g. Gmail using Google App Password).
        Requires NO custom domain and sends to ANY recipient.
        """
        sender_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
        sender_name = settings.SMTP_FROM_NAME or "KTM-WDC Logistics"
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((sender_name, sender_email))
        msg["To"] = ", ".join(recipients)

        if text_content:
            msg.attach(MIMEText(text_content, "plain", "utf-8"))
        if html_content:
            msg.attach(MIMEText(html_content, "html", "utf-8"))

        try:
            port = settings.SMTP_PORT
            if port == 465:
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, port, timeout=12.0)
            else:
                server = smtplib.SMTP(settings.SMTP_HOST, port, timeout=12.0)
                if settings.SMTP_USE_TLS:
                    server.starttls()
            
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            
            server.sendmail(sender_email, recipients, msg.as_string())
            server.quit()
            logger.info(f"✅ [EmailService:SMTP] Dispatched email to {recipients} | Subject: '{subject}'")
            return {"status": "sent", "driver": "smtp", "recipients": recipients}
        except Exception as e:
            logger.error(f"❌ [EmailService:SMTP] Failed to send email via SMTP: {str(e)}")
            return {"error": str(e), "driver": "smtp"}

    BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

    @classmethod
    def send_via_brevo(
        cls,
        recipients: List[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> dict:
        """
        Sends transactional email via Brevo (formerly Sendinblue) REST API v3.
        Supports sending to ANY recipient with 300 free emails per day without custom domain.
        """
        api_key = settings.BREVO_API_KEY.strip()
        sender_email = (
            settings.BREVO_SENDER_EMAIL.strip() or 
            settings.SMTP_FROM_EMAIL.strip() or 
            settings.SMTP_USER.strip() or 
            "app.netpack@gmail.com"
        )
        sender_name = settings.BREVO_SENDER_NAME.strip() or "KTM-WDC Logistics"

        headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json"
        }
        payload = {
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": email} for email in recipients],
            "subject": subject,
            "htmlContent": html_content
        }
        if text_content:
            payload["textContent"] = text_content

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(cls.BREVO_API_URL, headers=headers, json=payload)
                if res.status_code in [200, 201, 202]:
                    data = res.json()
                    logger.info(f"✅ [EmailService:Brevo] Email sent. Message ID: {data.get('messageId')}")
                    return {"status": "sent", "driver": "brevo", "message_id": data.get("messageId"), "data": data}
                else:
                    logger.error(f"❌ [EmailService:Brevo] API Error ({res.status_code}): {res.text}")
                    return {"error": res.text, "status_code": res.status_code, "driver": "brevo"}
        except Exception as e:
            logger.error(f"❌ [EmailService:Brevo] Exception: {str(e)}")
            return {"error": str(e), "driver": "brevo"}

    @classmethod
    def send_via_resend(
        cls,
        recipients: List[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> dict:
        """
        Sends email via Resend REST API using httpx.
        """
        headers = {
            "Authorization": f"Bearer {settings.RESEND_API_KEY.strip()}",
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
                res = client.post(cls.RESEND_API_URL, headers=headers, json=payload)
                if res.status_code in [200, 201]:
                    data = res.json()
                    logger.info(f"✅ [EmailService:Resend] Email sent. ID: {data.get('id')}")
                    return data
                else:
                    logger.error(f"❌ [EmailService:Resend] API Error ({res.status_code}): {res.text}")
                    return {"error": res.text, "status_code": res.status_code, "driver": "resend"}
        except Exception as e:
            logger.error(f"❌ [EmailService:Resend] Exception: {str(e)}")
            return {"error": str(e), "driver": "resend"}

    @classmethod
    def send_email(
        cls,
        to: Union[str, List[str]],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> dict:
        """
        Intelligent multi-provider email sender.
        1. If SMTP_USER and SMTP_PASSWORD are set (e.g. Gmail): uses Gmail SMTP (no domain required!).
        2. Else if RESEND_API_KEY is configured: uses Resend REST API.
        3. Else: simulates email in development mode with clear console logging.
        """
        recipients = [to] if isinstance(to, str) else to

        # 1. Prefer Brevo REST API if configured (300 free emails/day to ANY address)
        if settings.BREVO_API_KEY.strip():
            return cls.send_via_brevo(recipients, subject, html_content, text_content)

        # 2. Prefer SMTP if configured (e.g. Gmail or Brevo SMTP: smtp-relay.brevo.com:587)
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            return cls.send_via_smtp(recipients, subject, html_content, text_content)

        # 3. Resend API
        if settings.RESEND_API_KEY.strip():
            return cls.send_via_resend(recipients, subject, html_content, text_content)

        # 4. Development simulation fallback
        logger.warning(
            f"⚠️ [EmailService:Simulated] No live email provider configured (BREVO_API_KEY, SMTP, or RESEND_API_KEY). "
            f"Simulating email dispatch to: {recipients} | Subject: '{subject}'"
        )
        return {
            "id": "simulated_dev_id",
            "status": "simulated",
            "to": recipients,
            "subject": subject
        }

    @classmethod
    def send_verification_code_email(cls, to_email: str, name: str, code: str, base_url: str = "") -> dict:
        origin = base_url or settings.FRONTEND_URL or "https://project-kwdc.vercel.app"
        verify_url = f"{origin}/verify-email?code={code}&email={to_email}"

        subject = f"Your KTM-WDC Verification Code: {code}"
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
                .code-box {{ background: #fff7ed; border: 2px dashed #f97316; border-radius: 14px; padding: 20px 32px; font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #c2410c; text-align: center; margin: 24px 0; }}
                .btn {{ display: inline-block; background: #f97316; color: #ffffff !important; font-weight: 600; padding: 12px 28px; border-radius: 10px; text-decoration: none; margin: 16px 0; }}
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
                    <p>Thank you for registering on the KTM-WDC platform. Please enter the following 6-digit verification code to activate your account and access your commercial logistics cockpit:</p>
                    
                    <div class="code-box">
                        {code}
                    </div>
                    
                    <p style="text-align: center; font-size: 13px; color: #64748b; margin-top: 8px;">
                        This verification code is valid for 15 minutes.
                    </p>
                    
                    <div style="text-align: center; margin-top: 24px;">
                        <a href="{verify_url}" class="btn" target="_blank">Verify in One Click</a>
                    </div>
                </div>
                <div class="footer">
                    Kathmandu Warehousing & Distribution Center &bull; Kathmandu, Nepal<br>
                    &copy; 2026 KTM-WDC Commercial Logistics
                </div>
            </div>
        </body>
        </html>
        """
        text = f"Welcome to KTM-WDC, {name}!\n\nYour 6-digit verification code is: {code}\n\nVerify online: {verify_url}\n\nValid for 15 minutes."
        return cls.send_email(to_email, subject, html, text)

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
                    &copy; 2026 KTM-WDC Commercial Logistics
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
                    &copy; 2026 KTM-WDC Commercial Logistics
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
