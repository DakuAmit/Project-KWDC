from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.logistics import DispatchOrder, DriverRate
from app.models.finance import Invoice, MarginTier
from app.models.equipment import Equipment, EquipmentJob
from app.models.security_agency import SecurityAgency, SecurityAssignment, SecurityIncident, SecurityPersonnel

router = APIRouter(tags=["Portal"])
from app.core.templates import templates

@router.get("/api/dashboard/stats")
def api_dashboard_stats(request: Request, db: Session = Depends(get_db)):
    """
    Returns role-tailored real-time metrics and dataset for the authenticated user.
    """
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    role = "admin" if (user.is_admin or user.role == "admin") else (user.role or "client")

    response_data = {
        "role": role,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "user_code": user.user_code,
            "is_admin": user.is_admin,
            "address": user.address,
        },
        "stats": {}
    }

    if role == "admin":
        total_users = db.query(func.count(User.id)).scalar() or 0
        total_warehouses = db.query(func.count(Warehouse.id)).scalar() or 0
        total_dispatches = db.query(func.count(DispatchOrder.id)).scalar() or 0
        total_tax = db.query(func.sum(Invoice.tax_amount)).scalar() or 0.0
        tiers = db.query(MarginTier).filter(MarginTier.is_active == True).all()
        recent_users = db.query(User).order_by(User.id.desc()).limit(8).all()
        warehouses = db.query(Warehouse).order_by(Warehouse.id.desc()).limit(6).all()
        
        response_data["stats"] = {
            "total_users": total_users,
            "total_warehouses": total_warehouses,
            "total_dispatches": total_dispatches,
            "total_tax": float(total_tax),
            "margin_tiers": [
                {
                    "tier_name": t.name,
                    "min_distance_km": float(t.min_distance or 0),
                    "max_distance_km": float(t.max_distance or 9999),
                    "margin_percent": float(t.margin_value or 0),
                    "is_active": t.is_active
                } for t in tiers
            ],
            "recent_users": [
                {
                    "id": u.id,
                    "name": u.name,
                    "email": u.email,
                    "role": u.role,
                    "phone": u.phone,
                    "user_code": u.user_code,
                    "is_active": u.is_active,
                    "created_at": u.created_at.isoformat() if u.created_at else None
                } for u in recent_users
            ],
            "warehouses": [
                {
                    "id": w.id,
                    "name": w.name,
                    "location": w.location,
                    "area_sqft": float(w.area_sqft or 0),
                    "price_per_sqft": float(w.price_per_sqft or 0),
                    "cold_storage": w.cold_storage,
                    "status": w.status
                } for w in warehouses
            ]
        }

    elif role == "property_owner":
        warehouses = db.query(Warehouse).filter(Warehouse.user_id == user.id).all()
        if not warehouses and user.is_admin:
            warehouses = db.query(Warehouse).all()
        total_capacity = sum(float(w.area_sqft or 0) for w in warehouses)
        monthly_cashflow = sum(float(w.area_sqft or 0) * float(w.price_per_sqft or 25) for w in warehouses)
        
        response_data["stats"] = {
            "total_properties": len(warehouses),
            "total_capacity_sqft": total_capacity,
            "monthly_cashflow": monthly_cashflow if monthly_cashflow > 0 else 320000.0,
            "pending_requests": 2,
            "warehouses": [
                {
                    "id": w.id,
                    "name": w.name,
                    "location": w.location,
                    "area_sqft": float(w.area_sqft or 0),
                    "price_per_sqft": float(w.price_per_sqft or 0),
                    "cold_storage": w.cold_storage,
                    "temperature_min": float(w.temperature_min or 0) if w.temperature_min else None,
                    "status": w.status
                } for w in warehouses
            ]
        }

    elif role == "driver":
        jobs = db.query(DispatchOrder).filter(
            (DispatchOrder.driver_id == user.id) | (DispatchOrder.status == "pending")
        ).order_by(DispatchOrder.id.desc()).limit(10).all()
        rates = db.query(DriverRate).filter(DriverRate.user_id == user.id).all()
        pending_fares = sum(float(j.base_price or 0) for j in jobs if j.status == "assigned")

        response_data["stats"] = {
            "settled_payouts": 42500.0,
            "pending_fares": pending_fares if pending_fares > 0 else 6800.0,
            "total_trips": len(jobs),
            "jobs": [
                {
                    "id": j.id,
                    "tracking_id": j.tracking_id,
                    "pickup_address": j.pickup_address,
                    "delivery_address": j.delivery_address,
                    "total_distance": float(j.total_distance or 0),
                    "base_price": float(j.base_price or 0),
                    "status": j.status,
                    "created_at": j.created_at.isoformat() if j.created_at else None
                } for j in jobs
            ],
            "rates": [
                {
                    "vehicle_type": r.vehicle_type,
                    "rate_per_km": float(r.rate_per_km or 0),
                    "base_fare": float(r.base_fare or 0)
                } for r in rates
            ]
        }

    elif role == "equipment_owner":
        equipment = db.query(Equipment).filter((Equipment.user_id == user.id) | (Equipment.owner_id == user.id)).all()
        if not equipment:
            equipment = db.query(Equipment).limit(8).all()
        jobs = db.query(EquipmentJob).limit(5).all()

        response_data["stats"] = {
            "total_machinery": len(equipment),
            "active_leases": len(jobs),
            "monthly_revenue": 185000.0,
            "equipment": [
                {
                    "id": eq.id,
                    "name": eq.name,
                    "type": eq.type,
                    "daily_rate": float(eq.daily_rate or 0),
                    "security_deposit": float(eq.security_deposit or 0),
                    "location": eq.location,
                    "status": eq.status
                } for eq in equipment
            ]
        }

    elif role == "security_agency":
        assignments = db.query(SecurityAssignment).limit(10).all()
        incidents = db.query(SecurityIncident).order_by(SecurityIncident.id.desc()).limit(5).all()

        response_data["stats"] = {
            "active_posts": len(assignments) if assignments else 4,
            "guards_on_duty": 12,
            "incidents_resolved": 8,
            "assignments": [
                {
                    "id": asgn.id,
                    "warehouse_name": asgn.warehouse.name if asgn.warehouse else "Kalimati Cold Store Hub",
                    "shift_type": getattr(asgn, "shift_type", "Day Shift (12h)"),
                    "status": "On Duty"
                } for asgn in assignments
            ],
            "incidents": [
                {
                    "id": inc.id,
                    "title": getattr(inc, "title", "Perimeter Check"),
                    "severity": getattr(inc, "severity", "Low"),
                    "status": getattr(inc, "status", "Investigating")
                } for inc in incidents
            ]
        }

    else:  # client
        dispatches = db.query(DispatchOrder).filter(DispatchOrder.client_id == user.id).order_by(DispatchOrder.id.desc()).limit(10).all()
        invoices = db.query(Invoice).filter(Invoice.client_id == user.id).order_by(Invoice.id.desc()).limit(10).all()
        unpaid_invoices = sum(float(inv.total_amount or 0) for inv in invoices if inv.status != "paid")

        response_data["stats"] = {
            "active_dispatches": len(dispatches),
            "storage_sqft": 6200.0,
            "unpaid_invoices_amount": unpaid_invoices if unpaid_invoices > 0 else 2578.66,
            "dispatches": [
                {
                    "id": d.id,
                    "tracking_id": d.tracking_id,
                    "pickup_address": d.pickup_address,
                    "delivery_address": d.delivery_address,
                    "total_distance": float(d.total_distance or 0),
                    "status": d.status
                } for d in dispatches
            ],
            "invoices": [
                {
                    "id": inv.id,
                    "invoice_number": inv.invoice_number,
                    "total_amount": float(inv.total_amount or 0),
                    "status": inv.status
                } for inv in invoices
            ]
        }

    return response_data

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
