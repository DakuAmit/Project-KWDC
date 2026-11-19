from fastapi import APIRouter, Depends, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.finance import Invoice
from app.services.invoice_service import InvoiceService

router = APIRouter(prefix="/invoices", tags=["Tax Invoices"])
api_router = APIRouter(prefix="/api/invoices", tags=["Invoices API"])
from app.core.templates import templates

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    if user.is_admin:
        invoices = db.query(Invoice).order_by(Invoice.id.desc()).all()
    else:
        invoices = db.query(Invoice).filter(Invoice.client_id == user.id).order_by(Invoice.id.desc()).all()

    return templates.TemplateResponse(
        request=request,
        name="invoices/index.html",
        context={"user": user, "invoices": invoices}
    )

@router.get("/{invoice_id}", response_class=HTMLResponse)
def show(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return templates.TemplateResponse(
        request=request,
        name="invoices/detail.html",
        context={"user": user, "invoice": inv}
    )

@api_router.get("/{invoice_id}/download")
@router.get("/{invoice_id}/download")
def download_pdf(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    pdf_bytes = InvoiceService.generate_pdf_bytes(inv)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={inv.invoice_number}.pdf"}
    )

import secrets
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models.finance import Transaction

class PayInvoicePayload(BaseModel):
    payment_method: str = "esewa"
    reference_id: Optional[str] = None

@api_router.get("")
@api_router.get("/")
@router.get("/api/invoices")
def get_api_invoices(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if user.is_admin or user.role == "admin":
        invoices = db.query(Invoice).order_by(Invoice.id.desc()).all()
    else:
        invoices = db.query(Invoice).filter(
            (Invoice.user_id == user.id) | (Invoice.client_id == user.id)
        ).order_by(Invoice.id.desc()).all()

    return [
        {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "order_type": inv.order_type or "Commercial Service",
            "subtotal": float(inv.subtotal or 0),
            "tax_rate": float(inv.tax_rate or 13.0),
            "tax_amount": float(inv.tax_amount or 0),
            "grand_total": float(inv.grand_total or inv.amount or 0),
            "payment_status": inv.payment_status or "unpaid",
            "payment_method": inv.payment_method,
            "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
            "description": inv.description,
            "created_at": inv.created_at.isoformat() if inv.created_at else None
        } for inv in invoices
    ]

@api_router.post("/{invoice_id}/pay")
@router.post("/api/invoices/{invoice_id}/pay")
def pay_api_invoice(invoice_id: int, payload: PayInvoicePayload, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not user.is_admin and inv.user_id != user.id and inv.client_id != user.id:
        raise HTTPException(status_code=403, detail="Unauthorized to settle this invoice")

    now = datetime.utcnow()
    inv.payment_status = "paid"
    inv.status = "paid"
    inv.payment_method = payload.payment_method.lower()
    inv.paid_at = now

    tx = Transaction(
        invoice_id=inv.id,
        user_id=user.id,
        amount=inv.grand_total or inv.amount or 0.0,
        tax=inv.tax_amount or 0.0,
        payment_method=payload.payment_method.lower(),
        transaction_id=payload.reference_id or f"TXN-{secrets.randbelow(899999)+100000}",
        status="completed",
        payment_date=now
    )
    db.add(tx)
    db.commit()

    return {
        "status": "success",
        "message": f"Invoice {inv.invoice_number} settled successfully via {payload.payment_method.upper()}",
        "invoice": {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "payment_status": "paid",
            "payment_method": inv.payment_method,
            "paid_at": now.isoformat()
        }
    }
