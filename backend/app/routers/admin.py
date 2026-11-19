from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Request, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.user import User
from app.models.warehouse import Warehouse, WarehouseRequest
from app.models.logistics import DispatchOrder, DeliveryStop, Vehicle, DriverRate
from app.models.finance import Invoice, Transaction, MarginTier, PartnerEarning
from app.models.inventory import Stock, Box
from app.models.equipment import Equipment, EquipmentJob
from app.models.security_agency import SecurityAgency, SecurityPersonnel, SecurityAssignment, SecurityIncident
from app.core.templates import templates

router = APIRouter(prefix="/admin", tags=["Administration"])
api_router = APIRouter(prefix="/api/admin", tags=["Admin API"])

# Dependency to guard all admin API routes
def require_admin_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not user.is_admin and user.role != "admin":
        raise HTTPException(status_code=403, detail="SuperAdmin authorization required")
    return user

# Pydantic Request Models
class UserStatusPayload(BaseModel):
    is_active: bool

class UserVerifyPayload(BaseModel):
    is_verified: bool

class WarehouseStatusPayload(BaseModel):
    status: str

class DispatchStatusPayload(BaseModel):
    status: str

class DispatchAssignPayload(BaseModel):
    driver_id: int

class IncidentStatusPayload(BaseModel):
    status: str

class MarginTierPayload(BaseModel):
    name: str
    min_distance: float
    max_distance: Optional[float] = None
    margin_value: float
    service_type: str = "dispatch"
    margin_type: str = "percentage"
    is_active: bool = True


# =========================================================================
# DRAWER 1: OVERVIEW & SYSTEM HEALTH
# =========================================================================

