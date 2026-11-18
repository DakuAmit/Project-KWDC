import hmac
import hashlib
import base64
import json
import uuid
from typing import Dict, Any, Optional
import httpx
from app.core.config import settings

class PaymentService:
    @staticmethod
    def generate_esewa_signature(total_amount: float, transaction_uuid: str, product_code: str, secret_key: str) -> str:
        """eSewa EPWI v2 HMAC-SHA256 signature generator"""
        message = f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}"
        signature = hmac.new(
            secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode("utf-8")

    @classmethod
    def initiate_esewa_payment(cls, amount: float, invoice_number: str) -> Dict[str, Any]:
        transaction_uuid = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        product_code = settings.ESEWA_PRODUCT_CODE
        signature = cls.generate_esewa_signature(
            total_amount=amount,
            transaction_uuid=transaction_uuid,
            product_code=product_code,
            secret_key=settings.ESEWA_SECRET_KEY
        )
        return {
            "gateway": "esewa",
            "action_url": f"{settings.ESEWA_BASE_URL}/api/epay/main/v2/form",
            "fields": {
                "amount": str(amount),
                "tax_amount": "0",
                "total_amount": str(amount),
                "transaction_uuid": transaction_uuid,
                "product_code": product_code,
                "product_service_charge": "0",
                "product_delivery_charge": "0",
                "success_url": "/payment/esewa/success",
                "failure_url": "/payment/esewa/failure",
                "signed_field_names": "total_amount,transaction_uuid,product_code",
                "signature": signature
            }
        }

    @classmethod
    async def initiate_khalti_payment(cls, amount: float, invoice_number: str, user_name: str, user_email: str) -> Dict[str, Any]:
        if not settings.KHALTI_SECRET_KEY:
            # Sandbox / Simulation mode
            return {
                "success": True,
                "pidx": f"khalti_demo_{uuid.uuid4().hex[:8]}",
                "payment_url": f"/payment/success?method=khalti&invoice={invoice_number}&amount={amount}"
            }
        
        url = f"{settings.KHALTI_BASE_URL}/epayment/initiate/"
        headers = {
            "Authorization": f"Key {settings.KHALTI_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "return_url": "/payment/khalti/verify",
            "website_url": "https://kwdc.com.np",
            "amount": int(round(amount * 100)), # Paisa
            "purchase_order_id": invoice_number,
            "purchase_order_name": f"Invoice #{invoice_number}",
            "customer_info": {
                "name": user_name,
                "email": user_email,
                "phone": "9800000000"
            }
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                return {"success": True, "pidx": data.get("pidx"), "payment_url": data.get("payment_url")}
            return {"success": False, "message": "Failed to connect to Khalti Gateway"}
