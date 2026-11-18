from fastapi import APIRouter, Depends, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.finance import Invoice
from app.services.invoice_service import InvoiceService

router = APIRouter(prefix="/invoices", tags=["Tax Invoices"])
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
