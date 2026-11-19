from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.logistics import DispatchOrder, DispatchLocationHistory, Vehicle, DriverRate

router = APIRouter(tags=["Commercial Driver"])
from app.core.templates import templates

class DriverTelemetryPayload(BaseModel):
    order_id: Optional[int] = None
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    speed: Optional[float] = None

class DriverOrderStatusPayload(BaseModel):
    status: str
    admin_notes: Optional[str] = None

class DriverPODPayload(BaseModel):
    recipient_name: Optional[str] = None
    delivery_notes: Optional[str] = None
    pod_reference: Optional[str] = None

@router.get("/driver/dashboard", response_class=HTMLResponse)
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

@router.get("/driver/rates", response_class=HTMLResponse)
def driver_rates(request: Request, db: Session = Depends(get_db)):
    return RedirectResponse(url="/driver/dashboard")

# =========================================================================
# COMMERCIAL DRIVER REST API (Live Telemetry, Trip Acceptance, Digital POD)
# =========================================================================

@router.get("/api/driver/overview")
def get_driver_overview(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Driver vehicle
    vehicle = db.query(Vehicle).filter(
        (Vehicle.driver_id == user.id) | (Vehicle.user_id == user.id)
    ).first()

    # Active & Assigned jobs
    assigned_jobs = db.query(DispatchOrder).filter(
        DispatchOrder.driver_id == user.id
    ).order_by(DispatchOrder.id.desc()).all()

    # Available unassigned freight shipments for pickup
    available_jobs = db.query(DispatchOrder).filter(
        DispatchOrder.status == "pending",
        DispatchOrder.driver_id == None
    ).order_by(DispatchOrder.id.desc()).limit(10).all()

    settled_payouts = sum(float(j.driver_earning or j.base_price or 0) for j in assigned_jobs if j.status == "delivered")
    pending_fares = sum(float(j.driver_earning or j.base_price or 0) for j in assigned_jobs if j.status in ("assigned", "picked_up", "on_the_way"))

    return {
        "status": "success",
        "driver": {
            "id": user.id,
            "name": user.name,
            "phone": user.phone,
            "user_code": user.user_code,
            "is_verified": getattr(user, "is_verified", True)
        },
        "vehicle": {
            "vehicle_number": vehicle.vehicle_number if vehicle else "BA 2 KHA 8912",
            "vehicle_type": vehicle.vehicle_type if vehicle else "Tata 1.5-Ton Commercial Truck",
            "capacity": float(vehicle.capacity or 1.5) if vehicle else 1.5,
            "is_verified": vehicle.is_verified if vehicle else True
        } if vehicle else None,
        "settled_payouts": settled_payouts,
        "pending_fares": pending_fares,
        "total_deliveries": len([j for j in assigned_jobs if j.status == "delivered"]),
        "assigned_jobs": [
            {
                "id": j.id,
                "tracking_id": j.tracking_id,
                "pickup_address": j.pickup_address,
                "delivery_address": (j.stops[0].address if j.stops and len(j.stops) > 0 else getattr(j, "delivery_address", "Kathmandu Hub")),
                "total_distance": float(j.total_distance or 0),
                "driver_share": float(j.driver_earning or j.base_price or 0),
                "status": j.status,
                "created_at": j.created_at.isoformat() if j.created_at else None
            } for j in assigned_jobs
        ],
        "available_jobs": [
            {
                "id": j.id,
                "tracking_id": j.tracking_id,
                "pickup_address": j.pickup_address,
                "delivery_address": (j.stops[0].address if j.stops and len(j.stops) > 0 else getattr(j, "delivery_address", "Kathmandu Hub")),
                "total_distance": float(j.total_distance or 0),
                "driver_share": float(j.driver_earning or j.base_price or 0),
                "status": j.status
            } for j in available_jobs
        ]
    }

@router.post("/api/driver/telemetry")
def submit_driver_telemetry(payload: DriverTelemetryPayload, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    now = datetime.utcnow()
    # Find active order if not explicitly passed
    order = None
    if payload.order_id:
        order = db.query(DispatchOrder).filter(DispatchOrder.id == payload.order_id).first()
    else:
        order = db.query(DispatchOrder).filter(
            DispatchOrder.driver_id == user.id,
            DispatchOrder.status.in_(["assigned", "picked_up", "on_the_way"])
        ).order_by(DispatchOrder.id.desc()).first()

    if order:
        order.current_latitude = payload.latitude
        order.current_longitude = payload.longitude
        order.last_location_update = now

        # Add to telemetry history breadcrumb
        history = DispatchLocationHistory(
            dispatch_id=order.id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            accuracy=payload.accuracy or 10.0,
            recorded_at=now
        )
        db.add(history)
        db.commit()

    return {
        "status": "success",
        "message": "GPS telemetry broadcast received and stored in database",
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "recorded_at": now.isoformat(),
        "active_order_tracking_id": order.tracking_id if order else None
    }

@router.patch("/api/driver/orders/{order_id}/status")
def update_driver_order_status(order_id: int, payload: DriverOrderStatusPayload, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    order = db.query(DispatchOrder).filter(DispatchOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Dispatch order not found")

    valid_statuses = ["assigned", "picked_up", "on_the_way", "delivered", "cancelled"]
    target_status = payload.status.lower()
    if target_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status '{payload.status}'. Must be one of {valid_statuses}")

    now = datetime.utcnow()
    # If unassigned order being accepted
    if target_status == "assigned" and (order.driver_id is None or order.driver_id == user.id):
        order.driver_id = user.id
        order.assigned_at = now

    if target_status == "picked_up":
        order.picked_up_at = now
    elif target_status == "on_the_way":
        order.on_the_way_at = now
    elif target_status == "delivered":
        order.delivered_at = now
        order.payment_status = "payable"

    order.status = target_status
    if payload.admin_notes:
        order.admin_notes = payload.admin_notes

    db.commit()

    return {
        "status": "success",
        "message": f"Order #{order.tracking_id} status updated to '{target_status}'",
        "order": {
            "id": order.id,
            "tracking_id": order.tracking_id,
            "status": order.status,
            "driver_id": order.driver_id,
            "payment_status": order.payment_status
        }
    }

@router.post("/api/driver/orders/{order_id}/pod")
def submit_digital_pod(order_id: int, payload: DriverPODPayload, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    order = db.query(DispatchOrder).filter(DispatchOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Dispatch order not found")

    now = datetime.utcnow()
    order.status = "delivered"
    order.delivered_at = now
    order.payment_status = "payable"
    order.admin_notes = f"POD Received by: {payload.recipient_name or 'Consignee'}. Note: {payload.delivery_notes or 'Goods inspected and verified in sound condition.'}"

    db.commit()

    return {
        "status": "success",
        "message": f"Proof of Delivery verified for #{order.tracking_id}. Driver payout marked payable.",
        "tracking_id": order.tracking_id,
        "delivered_at": now.isoformat()
    }
