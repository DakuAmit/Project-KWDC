from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.logistics import DispatchOrder

router = APIRouter(prefix="/driver", tags=["Driver Portal"])
from app.core.templates import templates

@router.get("/dashboard", response_class=HTMLResponse)
def driver_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    jobs = db.query(DispatchOrder).filter(
        (DispatchOrder.driver_id == user.id) | (DispatchOrder.status == "pending")
    ).order_by(DispatchOrder.id.desc()).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboards/driver.html",
        context={"user": user, "jobs": jobs}
    )

@router.get("/rates", response_class=HTMLResponse)
def driver_rates(request: Request, db: Session = Depends(get_db)):
    return RedirectResponse(url="/driver/dashboard")
