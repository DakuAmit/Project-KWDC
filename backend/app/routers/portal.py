from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.user import User
from app.models.warehouse import Warehouse, WarehouseRequest
from app.models.logistics import DispatchOrder, DriverRate
from app.models.finance import Invoice, MarginTier
from app.models.equipment import Equipment, EquipmentJob
from app.models.security_agency import SecurityAgency, SecurityAssignment, SecurityIncident, SecurityPersonnel

router = APIRouter(tags=["Portal"])
from app.core.templates import templates

@router.get("/api/dashboard/stats")
@router.post("/api/dashboard/stats")
@router.get("/api/portal/cockpit-stats")
@router.post("/api/portal/cockpit-stats")
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
        monthly_cashflow = sum(float(w.area_sqft or 0) * float(w.price_per_sqft or 0) for w in warehouses)
        
        # Real pending space inquiries for properties owned by this user
        wh_ids = [w.id for w in warehouses]
        pending_reqs = 0
        if wh_ids:
            pending_reqs = db.query(WarehouseRequest).filter(
                WarehouseRequest.warehouse_id.in_(wh_ids),
                WarehouseRequest.status == "pending"
            ).count()
        
        response_data["stats"] = {
            "total_properties": len(warehouses),
            "total_capacity_sqft": total_capacity,
            "monthly_cashflow": monthly_cashflow,
            "pending_requests": pending_reqs,
            "warehouses": [
                {
                    "id": w.id,
                    "name": w.name,
                    "location": w.location,
                    "area_sqft": float(w.area_sqft or 0),
                    "price_per_sqft": float(w.price_per_sqft or 0),
                    "cold_storage": bool(w.cold_storage),
                    "temperature_min": float(w.temperature_min or 0) if w.temperature_min is not None else None,
                    "status": w.status
                } for w in warehouses
            ]
        }

    elif role == "driver":
        jobs = db.query(DispatchOrder).filter(
            (DispatchOrder.driver_id == user.id)
        ).order_by(DispatchOrder.id.desc()).limit(15).all()
        
        rates = db.query(DriverRate).filter(DriverRate.user_id == user.id).all()
        settled_payouts = sum(float(j.base_price or 0) for j in jobs if j.status == "completed")
        pending_fares = sum(float(j.base_price or 0) for j in jobs if j.status in ("assigned", "in_transit"))

        response_data["stats"] = {
            "settled_payouts": settled_payouts,
            "pending_fares": pending_fares,
            "total_trips": len([j for j in jobs if j.status == "completed"]),
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
        equipment = db.query(Equipment).filter(
            (Equipment.user_id == user.id) | (Equipment.owner_id == user.id)
        ).all()
        if not equipment and user.is_admin:
            equipment = db.query(Equipment).all()
            
        eq_ids = [eq.id for eq in equipment]
        jobs = []
        if eq_ids:
            jobs = db.query(EquipmentJob).filter(EquipmentJob.equipment_id.in_(eq_ids)).all()

        monthly_revenue = sum(float(job.agreed_rate or 0) for job in jobs if job.status == "completed")

        response_data["stats"] = {
            "total_machinery": len(equipment),
            "active_leases": len([j for j in jobs if j.status == "active"]),
            "monthly_revenue": monthly_revenue,
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
        agency = db.query(SecurityAgency).filter(SecurityAgency.user_id == user.id).first()
        assignments = []
        incidents = []
        guards_count = 0
        resolved_count = 0
        
        if agency:
            assignments = db.query(SecurityAssignment).filter(SecurityAssignment.agency_id == agency.id).all()
            incidents = db.query(SecurityIncident).filter(SecurityIncident.agency_id == agency.id).order_by(SecurityIncident.id.desc()).limit(5).all()
            guards_count = db.query(SecurityPersonnel).filter(SecurityPersonnel.agency_id == agency.id, SecurityPersonnel.status == "on_duty").count()
            resolved_count = db.query(SecurityIncident).filter(SecurityIncident.agency_id == agency.id, SecurityIncident.status == "resolved").count()
        elif user.is_admin:
            assignments = db.query(SecurityAssignment).limit(10).all()
            incidents = db.query(SecurityIncident).order_by(SecurityIncident.id.desc()).limit(5).all()
            guards_count = db.query(SecurityPersonnel).filter(SecurityPersonnel.status == "on_duty").count()
            resolved_count = db.query(SecurityIncident).filter(SecurityIncident.status == "resolved").count()

        response_data["stats"] = {
            "active_posts": len(assignments),
            "guards_on_duty": guards_count,
            "incidents_resolved": resolved_count,
            "assignments": [
                {
                    "id": asgn.id,
                    "warehouse_name": asgn.warehouse.name if asgn.warehouse else "Commercial Post",
                    "shift_type": getattr(asgn, "shift_type", "Standard Shift"),
                    "status": getattr(asgn, "status", "Assigned")
                } for asgn in assignments
            ],
            "incidents": [
                {
                    "id": inc.id,
                    "title": getattr(inc, "title", "Incident Report"),
                    "severity": getattr(inc, "severity", "Routine"),
                    "status": getattr(inc, "status", "Logged")
                } for inc in incidents
            ]
        }

    else:  # client
        dispatches = db.query(DispatchOrder).filter(DispatchOrder.client_id == user.id).order_by(DispatchOrder.id.desc()).limit(15).all()
        invoices = db.query(Invoice).filter(
            (Invoice.client_id == user.id) | (Invoice.user_id == user.id)
        ).order_by(Invoice.id.desc()).limit(15).all()
        unpaid_invoices = sum(
            float(inv.grand_total or inv.amount or inv.total_amount or 0)
            for inv in invoices
            if (inv.payment_status != "paid" and inv.status != "paid")
        )
        
        # Real approved storage space for this client (Multi-tenant capacity partitioning)
        storage_reqs = db.query(WarehouseRequest).filter(
            WarehouseRequest.client_id == user.id,
            WarehouseRequest.status == "approved"
        ).all()
        storage_sqft = sum(float(r.space_required or 0) for r in storage_reqs)

        assigned_warehouses = []
        for r in storage_reqs:
            w = r.warehouse
            if w:
                temp_range = None
                if w.cold_storage:
                    t_min = f"{w.temperature_min}°C" if w.temperature_min is not None else "-20°C"
                    t_max = f"{w.temperature_max}°C" if w.temperature_max is not None else "4°C"
                    temp_range = f"{t_min} to {t_max}"

                assigned_warehouses.append({
                    "request_id": r.id,
                    "warehouse_id": w.id,
                    "name": w.name,
                    "location": w.location,
                    "address": getattr(w, "address", w.location) or w.location,
                    "leased_sqft": float(r.space_required or 0),
                    "agreed_monthly_rent": float(r.agreed_price or (float(w.price_per_sqft or 0) * float(r.space_required or 0))),
                    "storage_type": getattr(w, "storage_type", "Closed Covered Godown") or "Closed Covered Godown",
                    "cold_storage": bool(w.cold_storage),
                    "temperature_range": temp_range,
                    "has_cctv": bool(getattr(w, "has_cctv", True)),
                    "cctv_count": getattr(w, "cctv_cameras_count", 16) or 16,
                    "security_guards": getattr(w, "security_guards_count", 4) or 4,
                    "loading_docks": getattr(w, "loading_docks_count", 2) or 2,
                    "container_road": getattr(w, "container_road_type", "Paved 4-Lane Access") or "Paved 4-Lane Access",
                    "nearby_police": getattr(w, "nearby_police_station", "Metropolitan Police Post") or "Metropolitan Police Post",
                    "nearby_hospital": getattr(w, "nearby_hospital", "Regional Emergency Hospital") or "Regional Emergency Hospital",
                    "nearby_fire": getattr(w, "nearby_fire_brigade", "Municipal Fire Station (Damkal)") or "Municipal Fire Station (Damkal)"
                })

        response_data["stats"] = {
            "has_assigned_warehouse": len(assigned_warehouses) > 0,
            "assigned_warehouses": assigned_warehouses,
            "active_dispatches": len([d for d in dispatches if d.status in ("pending", "assigned", "picked_up", "on_the_way", "in_transit")]),
            "storage_sqft": storage_sqft,
            "unpaid_invoices_amount": unpaid_invoices,
            "dispatches": [
                {
                    "id": d.id,
                    "tracking_id": d.tracking_id,
                    "warehouse_id": d.warehouse_id,
                    "pickup_address": d.pickup_address,
                    "delivery_address": (d.stops[0].address if d.stops and len(d.stops) > 0 else getattr(d, "delivery_address", "Kathmandu Hub")),
                    "total_distance": float(d.total_distance or 0),
                    "grand_total": float(d.grand_total or 0),
                    "status": d.status,
                    "created_at": d.created_at.strftime('%Y-%m-%d') if d.created_at else None
                } for d in dispatches
            ],
            "invoices": [
                {
                    "id": inv.id,
                    "invoice_number": inv.invoice_number,
                    "order_type": "Freight Dispatch" if inv.order_type == "dispatch" else (inv.order_type.title() if inv.order_type else "Commercial Service"),
                    "subtotal": float(inv.subtotal or round(float(inv.grand_total or inv.amount or 0) / 1.13, 2)),
                    "tax_amount": float(inv.tax_amount or round(float(inv.grand_total or inv.amount or 0) - float(inv.subtotal or (float(inv.grand_total or inv.amount or 0) / 1.13)), 2)),
                    "grand_total": float(inv.grand_total or inv.amount or 0),
                    "payment_status": inv.payment_status or inv.status or "unpaid",
                    "payment_method": inv.payment_method,
                    "created_at": inv.created_at.strftime('%Y-%m-%d') if inv.created_at else None
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