@api_router.get("/overview")
def get_admin_overview(current_user: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    users_count = db.query(func.count(User.id)).scalar() or 0
    wh_count = db.query(func.count(Warehouse.id)).scalar() or 0
    dispatch_count = db.query(func.count(DispatchOrder.id)).scalar() or 0
    equip_count = db.query(func.count(Equipment.id)).scalar() or 0
    sec_count = db.query(func.count(SecurityAgency.id)).scalar() or 0
    stock_count = db.query(func.count(Stock.id)).scalar() or 0
    box_count = db.query(func.count(Box.id)).scalar() or 0

    # Role breakdown
    roles_raw = db.query(User.role, func.count(User.id)).group_by(User.role).all()
    roles_breakdown = {r[0] or "client": r[1] for r in roles_raw}

    # Dispatch breakdown
    disp_raw = db.query(DispatchOrder.status, func.count(DispatchOrder.id)).group_by(DispatchOrder.status).all()
    disp_breakdown = {d[0] or "pending": d[1] for d in disp_raw}

    # Financials
    total_tax = float(db.query(func.sum(Invoice.tax_amount)).scalar() or 0.0)
    total_billed = float(db.query(func.sum(Invoice.grand_total)).scalar() or 0.0)
    total_settled = float(db.query(func.sum(Invoice.grand_total)).filter(Invoice.payment_status == "paid").scalar() or 0.0)
    unpaid_count = db.query(func.count(Invoice.id)).filter(Invoice.payment_status != "paid").scalar() or 0

    return {
        "status": "healthy",
        "server_time": datetime.utcnow().isoformat(),
        "counts": {
            "users": users_count,
            "warehouses": wh_count,
            "dispatches": dispatch_count,
            "equipment": equip_count,
            "security_agencies": sec_count,
            "stocks": stock_count,
            "boxes": box_count,
        },
        "roles": roles_breakdown,
        "dispatch_status": disp_breakdown,
        "financials": {
            "total_tax_collected": total_tax,
            "total_billed": total_billed,
            "total_settled": total_settled,
            "unpaid_invoices_count": unpaid_count
        }
    }


# =========================================================================
# DRAWER 2: ECOSYSTEM ENTITIES & USERS (KYC / RBAC)
# =========================================================================

@api_router.get("/users")
def get_admin_users(
    role: Optional[str] = Query(None),
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    query = db.query(User)
    if role and role.lower() != "all":
        query = query.filter(User.role == role.lower())
    users = query.order_by(User.id.desc()).all()

    return [
        {
            "id": u.id,
            "user_code": u.user_code or f"USR-{u.id:04d}",
            "name": u.name,
            "email": u.email,
            "phone": u.phone or "—",
            "role": u.role or "client",
            "is_active": bool(u.is_active),
            "is_verified": bool(u.email_verified_at is not None),
            "address": u.address or "—",
            "created_at": u.created_at.isoformat() if u.created_at else None
        } for u in users
    ]

@api_router.post("/users/{user_id}/status")
def toggle_user_status(
    user_id: int,
    payload: UserStatusPayload,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change self status")

    target.is_active = payload.is_active
    db.commit()
    return {"status": "success", "user_id": target.id, "is_active": target.is_active}

@api_router.post("/users/{user_id}/verify")
def toggle_user_verification(
    user_id: int,
    payload: UserVerifyPayload,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.email_verified_at = datetime.utcnow() if payload.is_verified else None
    db.commit()
    return {"status": "success", "user_id": target.id, "is_verified": bool(target.email_verified_at)}


# =========================================================================
# DRAWER 3: COMMERCIAL WAREHOUSING REGISTRY
# =========================================================================

@api_router.get("/warehouses")
def get_admin_warehouses(current_user: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    warehouses = db.query(Warehouse).order_by(Warehouse.id.desc()).all()
    return [
        {
            "id": w.id,
            "name": w.name,
            "location": w.location,
            "address": w.address or w.location,
            "area_sqft": float(w.area_sqft or 0),
            "price_per_sqft": float(w.price_per_sqft or 0),
            "cold_storage": bool(w.cold_storage),
            "temperature_min": float(w.temperature_min) if w.temperature_min is not None else None,
            "temperature_max": float(w.temperature_max) if w.temperature_max is not None else None,
            "kataho_code": w.kataho_code or "—",
            "cctv_count": w.cctv_count or 0,
            "guards_count": w.guards_count or 0,
            "status": w.status or "pending",
            "owner_name": w.owner.name if w.owner else "System",
            "owner_email": w.owner.email if w.owner else "—",
            "created_at": w.created_at.isoformat() if w.created_at else None
        } for w in warehouses
    ]

@api_router.post("/warehouses/{warehouse_id}/status")
def update_warehouse_status(
    warehouse_id: int,
    payload: WarehouseStatusPayload,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    wh.status = payload.status.lower()
    if wh.status == "approved":
        wh.approved_at = datetime.utcnow()
    db.commit()
    return {"status": "success", "warehouse_id": wh.id, "status": wh.status}


# =========================================================================
# DRAWER 4: FREIGHT OPERATIONS & DISPATCHES
# =========================================================================

@api_router.get("/dispatches")
def get_admin_dispatches(current_user: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    dispatches = db.query(DispatchOrder).order_by(DispatchOrder.id.desc()).all()
    return [
        {
            "id": d.id,
            "tracking_id": d.tracking_id or f"TRK-{d.id:05d}",
            "client_name": d.client.name if d.client else "Direct Shipper",
            "client_phone": d.client.phone if d.client else "—",
            "driver_name": d.driver.name if d.driver else "Unassigned",
            "driver_phone": d.driver.phone if d.driver else "—",
            "pickup_address": d.pickup_address,
            "total_distance": float(d.total_distance or 0),
            "base_price": float(d.base_price or 0),
            "admin_margin": float(d.admin_margin or 0),
            "tax_amount": float(d.tax_amount or 0),
            "grand_total": float(d.grand_total or 0),
            "payment_status": d.payment_status or "pending",
            "status": d.status or "pending",
            "current_latitude": float(d.current_latitude) if d.current_latitude else None,
            "current_longitude": float(d.current_longitude) if d.current_longitude else None,
            "created_at": d.created_at.isoformat() if d.created_at else None
        } for d in dispatches
    ]

@api_router.post("/dispatches/{dispatch_id}/status")
def update_dispatch_status(
    dispatch_id: int,
    payload: DispatchStatusPayload,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    d = db.query(DispatchOrder).filter(DispatchOrder.id == dispatch_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispatch order not found")

    d.status = payload.status.lower()
    if d.status == "delivered":
        d.delivered_at = datetime.utcnow()
    elif d.status == "cancelled":
        d.cancelled_at = datetime.utcnow()
    db.commit()
    return {"status": "success", "dispatch_id": d.id, "status": d.status}

@api_router.post("/dispatches/{dispatch_id}/assign")
def assign_dispatch_driver(
    dispatch_id: int,
    payload: DispatchAssignPayload,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    d = db.query(DispatchOrder).filter(DispatchOrder.id == dispatch_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispatch order not found")

    driver = db.query(User).filter(User.id == payload.driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    d.driver_id = driver.id
    d.status = "assigned"
    d.assigned_at = datetime.utcnow()
    db.commit()
    return {"status": "success", "dispatch_id": d.id, "driver_name": driver.name, "status": d.status}


# =========================================================================
# DRAWER 5: REAL-TIME TELEMETRY & FLEET TRACKING
# =========================================================================

@api_router.get("/telemetry")
def get_admin_telemetry(current_user: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    active_dispatches = db.query(DispatchOrder).filter(
        DispatchOrder.status.in_(["assigned", "picked_up", "on_the_way"])
    ).all()

    # If no active, return recent with coordinates
    if not active_dispatches:
        active_dispatches = db.query(DispatchOrder).filter(
            DispatchOrder.current_latitude != None
        ).limit(20).all()

    return [
        {
            "id": d.id,
            "tracking_id": d.tracking_id,
            "driver_name": d.driver.name if d.driver else "En Route",
            "driver_phone": d.driver.phone if d.driver else "",
            "pickup_address": d.pickup_address,
            "current_latitude": float(d.current_latitude or 27.7172),  # Default Kathmandu valley center
            "current_longitude": float(d.current_longitude or 85.3240),
            "status": d.status,
            "last_update": d.last_location_update.isoformat() if d.last_location_update else None
        } for d in active_dispatches
    ]


# =========================================================================
# DRAWER 6: QR INVENTORY & STOCK BATCHES
# =========================================================================

@api_router.get("/inventory")
def get_admin_inventory(current_user: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    stocks = db.query(Stock).order_by(Stock.id.desc()).all()
    boxes_count = db.query(func.count(Box.id)).scalar() or 0

    return {
        "total_boxes": boxes_count,
        "stocks": [
            {
                "id": s.id,
                "product_name": s.product_name,
                "sku": s.sku,
                "batch_id": s.batch_id,
                "client_name": s.client_name,
                "warehouse_name": s.warehouse_name or "KTM Facility",
                "total_quantity": s.total_quantity or 0,
                "remaining_quantity": s.remaining_quantity or 0,
                "expiry_date": s.expiry_date.isoformat() if s.expiry_date else None,
                "status": s.status or "in_stock"
            } for s in stocks
        ]
    }


# =========================================================================
# DRAWER 7: HEAVY EQUIPMENT & MACHINERY
# =========================================================================

@api_router.get("/equipment")
def get_admin_equipment(current_user: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    equipments = db.query(Equipment).order_by(Equipment.id.desc()).all()
    jobs = db.query(EquipmentJob).order_by(EquipmentJob.id.desc()).all()

    return {
        "equipment": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.type,
                "model": e.model or "—",
                "daily_rate": float(e.daily_rate or 0),
                "security_deposit": float(e.security_deposit or 0),
                "location": e.location or "Kathmandu",
                "status": e.status or "available",
                "owner_name": e.owner.name if e.owner else "Independent Fleet"
            } for e in equipments
        ],
        "jobs": [
            {
                "id": j.id,
                "equipment_name": j.equipment.name if j.equipment else "Machinery",
                "price": float(j.price or 0),
                "start_date": j.start_date.isoformat() if j.start_date else None,
                "end_date": j.end_date.isoformat() if j.end_date else None,
                "status": j.status or "pending"
            } for j in jobs
        ]
    }


# =========================================================================
# DRAWER 8: SECURITY AGENCIES & GUARDS
# =========================================================================

@api_router.get("/security")
def get_admin_security(current_user: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    agencies = db.query(SecurityAgency).order_by(SecurityAgency.id.desc()).all()
    incidents = db.query(SecurityIncident).order_by(SecurityIncident.id.desc()).all()
    guards_count = db.query(func.count(SecurityPersonnel.id)).scalar() or 0

    return {
        "total_guards": guards_count,
        "agencies": [
            {
                "id": a.id,
                "agency_name": a.agency_name,
                "license_number": a.license_number or "—",
                "pan_vat_number": a.pan_vat_number or "—",
                "phone": a.phone or "—",
                "status": a.status or "approved",
                "is_verified": bool(a.is_verified)
            } for a in agencies
        ],
        "incidents": [
            {
                "id": inc.id,
                "agency_name": inc.agency.agency_name if inc.agency else "Security Command",
                "incident_type": inc.incident_type or "Routine",
                "severity": inc.severity or "Medium",
                "description": inc.description,
                "status": inc.status or "reported",
                "police_station": inc.police_station_notified or "—"
            } for inc in incidents
        ]
    }

@api_router.post("/security/incidents/{incident_id}/status")
def update_incident_status(
    incident_id: int,
    payload: IncidentStatusPayload,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    inc = db.query(SecurityIncident).filter(SecurityIncident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    inc.status = payload.status.lower()
    db.commit()
    return {"status": "success", "incident_id": inc.id, "status": inc.status}


# =========================================================================
# DRAWER 9: FINANCIALS & 13% IRD VAT INVOICES
# =========================================================================

@api_router.get("/invoices")
def get_admin_invoices(current_user: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    invoices = db.query(Invoice).order_by(Invoice.id.desc()).all()

    total_billed = sum(float(i.grand_total or i.amount or 0) for i in invoices)
    total_tax = sum(float(i.tax_amount or 0) for i in invoices)
    total_settled = sum(float(i.grand_total or i.amount or 0) for i in invoices if (i.payment_status or "").lower() == "paid")
    total_unpaid = total_billed - total_settled

    return {
        "summary": {
            "total_billed": round(total_billed, 2),
            "total_tax_13_vat": round(total_tax, 2),
            "total_settled": round(total_settled, 2),
            "total_unpaid": round(total_unpaid, 2)
        },
        "invoices": [
            {
                "id": i.id,
                "invoice_number": i.invoice_number,
                "order_type": i.order_type or "Commercial Service",
                "client_name": i.user.name if i.user else "Registered Client",
                "subtotal": float(i.subtotal or 0),
                "tax_rate": float(i.tax_rate or 13.0),
                "tax_amount": float(i.tax_amount or 0),
                "grand_total": float(i.grand_total or i.amount or 0),
                "payment_status": i.payment_status or "unpaid",
                "payment_method": i.payment_method or "—",
                "paid_at": i.paid_at.isoformat() if i.paid_at else None,
                "created_at": i.created_at.isoformat() if i.created_at else None
            } for i in invoices
        ]
    }


# =========================================================================
# DRAWER 10: PLATFORM MARGINS & SETTINGS
# =========================================================================

@api_router.get("/settings")
def get_admin_settings(current_user: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    margin_tiers = db.query(MarginTier).filter(MarginTier.is_active == True).order_by(MarginTier.min_distance.asc()).all()

    return {
        "vat_rate": 13.0,
        "currency": "NPR",
        "margin_tiers": [
            {
                "id": m.id,
                "name": m.name,
                "min_distance": float(m.min_distance or 0),
                "max_distance": float(m.max_distance) if m.max_distance is not None else None,
                "service_type": m.service_type,
                "margin_value": float(m.margin_value or 0),
                "margin_type": m.margin_type,
                "is_active": bool(m.is_active)
            } for m in margin_tiers
        ],
        "vehicle_tariffs": [
            {"vehicle": "Pickup (1 Ton)", "base_price_per_km": 45.0, "minimum_base_fare": 500.0},
            {"vehicle": "Mini Truck (2.5 Ton)", "base_price_per_km": 75.0, "minimum_base_fare": 900.0},
            {"vehicle": "Medium Haul (5 Ton)", "base_price_per_km": 120.0, "minimum_base_fare": 1800.0},
            {"vehicle": "Heavy Container (10+ Ton)", "base_price_per_km": 190.0, "minimum_base_fare": 3500.0}
        ]
    }

@api_router.post("/settings/margin-tiers")
def create_margin_tier(
    payload: MarginTierPayload,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    tier = MarginTier(
        name=payload.name.strip(),
        min_distance=payload.min_distance,
        max_distance=payload.max_distance,
        service_type=payload.service_type,
        margin_type=payload.margin_type,
        margin_value=payload.margin_value,
        is_active=payload.is_active
    )
    db.add(tier)
    db.commit()
    db.refresh(tier)
    return {"status": "success", "tier_id": tier.id, "name": tier.name}

@api_router.delete("/settings/margin-tiers/{tier_id}")
def delete_margin_tier(
    tier_id: int,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db)
):
    tier = db.query(MarginTier).filter(MarginTier.id == tier_id).first()
    if not tier:
        raise HTTPException(status_code=404, detail="Margin tier not found")

    tier.is_active = False
    db.commit()
    return {"status": "success", "message": f"Tier {tier_id} deactivated"}


# =========================================================================
# LEGACY SSR REDIRECT / TEMPLATE ROUTER (for backward compatibility)
# =========================================================================

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    return RedirectResponse(url="/dashboard.html?role=admin", status_code=status.HTTP_302_FOUND)
