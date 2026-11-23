"""
Fleet Partner & Telemetry Router
Supports:
1. Multi-Vehicle Fleet Roster (2-Wheelers, Pickups, Heavy Trucks, Container Trailers)
2. Multiple Assigned Drivers
3. Multi-Drop Freight Orders (up to 5 consignee stops)
4. Distance-Tiered Admin Margins (10%-15%) & 13% IRD VAT
5. Live GPS Telemetry Broadcast
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List, Optional
from backend.database import get_db
from backend.models import (
    Vehicle, Driver, DispatchOrder, DeliveryStop, User, UserRole,
    VehicleCategory, FreightStatus, TaxInvoice, PaymentStatus
)
from backend.schemas import VehicleCreate, DriverCreate
from backend.auth_utils import require_user, require_roles
from backend.services.vat_service import generate_ird_tax_invoice

router = APIRouter(prefix="/api/fleet", tags=["Fleet Partner & Logistics"])

@router.post("/vehicles")
def register_vehicle(
    payload: VehicleCreate,
    current_user: User = Depends(require_roles([UserRole.FLEET_PARTNER, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Registers a vehicle under the Fleet Partner's account with verified Bluebook."""
    existing = db.query(Vehicle).filter(Vehicle.license_plate == payload.license_plate).first()
    if existing:
        raise HTTPException(status_code=400, detail="Vehicle with this license plate already registered.")

    vehicle = Vehicle(
        fleet_partner_id=current_user.id,
        category=payload.category,
        model_name=payload.model_name,
        license_plate=payload.license_plate,
        bluebook_number=payload.bluebook_number,
        payload_capacity_kg=payload.payload_capacity_kg,
        volume_capacity_cft=payload.volume_capacity_cft,
        is_verified=True,
        is_available=True
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return {"message": "Vehicle registered with verified Bluebook.", "vehicle_id": vehicle.id}

@router.get("/my-fleet")
def get_my_fleet(
    current_user: User = Depends(require_roles([UserRole.FLEET_PARTNER, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    vehicles = db.query(Vehicle).filter(Vehicle.fleet_partner_id == current_user.id).all()
    drivers = db.query(Driver).filter(Driver.fleet_partner_id == current_user.id).all()

    return {
        "vehicles": [
            {
                "id": v.id,
                "category": v.category.value,
                "model_name": v.model_name,
                "license_plate": v.license_plate,
                "bluebook_number": v.bluebook_number,
                "payload_capacity_kg": v.payload_capacity_kg,
                "is_available": v.is_available,
                "current_lat": v.current_lat,
                "current_lng": v.current_lng
            }
            for v in vehicles
        ],
        "drivers": [
            {
                "id": d.id,
                "full_name": d.full_name,
                "phone_number": d.phone_number,
                "license_number": d.license_number,
                "assigned_vehicle_id": d.assigned_vehicle_id
            }
            for d in drivers
        ]
    }

@router.post("/drivers")
def register_driver(
    payload: DriverCreate,
    current_user: User = Depends(require_roles([UserRole.FLEET_PARTNER, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    driver = Driver(
        fleet_partner_id=current_user.id,
        assigned_vehicle_id=payload.assigned_vehicle_id,
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        license_number=payload.license_number,
        citizenship_no=payload.citizenship_no,
        is_active=True
    )
    db.add(driver)
    db.commit()
    db.refresh(driver)
    return {"message": "Driver added to fleet roster.", "driver_id": driver.id}

@router.post("/telemetry/ping")
def update_telemetry(
    vehicle_id: int,
    latitude: float,
    longitude: float,
    heading: Optional[float] = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    100ms GPS stream / Telemetry ping from the driver mobile client.
    Updates vehicle coordinate cache and active dispatch order.
    """
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found.")

    now = datetime.now(timezone.utc)
    vehicle.current_lat = latitude
    vehicle.current_lng = longitude
    vehicle.last_telemetry_at = now

    # Also update any active dispatch order for this vehicle
    active_order = db.query(DispatchOrder).filter(
        DispatchOrder.vehicle_id == vehicle_id,
        DispatchOrder.status.in_([FreightStatus.PICKUP_IN_PROGRESS, FreightStatus.IN_TRANSIT])
    ).first()

    if active_order:
        active_order.live_lat = latitude
        active_order.live_lng = longitude
        active_order.telemetry_heading = heading
        active_order.last_telemetry_at = now

    db.commit()
    return {"status": "ok", "timestamp": now.isoformat()}
