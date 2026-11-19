from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.core.templates import templates
from app.models.warehouse import Warehouse, WarehouseRequest
from app.models.finance import Invoice
from app.models.user import User

router = APIRouter(prefix="/property-owner", tags=["Property Owner"])
api_router = APIRouter(prefix="/api/property-owner", tags=["Property Owner API"])

class RequestStatusPayload(BaseModel):
    status: str
    admin_notes: Optional[str] = None

@router.get("/dashboard", response_class=HTMLResponse)
def property_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    warehouses = db.query(Warehouse).filter(Warehouse.user_id == user.id).all()
    if not warehouses and (user.is_admin or user.role == "admin"):
        warehouses = db.query(Warehouse).all()

    wh_ids = [w.id for w in warehouses]
    all_requests = db.query(WarehouseRequest).filter(WarehouseRequest.warehouse_id.in_(wh_ids)).all() if wh_ids else []
    pending_count = len([r for r in all_requests if r.status == "pending"])
    approved_requests = [r for r in all_requests if r.status == "approved"]
    monthly_cashflow = sum(float(r.agreed_price or 0) for r in approved_requests)
    total_capacity = sum(float(w.area_sqft or 0) for w in warehouses)
    total_leased = sum(float(r.space_required or 0) for r in approved_requests)

    return templates.TemplateResponse(
        request=request,
        name="dashboards/property.html",
        context={
            "user": user,
            "warehouses": warehouses,
            "requests": all_requests,
            "pending_count": pending_count,
            "monthly_cashflow": monthly_cashflow,
            "total_capacity": total_capacity,
            "total_leased": total_leased
        }
    )

@api_router.get("/overview")
@router.get("/api/overview")
def get_property_overview(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # If admin previewing or real property owner
    query = db.query(Warehouse)
    if not (user.is_admin or user.role == "admin"):
        query = query.filter(Warehouse.user_id == user.id)
    warehouses = query.order_by(Warehouse.id.desc()).all()

    wh_ids = [w.id for w in warehouses]

    # Fetch all space requests for these warehouses
    requests_query = db.query(WarehouseRequest).filter(WarehouseRequest.warehouse_id.in_(wh_ids)) if wh_ids else []
    all_requests = requests_query.order_by(WarehouseRequest.id.desc()).all() if wh_ids else []

    total_capacity = sum(float(w.area_sqft or 0) for w in warehouses)
    
    # Calculate leased sqft from approved requests
    approved_requests = [r for r in all_requests if r.status == "approved"]
    total_leased = sum(float(r.space_required or 0) for r in approved_requests)
    total_available = max(0.0, total_capacity - total_leased)
    occupancy_pct = round((total_leased / total_capacity * 100), 1) if total_capacity > 0 else 0.0

    # Monthly cashflow from approved leases
    monthly_cashflow = sum(float(r.agreed_price or 0) for r in approved_requests)

    # Detailed warehouse list with multi-tenant stats
    wh_data = []
    for w in warehouses:
        w_approved = [r for r in w.requests if r.status == "approved"]
        w_leased = sum(float(r.space_required or 0) for r in w_approved)
        w_total = float(w.area_sqft or 0)
        w_avail = max(0.0, w_total - w_leased)
        w_occ = round((w_leased / w_total * 100), 1) if w_total > 0 else 0.0

        wh_data.append({
            "id": w.id,
            "name": w.name,
            "location": w.location,
            "address": w.address,
            "area_sqft": w_total,
            "leased_sqft": w_leased,
            "available_sqft": w_avail,
            "occupancy_pct": w_occ,
            "active_tenants_count": len(w_approved),
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
            "latitude": float(w.latitude) if w.latitude is not None else 27.6982,
            "longitude": float(w.longitude) if w.longitude is not None else 85.3015,
            "status": w.status
        })

    # Detailed requests list
    req_data = []
    for r in all_requests:
        client = db.query(User).filter(User.id == r.client_id).first()
        wh = next((w for w in warehouses if w.id == r.warehouse_id), None)
        req_data.append({
            "id": r.id,
            "warehouse_id": r.warehouse_id,
            "warehouse_name": wh.name if wh else "Unknown Facility",
            "client_id": r.client_id,
            "client_name": client.name if client else "Enterprise Client",
            "client_company": client.user_type if (client and client.user_type) else None,
            "client_email": client.email if client else None,
            "client_phone": client.phone if client else None,
            "space_required": float(r.space_required or 0),
            "purpose": r.purpose or "Commercial goods storage",
            "agreed_price": float(r.agreed_price or 0),
            "status": r.status,
            "admin_notes": r.admin_notes,
            "created_at": r.created_at.isoformat() if r.created_at else None
        })

    # Active Tenants breakdown (1:M multi-tenancy)
    tenants = []
    for r in approved_requests:
        client = db.query(User).filter(User.id == r.client_id).first()
        wh = next((w for w in warehouses if w.id == r.warehouse_id), None)
        tenants.append({
            "request_id": r.id,
            "client_id": r.client_id,
            "client_name": client.name if client else "Tenant",
            "client_company": client.user_type if (client and client.user_type) else None,
            "warehouse_id": r.warehouse_id,
            "warehouse_name": wh.name if wh else "Storage Godown",
            "space_leased_sqft": float(r.space_required or 0),
            "monthly_rent": float(r.agreed_price or 0),
            "leased_since": r.created_at.strftime("%Y-%m-%d") if r.created_at else "Active"
        })

    return {
        "summary": {
            "total_properties": len(warehouses),
            "total_capacity_sqft": total_capacity,
            "total_leased_sqft": total_leased,
            "total_available_sqft": total_available,
            "overall_occupancy_pct": occupancy_pct,
            "monthly_cashflow": monthly_cashflow,
            "pending_requests_count": len([r for r in all_requests if r.status == "pending"]),
            "active_tenants_count": len(approved_requests)
        },
        "warehouses": wh_data,
        "requests": req_data,
        "tenants": tenants
    }

@api_router.patch("/requests/{request_id}")
@router.patch("/api/requests/{request_id}")
def update_space_request(request_id: int, payload: RequestStatusPayload, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    wh_req = db.query(WarehouseRequest).filter(WarehouseRequest.id == request_id).first()
    if not wh_req:
        raise HTTPException(status_code=404, detail="Space reservation request not found")

    # Verify authorization: current user must own the warehouse (or be admin)
    wh = db.query(Warehouse).filter(Warehouse.id == wh_req.warehouse_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Associated warehouse not found")

    if not (user.is_admin or user.role == "admin" or wh.user_id == user.id):
        raise HTTPException(status_code=403, detail="Unauthorized to manage requests for this facility")

    status_val = payload.status.lower()
    if status_val not in ["approved", "rejected", "pending"]:
        raise HTTPException(status_code=400, detail="Status must be approved, rejected, or pending")

    wh_req.status = status_val
    if payload.admin_notes:
        wh_req.admin_notes = payload.admin_notes.strip()

    # Update associated invoice status
    inv = db.query(Invoice).filter(Invoice.warehouse_request_id == wh_req.id).first()
    if inv:
        if status_val == "approved":
            inv.status = "approved"
        elif status_val == "rejected":
            inv.status = "cancelled"
            inv.payment_status = "cancelled"

    db.commit()
    db.refresh(wh_req)

    return {
        "status": "success",
        "message": f"Space request #{wh_req.id} set to {status_val}",
        "request": {
            "id": wh_req.id,
            "status": wh_req.status,
            "space_required": float(wh_req.space_required or 0),
            "admin_notes": wh_req.admin_notes
        }
    }
