from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.security_agency import SecurityAssignment, SecurityIncident

router = APIRouter(prefix="/security", tags=["Security Agency"])
from app.core.templates import templates

@router.get("/dashboard", response_class=HTMLResponse)
def security_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    assignments = db.query(SecurityAssignment).all()
    incidents = db.query(SecurityIncident).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboards/security.html",
        context={"user": user, "assignments": assignments, "incidents": incidents}
    )

@router.get("/incidents", response_class=HTMLResponse)
def security_incidents(request: Request, db: Session = Depends(get_db)):
    return security_dashboard(request, db)
