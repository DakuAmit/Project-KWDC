from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.logistics import DispatchOrder
from app.models.finance import Invoice

router = APIRouter(tags=["Portal"])
from app.core.templates import templates

@router.get("/", response_class=HTMLResponse)
def index_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="welcome.html", context={"user": None})

@router.get("/ping", response_class=PlainTextResponse)
def ping():
    return "pong"

@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    # Dynamic role routing
    if user.role == "admin" or user.is_admin:
        return RedirectResponse(url="/admin")
    elif user.role == "driver" or user.is_driver:
        return RedirectResponse(url="/driver/dashboard")
    elif user.role == "property_owner" or user.is_property_owner:
        return RedirectResponse(url="/property-owner/dashboard")
    elif user.role == "equipment_owner" or user.is_equipment_owner:
        return RedirectResponse(url="/equipment-owner/dashboard")
    elif user.role == "security_agency":
        return RedirectResponse(url="/security/dashboard")
    else:
        return RedirectResponse(url="/client/dashboard")

@router.get("/client/dashboard", response_class=HTMLResponse)
def client_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    dispatches = db.query(DispatchOrder).filter(DispatchOrder.client_id == user.id).order_by(DispatchOrder.id.desc()).all()
    invoices = db.query(Invoice).filter(Invoice.client_id == user.id).order_by(Invoice.id.desc()).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboards/client.html",
        context={"user": user, "dispatches": dispatches, "invoices": invoices}
    )

@router.get("/privacy-policy", response_class=HTMLResponse)
def privacy_policy(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    return templates.TemplateResponse(request=request, name="legal/privacy.html", context={"user": user})

@router.get("/terms-of-service", response_class=HTMLResponse)
def terms_of_service(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    return templates.TemplateResponse(request=request, name="legal/terms.html", context={"user": user})
