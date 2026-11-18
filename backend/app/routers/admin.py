from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.logistics import DispatchOrder
from app.models.finance import Invoice, MarginTier

router = APIRouter(prefix="/admin", tags=["Administration"])
templates = Jinja2Templates(directory="app/templates")

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user or (user.role != "admin" and not user.is_admin):
        return RedirectResponse(url="/login")

    stats = {
        "total_users": db.query(func.count(User.id)).scalar() or 0,
        "total_warehouses": db.query(func.count(Warehouse.id)).scalar() or 0,
        "total_dispatches": db.query(func.count(DispatchOrder.id)).scalar() or 0,
        "total_tax": float(db.query(func.sum(Invoice.tax_amount)).scalar() or 0.0),
    }

    margin_tiers = db.query(MarginTier).filter(MarginTier.is_active == True).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboards/admin.html",
        context={"user": user, "stats": stats, "margin_tiers": margin_tiers}
    )

@router.get("/users", response_class=HTMLResponse)
def list_users(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user or (user.role != "admin" and not user.is_admin):
        return RedirectResponse(url="/login")

    users = db.query(User).order_by(User.id.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="dashboards/admin.html",
        context={"user": user, "stats": {}, "users": users}
    )
