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
import secrets
from typing import Optional
from pydantic import BaseModel
from app.models.finance import Invoice

class WarehouseCreatePayload(BaseModel):
    name: str
    location: str
    address: Optional[str] = None
    area_sqft: float
    price_per_sqft: float
    description: Optional[str] = None
    kataho_code: Optional[str] = None
    facilities: Optional[str] = None  # Storage classification: Closed Godown, Open Yard Free Space, etc.
    cold_storage: bool = False
    temperature_min: Optional[float] = None
    temperature_max: Optional[float] = None
    humidity_control: bool = False
    cctv_count: int = 0
    guards_count: int = 0
    fire_extinguishers: int = 0
    loading_dock: bool = False
    parking_spaces: int = 0
    parking_type: Optional[str] = "open"
    nearby_police: Optional[str] = None
    nearby_fire: Optional[str] = None
    nearby_hospital: Optional[str] = None
    nearby_bank: Optional[str] = None
    nearby_fuel: Optional[str] = None
    nearby_market: Optional[str] = None

class WarehouseReservePayload(BaseModel):
    space_required: float
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    purpose: Optional[str] = None

api_router = APIRouter(prefix="/api/warehouses", tags=["Warehouses API"])

@api_router.get("")
@api_router.get("/")
@router.get("/api/warehouses")
def get_api_warehouses(db: Session = Depends(get_db)):
    warehouses = db.query(Warehouse).order_by(Warehouse.id.desc()).all()
    results = []
    for w in warehouses:
        total_sqft = float(w.area_sqft or 0)
        approved_reqs = [r for r in w.requests if r.status == "approved"]
        leased_sqft = sum(float(r.space_required or 0) for r in approved_reqs)
        available_sqft = max(0.0, total_sqft - leased_sqft)
        occupancy_pct = round((leased_sqft / total_sqft * 100), 1) if total_sqft > 0 else 0.0

        results.append({
            "id": w.id,
            "name": w.name,
            "location": w.location,
            "address": w.address,
            "area_sqft": total_sqft,
            "leased_sqft": leased_sqft,
            "available_sqft": available_sqft,
            "occupancy_pct": occupancy_pct,
            "active_tenants_count": len(approved_reqs),
            "pending_requests_count": len([r for r in w.requests if r.status == "pending"]),
            "price_per_sqft": float(w.price_per_sqft or 0),
            "cold_storage": bool(w.cold_storage),
            "temperature_min": float(w.temperature_min or 0) if w.temperature_min is not None else None,
            "temperature_max": float(w.temperature_max or 0) if w.temperature_max is not None else None,
            "humidity_control": bool(w.humidity_control),
            "facilities": w.facilities or "Closed Covered Godown",
            "cctv_count": w.cctv_count or 0,
            "guards_count": w.guards_count or 0,
            "fire_extinguishers": w.fire_extinguishers or 0,
            "loading_dock": bool(w.loading_dock),
            "parking_spaces": w.parking_spaces or 0,
            "parking_type": w.parking_type or "open",
            "nearby_police": w.nearby_police,
            "nearby_fire": w.nearby_fire,
            "nearby_hospital": w.nearby_hospital,
            "nearby_bank": w.nearby_bank,
            "nearby_fuel": w.nearby_fuel,
            "nearby_market": w.nearby_market,
            "kataho_code": w.kataho_code,
            "description": w.description,
            "status": w.status,
            "user_id": w.user_id,
            "created_at": w.created_at.isoformat() if w.created_at else None
        })
    return results

