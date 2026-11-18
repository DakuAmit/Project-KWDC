import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.finance import Invoice, Transaction
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payment", tags=["Payment Suite"])
from app.core.templates import templates

@router.get("", response_class=HTMLResponse)
@router.get("/history", response_class=HTMLResponse)
def history(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    transactions = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    invoices = db.query(Invoice).filter(Invoice.client_id == user.id).all()

    return templates.TemplateResponse(
        request=request,
        name="invoices/index.html",
        context={"user": user, "invoices": invoices, "transactions": transactions}
    )

@router.post("/esewa/init")
def esewa_init(invoice_id: int = Form(...), db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    pay_data = PaymentService.initiate_esewa_payment(
        amount=float(inv.grand_total),
        invoice_number=inv.invoice_number
    )
    return RedirectResponse(
        url=f"/payment/success?method=esewa&invoice_id={inv.id}&amount={inv.grand_total}",
        status_code=303
    )

@router.post("/khalti/init")
async def khalti_init(invoice_id: int = Form(...), db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return RedirectResponse(
        url=f"/payment/success?method=khalti&invoice_id={inv.id}&amount={inv.grand_total}",
        status_code=303
    )

@router.get("/success")
def payment_success(
    invoice_id: int,
    method: str = "esewa",
    db: Session = Depends(get_db)
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if inv:
        inv.payment_status = "paid"
        inv.payment_method = method
        inv.paid_at = datetime.utcnow()

        txn = Transaction(
            invoice_id=inv.id,
            user_id=inv.user_id or 1,
            amount=inv.grand_total,
            tax=inv.tax_amount,
            payment_method=method,
            transaction_id=f"TXN-{uuid.uuid4().hex[:10].upper()}",
            receipt_no=f"RCP-{uuid.uuid4().hex[:8].upper()}",
            status="completed",
            payment_date=datetime.utcnow()
        )
        db.add(txn)
        db.commit()

    return RedirectResponse(url=f"/invoices/{invoice_id}?paid=1", status_code=302)
