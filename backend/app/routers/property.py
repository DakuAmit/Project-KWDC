from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.warehouse import Warehouse

router = APIRouter(prefix="/property-owner", tags=["Property Owner"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/dashboard", response_class=HTMLResponse)
def property_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    warehouses = db.query(Warehouse).filter(Warehouse.user_id == user.id).all()
    if not warehouses and user.is_admin:
        warehouses = db.query(Warehouse).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboards/property.html",
        context={"user": user, "warehouses": warehouses}
    )