@api_router.post("")
@api_router.post("/")
@router.post("/api/warehouses")
def create_api_warehouse(payload: WarehouseCreatePayload, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required to register facility")

    new_wh = Warehouse(
        user_id=user.id,
        name=payload.name.strip(),
        location=payload.location.strip(),
        address=payload.address.strip() if payload.address else payload.location.strip(),
        area_sqft=payload.area_sqft,
        price_per_sqft=payload.price_per_sqft,
        cold_storage=payload.cold_storage,
        temperature_min=payload.temperature_min if payload.cold_storage else None,
        temperature_max=payload.temperature_max if payload.cold_storage else None,
        humidity_control=payload.humidity_control,
        facilities=payload.facilities or "Closed Covered Godown",
        cctv_count=payload.cctv_count,
        guards_count=payload.guards_count,
        fire_extinguishers=payload.fire_extinguishers,
        loading_dock=payload.loading_dock,
        parking_spaces=payload.parking_spaces,
        parking_type=payload.parking_type or "open",
        nearby_police=payload.nearby_police,
        nearby_fire=payload.nearby_fire,
        nearby_hospital=payload.nearby_hospital,
        nearby_bank=payload.nearby_bank,
        nearby_fuel=payload.nearby_fuel,
        nearby_market=payload.nearby_market,
        description=payload.description,
        kataho_code=payload.kataho_code,
        status="approved"
    )
    db.add(new_wh)
    db.commit()
    db.refresh(new_wh)

    return {
        "status": "success",
        "message": "Commercial facility listed successfully",
        "warehouse": {
            "id": new_wh.id,
            "name": new_wh.name,
            "location": new_wh.location,
            "area_sqft": float(new_wh.area_sqft or 0),
            "price_per_sqft": float(new_wh.price_per_sqft or 0),
            "cold_storage": bool(new_wh.cold_storage),
            "facilities": new_wh.facilities,
            "status": new_wh.status
        }
    }

@api_router.post("/{warehouse_id}/reserve")
@router.post("/api/warehouses/{warehouse_id}/reserve")
def reserve_api_warehouse(warehouse_id: int, payload: WarehouseReservePayload, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required to reserve storage")

    wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    # Multi-tenant partitioning check
    total_sqft = float(wh.area_sqft or 0)
    approved_reqs = [r for r in wh.requests if r.status == "approved"]
    leased_sqft = sum(float(r.space_required or 0) for r in approved_reqs)
    available_sqft = max(0.0, total_sqft - leased_sqft)

    if payload.space_required > available_sqft:
        raise HTTPException(
            status_code=400,
            detail=f"Requested space ({payload.space_required:,.0f} sqft) exceeds available capacity ({available_sqft:,.0f} sqft) at {wh.name}."
        )

    subtotal = round(payload.space_required * float(wh.price_per_sqft or 35.0), 2)
    vat_13 = round(subtotal * 0.13, 2)
    grand_total = round(subtotal + vat_13, 2)

    # 1. Create space reservation (partition)
    wh_req = WarehouseRequest(
        client_id=user.id,
        warehouse_id=wh.id,
        space_required=payload.space_required,
        purpose=payload.purpose,
        agreed_price=subtotal,
        status="approved"
    )
    db.add(wh_req)
    db.flush()

    # 2. Issue official IRD Tax Invoice
    inv_num = f"INV-WH-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.randbelow(8999) + 1000}"
    invoice = Invoice(
        user_id=user.id,
        client_id=user.id,
        warehouse_request_id=wh_req.id,
        invoice_number=inv_num,
        order_type="Warehouse Lease",
        subtotal=subtotal,
        tax_rate=13.00,
        tax_amount=vat_13,
        grand_total=grand_total,
        amount=grand_total,
        status="pending",
        payment_status="unpaid",
        description=f"Storage space reservation ({payload.space_required:,.0f} sqft) at {wh.name}"
    )
    db.add(invoice)
    db.commit()

    return {
        "status": "success",
        "message": f"Successfully reserved {payload.space_required:,.0f} sqft at {wh.name}",
        "reservation_id": wh_req.id,
        "invoice": {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "subtotal": subtotal,
            "vat_amount": vat_13,
            "grand_total": grand_total,
            "payment_status": "unpaid"
        }
    }
