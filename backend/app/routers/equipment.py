from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.equipment import Equipment, EquipmentJob

router = APIRouter(tags=["Heavy Equipment"])
from app.core.templates import templates

@router.get("/equipment-owner/dashboard", response_class=HTMLResponse)
def equipment_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    equipment = db.query(Equipment).all()
    jobs = db.query(EquipmentJob).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboards/equipment.html",
        context={"user": user, "equipment": equipment, "jobs": jobs}
    )

@router.get("/equipment", response_class=HTMLResponse)
def equipment_list(request: Request, db: Session = Depends(get_db)):
    return equipment_dashboard(request, db)
