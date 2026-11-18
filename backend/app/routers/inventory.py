from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.inventory import Stock, Box
from app.services.qr_service import QRService

router = APIRouter(tags=["Inventory & QR Tracking"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/stock", response_class=HTMLResponse)
def list_stock(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    stocks = db.query(Stock).all()
    boxes = db.query(Box).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboards/client.html",
        context={"user": user, "stocks": stocks, "boxes": boxes, "dispatches": [], "invoices": []}
    )

@router.get("/boxes/{box_id}/qr")
def box_qr(box_id: int, db: Session = Depends(get_db)):
    box = db.query(Box).filter(Box.id == box_id).first()
    data = box.qr_code if box else f"KWDC-BOX-{box_id}"
    qr_bytes = QRService.generate_qr_bytes(data)
    return Response(content=qr_bytes, media_type="image/png")
