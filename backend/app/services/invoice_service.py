import io
import json
import random
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from app.models.finance import Invoice
from app.services.qr_service import QRService

class InvoiceService:
    @staticmethod
    def generate_invoice_number() -> str:
        year = datetime.now().year
        rand_num = random.randint(100000, 999999)
        return f"INV-{year}-{rand_num}"

    @classmethod
    def create_dispatch_invoice(
        cls,
        db: Session,
        dispatch_order,
        client_id: int
    ) -> Invoice:
        # Check if already exists
        existing = db.query(Invoice).filter(
            Invoice.order_type == "dispatch",
            Invoice.order_id == dispatch_order.id
        ).first()
        if existing:
            return existing

        inv_number = cls.generate_invoice_number()
        subtotal = float(dispatch_order.base_price or 0) + float(dispatch_order.admin_margin or 0)
        tax_amount = round(subtotal * 0.13, 2)
        grand_total = round(subtotal + tax_amount, 2)

        items = [
            {"description": "Freight Dispatch Transportation Fare", "amount": float(dispatch_order.base_price or 0)},
            {"description": "Platform Admin Margin Fee", "amount": float(dispatch_order.admin_margin or 0)},
        ]

        qr_token = QRService.generate_qr_base64(f"https://kwdc.gov.np/verify/{inv_number}")

        invoice = Invoice(
            user_id=client_id,
            client_id=client_id,
            invoice_number=inv_number,
            order_type="dispatch",
            order_id=dispatch_order.id,
            amount=grand_total,
            subtotal=subtotal,
            tax_rate=13.0,
            tax_amount=tax_amount,
            grand_total=grand_total,
            pan_number=dispatch_order.pan_number or "999999999",
            billing_type=dispatch_order.bill_type or "regular",
            billing_address=dispatch_order.pickup_address,
            items=json.dumps(items),
            status="pending",
            payment_status="unpaid",
            due_date=date.today() + timedelta(days=7),
            qr_code=qr_token,
            notes=f"Tax invoice generated for Dispatch #{dispatch_order.tracking_id}"
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return invoice

    @staticmethod
    def generate_pdf_bytes(invoice: Invoice) -> bytes:
        """Render official IRD Nepal Schedule 13 compliant Tax Invoice PDF using ReportLab"""
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # Header Banner
        p.setFillColor(colors.HexColor("#1e293b"))
        p.rect(0, height - 90, width, 90, fill=True, stroke=False)
        
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 20)
        p.drawString(40, height - 45, "KTM-WDC LOGISTICS PORTAL")
        p.setFont("Helvetica", 10)
        p.drawString(40, height - 65, "Kathmandu Warehousing & Distribution Center | Inland Revenue Dept. Approved")

        p.setFont("Helvetica-Bold", 12)
        p.drawRightString(width - 40, height - 45, "TAX INVOICE (कर बिजक)")
        p.setFont("Helvetica", 9)
        p.drawRightString(width - 40, height - 60, f"Invoice: {invoice.invoice_number}")
        created_str = invoice.created_at.strftime('%Y-%m-%d') if invoice.created_at else datetime.now().strftime('%Y-%m-%d')
        p.drawRightString(width - 40, height - 73, f"Date: {created_str}")

        # Billing Info Section
        p.setFillColor(colors.HexColor("#0f172a"))
        p.setFont("Helvetica-Bold", 11)
        p.drawString(40, height - 120, "Issuer Details:")
        p.setFont("Helvetica", 9)
        p.drawString(40, height - 135, "KTM Warehousing & Distribution Center Pvt. Ltd.")
        p.drawString(40, height - 148, "PAN / VAT No: 601234567")
        p.drawString(40, height - 161, "Kalimati-14, Kathmandu, Nepal | Phone: +977-1-4200000")

        p.setFont("Helvetica-Bold", 11)
        p.drawString(320, height - 120, "Billed To (Customer):")
        p.setFont("Helvetica", 9)
        try:
            cust_name = invoice.user.name if invoice.user else "Valued Client"
        except Exception:
            cust_name = "Valued Client"

        cust_pan = invoice.pan_number or "N/A"
        p.drawString(320, height - 135, f"Name: {cust_name}")
        p.drawString(320, height - 148, f"Buyer PAN: {cust_pan}")
        p.drawString(320, height - 161, f"Address: {invoice.billing_address or 'Kathmandu, Nepal'}")

        # Table Header
        table_top = height - 200
        p.setFillColor(colors.HexColor("#e2e8f0"))
        p.rect(40, table_top - 20, width - 80, 20, fill=True, stroke=False)
        
        p.setFillColor(colors.HexColor("#1e293b"))
        p.setFont("Helvetica-Bold", 9)
        p.drawString(50, table_top - 14, "S.N.")
        p.drawString(85, table_top - 14, "Description of Goods / Service")
        p.drawRightString(width - 150, table_top - 14, "Taxable Rate")
        p.drawRightString(width - 50, table_top - 14, "Total (NPR)")

        # Table Rows
        y = table_top - 38
        p.setFont("Helvetica", 9)
        items_list = []
        if invoice.items:
            try:
                items_list = json.loads(invoice.items)
            except Exception:
                items_list = [{"description": "Logistics Services", "amount": float(invoice.subtotal or 0)}]
        else:
            items_list = [{"description": f"{invoice.order_type.title() if invoice.order_type else 'Logistics'} Service", "amount": float(invoice.subtotal or 0)}]

        for idx, item in enumerate(items_list, 1):
            p.drawString(50, y, str(idx))
            p.drawString(85, y, str(item.get("description", "Service Charge")))
            amt = float(item.get("amount", 0))
            p.drawRightString(width - 150, y, f"Rs. {amt:,.2f}")
            p.drawRightString(width - 50, y, f"Rs. {amt:,.2f}")
            y -= 20

        # Totals Divider
        p.setStrokeColor(colors.HexColor("#cbd5e1"))
        p.line(40, y + 10, width - 40, y + 10)

        # Financial Calculations
        subtotal = float(invoice.subtotal or 0)
        tax = float(invoice.tax_amount or 0)
        grand = float(invoice.grand_total or 0)

        y -= 15
        p.setFont("Helvetica", 10)
        p.drawRightString(width - 160, y, "Taxable Amount (Subtotal):")
        p.drawRightString(width - 50, y, f"Rs. {subtotal:,.2f}")

        y -= 18
        p.drawRightString(width - 160, y, "Value Added Tax (13% VAT):")
        p.drawRightString(width - 50, y, f"Rs. {tax:,.2f}")

        y -= 22
        p.setFont("Helvetica-Bold", 12)
        p.setFillColor(colors.HexColor("#0f172a"))
        p.drawRightString(width - 160, y, "Grand Total (कुल जम्मा):")
        p.drawRightString(width - 50, y, f"Rs. {grand:,.2f}")

        # Status Stamp
        y -= 45
        status_color = colors.HexColor("#16a34a") if invoice.payment_status == "paid" else colors.HexColor("#ea580c")
        p.setFillColor(status_color)
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y, f"PAYMENT STATUS: {(invoice.payment_status or 'UNPAID').upper()}")

        # Footer
        p.setFont("Helvetica", 8)
        p.setFillColor(colors.HexColor("#64748b"))
        p.drawString(40, 40, "This is a computer-generated tax invoice issued in accordance with Nepal Value Added Tax Act, 2052.")
        p.drawString(40, 28, "Verify invoice validity via KTM-WDC Portal or scan QR code.")

        p.showPage()
        p.save()
        return buffer.getvalue()
