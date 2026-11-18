from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.warehouse import Warehouse, WarehouseRequest

router = APIRouter(prefix="/warehouses", tags=["Warehouses"])
from app.core.templates import templates

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    warehouses = db.query(Warehouse).filter(Warehouse.status == "approved").all()
    if not warehouses:
        warehouses = db.query(Warehouse).all()
    return templates.TemplateResponse(
        request=request,
        name="warehouses/index.html",
        context={"user": user, "warehouses": warehouses}
    )

@router.get("/create", response_class=HTMLResponse)
def create_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        request=request,
        name="warehouses/index.html",
        context={"user": user, "warehouses": []}
    )

@router.get("/{warehouse_id}", response_class=HTMLResponse)
def detail(warehouse_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return templates.TemplateResponse(
        request=request,
        name="warehouses/detail.html",
        context={"user": user, "warehouse": wh}
    )

@router.post("/{warehouse_id}/request")
def request_space(
    warehouse_id: int,
    request: Request,
    space_required: float = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    purpose: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    try:
        s_date = datetime.strptime(start_date, "%Y-%m-%d")
        e_date = datetime.strptime(end_date, "%Y-%m-%d")
    except Exception:
        s_date = datetime.now()
        e_date = datetime.now()

    agreed = space_required * float(wh.price_per_sqft or 50.0)

    req_obj = WarehouseRequest(
        client_id=user.id,
        warehouse_id=wh.id,
        start_date=s_date,
        end_date=e_date,
        space_required=space_required,
        purpose=purpose,
        agreed_price=agreed,
        status="pending"
    )
    db.add(req_obj)
    db.commit()
    return RedirectResponse(url=f"/warehouses/{warehouse_id}?success=1", status_code=302)
