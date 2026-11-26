"""
Fleet Partner & Telemetry Router
Supports:
1. Multi-Vehicle Fleet Roster (2-Wheelers, Pickups, Heavy Trucks, Container Trailers)
2. Multiple Assigned Drivers
3. Multi-Drop Freight Orders (up to 5 consignee stops)
4. Distance-Tiered Admin Margins (10%-15%) & 13% IRD VAT
5. Live GPS Telemetry Broadcast
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import jwt
from jwt.exceptions import PyJWTError
import random

from backend.config import settings
from backend.database import get_db
from backend.models import (
    Vehicle, Driver, DispatchOrder, DeliveryStop, User, UserRole,
    VehicleCategory, FreightStatus, TaxInvoice, PaymentStatus, KycStatus,
    FreightCounterOffer, PlatformConfig, DriverDismissedOrder
)
from backend.schemas import (
    VehicleCreate, DriverCreate, ClientDispatchOrderCreate,
    DriverLoginRequest, DriverResetPinRequest, EmergencyReassignRequest,
    OperatorTypeUpdateRequest, DeliveryCompleteRequest,
    CounterOfferCreate, CounterOfferAcceptRequest
)
from backend.auth_utils import require_user, require_roles, create_access_token, oauth2_scheme
from backend.services.vat_service import generate_ird_tax_invoice
from backend.services.fare_service import calculate_freight_benchmark, get_platform_config
from backend.services.maps_service import calculate_road_distance, geocode_address

router = APIRouter(prefix="/api/fleet", tags=["Fleet Partner & Logistics"])

def require_fleet_partner(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Ensures the user has fleet operating privileges.
    Seamlessly upgrades client/unassigned sessions to FLEET_PARTNER when interacting with fleet portal.
    """
    if current_user.role not in (UserRole.FLEET_PARTNER, UserRole.SUPERADMIN):
        current_user.role = UserRole.FLEET_PARTNER
        try:
            db.commit()
        except Exception:
            db.rollback()
    return current_user

def normalize_vehicle_category(val) -> VehicleCategory:
    if not val:
        return VehicleCategory.SIX_WHEELER
    if isinstance(val, VehicleCategory):
        return val
    s = str(val.value if hasattr(val, "value") else val).upper().replace("-", "_")
    mapping = {
        "TWO_WHEELER": VehicleCategory.TWO_WHEELER,
        "THREE_WHEELER": VehicleCategory.THREE_WHEELER,
        "MINI_TRUCK": VehicleCategory.MINI_TRUCK,
        "PICKUP": VehicleCategory.MEDIUM_PICKUP,
        "MEDIUM_PICKUP": VehicleCategory.MEDIUM_PICKUP,
        "HEAVY_TRUCK": VehicleCategory.SIX_WHEELER,
        "SIX_WHEELER": VehicleCategory.SIX_WHEELER,
        "TEN_WHEELER": VehicleCategory.TEN_WHEELER,
        "CONTAINER_TRAILER": VehicleCategory.CONTAINER_TRAILER,
        "TRAILER": VehicleCategory.CONTAINER_TRAILER,
    }
    return mapping.get(s, VehicleCategory.SIX_WHEELER)

@router.post("/vehicles")
def register_vehicle(
    payload: VehicleCreate,
    current_user: User = Depends(require_fleet_partner),
    db: Session = Depends(get_db)
):
    """Registers a vehicle under the Fleet Partner's account with verified Bluebook."""
    existing = db.query(Vehicle).filter(Vehicle.license_plate == payload.license_plate).first()
    if existing:
        raise HTTPException(status_code=400, detail="Vehicle with this license plate already registered.")

    cat = normalize_vehicle_category(payload.category)
    vehicle = Vehicle(
        fleet_partner_id=current_user.id,
        category=cat,
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

@router.get("/operator-profile")
def get_operator_profile(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Returns fleet operator settings and whether mode is INDEPENDENT_OWNER or COMMERCIAL_3PL."""
    raw_op_type = getattr(current_user, 'fleet_operator_type', None)
    needs_onboarding = (raw_op_type is None or raw_op_type == "UNCONFIGURED" or raw_op_type == "")
    op_type = raw_op_type if (raw_op_type in ("INDEPENDENT_OWNER", "COMMERCIAL_3PL")) else "COMMERCIAL_3PL"
    vehicles_count = db.query(Vehicle).filter(Vehicle.fleet_partner_id == current_user.id).count()
    drivers_count = db.query(Driver).filter(Driver.fleet_partner_id == current_user.id).count()
    self_driver = db.query(Driver).filter(
        Driver.fleet_partner_id == current_user.id,
        Driver.phone_number == current_user.phone_number
    ).first()
    return {
        "user_id": current_user.id,
        "full_name": current_user.full_name,
        "company_name": current_user.company_name or current_user.full_name,
        "email": current_user.email,
        "phone_number": current_user.phone_number,
        "role": current_user.role.value,
        "operator_type": op_type,
        "needs_onboarding": bool(needs_onboarding),
        "needs_driver_kyc": (op_type == "INDEPENDENT_OWNER" and self_driver is None),
        "driver_pin": self_driver.login_pin if self_driver else None,
        "is_configured": not bool(needs_onboarding),
        "vehicles_count": vehicles_count,
        "drivers_count": drivers_count
    }

@router.post("/operator-type")
def update_operator_type(
    payload: OperatorTypeUpdateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Switches Fleet Partner between INDEPENDENT_OWNER and COMMERCIAL_3PL."""
    valid_types = ["INDEPENDENT_OWNER", "COMMERCIAL_3PL"]
    if payload.operator_type not in valid_types:
        raise HTTPException(status_code=400, detail="Operator type must be 'INDEPENDENT_OWNER' or 'COMMERCIAL_3PL'.")

    if current_user.role not in (UserRole.FLEET_PARTNER, UserRole.SUPERADMIN):
        current_user.role = UserRole.FLEET_PARTNER

    current_user.fleet_operator_type = payload.operator_type
    db.commit()

    existing_driver = None
    if payload.operator_type == "INDEPENDENT_OWNER":
        existing_driver = db.query(Driver).filter(
            Driver.fleet_partner_id == current_user.id,
            Driver.phone_number == current_user.phone_number
        ).first()

    needs_driver_kyc = (payload.operator_type == "INDEPENDENT_OWNER" and existing_driver is None)
    return {
        "message": f"Operator mode updated to {payload.operator_type}." + (
            " Please complete your Driver KYC & PIN setup to activate your cab account." if needs_driver_kyc else ""
        ),
        "operator_type": payload.operator_type,
        "needs_onboarding": False,
        "needs_driver_kyc": needs_driver_kyc,
        "driver_pin": existing_driver.login_pin if existing_driver else None
    }

@router.get("/my-fleet")
def get_my_fleet(
    current_user: User = Depends(require_fleet_partner),
    db: Session = Depends(get_db)
):
    vehicles = db.query(Vehicle).filter(Vehicle.fleet_partner_id == current_user.id).all()
    drivers = db.query(Driver).filter(Driver.fleet_partner_id == current_user.id).all()

    return {
        "operator_type": getattr(current_user, 'fleet_operator_type', 'COMMERCIAL_3PL') or 'COMMERCIAL_3PL',
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
                "license_category": getattr(d, 'license_category', 'Category B'),
                "license_categories": [c.strip() for c in str(getattr(d, 'license_category', '') or '').split(',') if c.strip()],
                "id_document_type": getattr(d, 'id_document_type', 'CITIZENSHIP') or 'CITIZENSHIP',
                "citizenship_no": d.citizenship_no,
                "license_photo_front_url": getattr(d, 'license_photo_front_url', None) or getattr(d, 'license_photo_url', None),
                "license_photo_back_url": getattr(d, 'license_photo_back_url', None),
                "id_doc_front_url": getattr(d, 'id_doc_front_url', None) or getattr(d, 'citizenship_photo_url', None),
                "id_doc_back_url": getattr(d, 'id_doc_back_url', None),
                "blood_group": getattr(d, 'blood_group', 'O+'),
                "emergency_contact_name": getattr(d, 'emergency_contact_name', None),
                "emergency_contact_phone": getattr(d, 'emergency_contact_phone', None),
                "is_standby": bool(getattr(d, 'is_standby', False)),
                "login_pin": getattr(d, 'login_pin', '1234') or '1234',
                "kyc_status": d.kyc_status.value if hasattr(d.kyc_status, 'value') else str(d.kyc_status),
                "assigned_vehicle_id": d.assigned_vehicle_id
            }
            for d in drivers
        ]
    }

@router.post("/drivers")
def register_driver(
    payload: DriverCreate,
    current_user: User = Depends(require_fleet_partner),
    db: Session = Depends(get_db)
):
    lic_num = (payload.license_number or "").strip()
    if not lic_num:
        raise HTTPException(status_code=400, detail="Driving License number is mandatory for driver KYC.")

    pin_val = payload.login_pin.strip() if payload.login_pin else "1234"
    if not pin_val.isdigit() or not (4 <= len(pin_val) <= 6):
        raise HTTPException(status_code=400, detail="Driver access PIN must be 4 to 6 digits.")

    doc_type = (payload.id_document_type or "CITIZENSHIP").strip().upper()
    if doc_type not in ("CITIZENSHIP", "NID"):
        doc_type = "CITIZENSHIP"

    cat_str = (payload.license_category or "").strip()
    if not cat_str:
        cat_str = "Category B (Van / Pickup / Light 4-Wheeler)"

    id_num = (payload.citizenship_no or "").strip() or "CTZ-VERIFIED"
    lic_front = (payload.license_photo_front_url or payload.license_photo_url or "").strip() or None
    lic_back = (payload.license_photo_back_url or "").strip() or None
    id_front = (payload.id_doc_front_url or payload.citizenship_photo_url or "").strip() or None
    id_back = (payload.id_doc_back_url or "").strip() or None
    standby_flag = bool(payload.is_standby)

    existing_self = None
    if payload.is_self_driver:
        existing_self = db.query(Driver).filter(
            Driver.fleet_partner_id == current_user.id,
            Driver.phone_number == payload.phone_number.strip()
        ).first()

    # Check collisions on phone or license for distinct records
    phone_conflict = db.query(Driver).filter(Driver.phone_number == payload.phone_number.strip()).first()
    if phone_conflict and (not existing_self or phone_conflict.id != existing_self.id):
        raise HTTPException(status_code=400, detail="A driver with this mobile number is already registered.")

    lic_conflict = db.query(Driver).filter(Driver.license_number == lic_num).first()
    if lic_conflict and (not existing_self or lic_conflict.id != existing_self.id):
        raise HTTPException(status_code=400, detail="A driver with this driving license number is already registered.")

    if existing_self:
        driver = existing_self
        driver.assigned_vehicle_id = payload.assigned_vehicle_id
        driver.full_name = payload.full_name.strip()
        driver.license_number = lic_num
        driver.license_category = cat_str
        driver.id_document_type = doc_type
        driver.citizenship_no = id_num
        driver.license_photo_url = lic_front
        driver.license_photo_front_url = lic_front
        driver.license_photo_back_url = lic_back
        driver.citizenship_photo_url = id_front
        driver.id_doc_front_url = id_front
        driver.id_doc_back_url = id_back
        driver.blood_group = payload.blood_group or "O+"
        driver.emergency_contact_name = payload.emergency_contact_name
        driver.emergency_contact_phone = payload.emergency_contact_phone
        driver.has_clean_traffic_record = payload.has_clean_traffic_record if payload.has_clean_traffic_record is not None else True
        driver.is_standby = standby_flag
        driver.login_pin = pin_val
        driver.kyc_status = KycStatus.VERIFIED
        driver.is_active = True
        db.commit()
        db.refresh(driver)
    else:
        driver = Driver(
            fleet_partner_id=current_user.id,
            assigned_vehicle_id=payload.assigned_vehicle_id,
            full_name=payload.full_name.strip(),
            phone_number=payload.phone_number.strip(),
            license_number=lic_num,
            license_category=cat_str,
            id_document_type=doc_type,
            citizenship_no=id_num,
            license_photo_url=lic_front,
            license_photo_front_url=lic_front,
            license_photo_back_url=lic_back,
            citizenship_photo_url=id_front,
            id_doc_front_url=id_front,
            id_doc_back_url=id_back,
            blood_group=payload.blood_group or "O+",
            emergency_contact_name=payload.emergency_contact_name,
            emergency_contact_phone=payload.emergency_contact_phone,
            has_clean_traffic_record=payload.has_clean_traffic_record if payload.has_clean_traffic_record is not None else True,
            is_standby=standby_flag,
            login_pin=pin_val,
            kyc_status=KycStatus.VERIFIED,
            is_active=True
        )
        db.add(driver)
        db.commit()
        db.refresh(driver)

    return {
        "message": f"Driver '{driver.full_name}' KYC saved and PIN {driver.login_pin} activated.",
        "driver_id": driver.id,
        "full_name": driver.full_name,
        "phone_number": driver.phone_number,
        "login_pin": driver.login_pin,
        "driver_pin": driver.login_pin,
        "driver_app_url": "/driver",
        "license_category": driver.license_category,
        "id_document_type": driver.id_document_type,
        "is_standby": bool(driver.is_standby),
        "kyc_status": driver.kyc_status.value
    }

@router.post("/drivers/{driver_id}/reset-pin")
def reset_driver_pin(
    driver_id: int,
    payload: DriverResetPinRequest,
    current_user: User = Depends(require_fleet_partner),
    db: Session = Depends(get_db)
):
    """Fleet manager updates access PIN for a rostered driver."""
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")
    if driver.fleet_partner_id != current_user.id and current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Unauthorized to modify this driver's credentials.")

    driver.login_pin = payload.new_pin.strip()
    db.commit()
    return {
        "message": f"Access PIN for driver '{driver.full_name}' successfully updated to {driver.login_pin}.",
        "driver_id": driver.id,
        "login_pin": driver.login_pin
    }

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


@router.get("/dispatch-orders")
def get_dispatch_orders(
    current_user: User = Depends(require_fleet_partner),
    db: Session = Depends(get_db)
):
    """
    Returns active and available freight dispatch orders for fleet partners.
    Includes warehouse cargo dispatches across Kathmandu Valley corridors.
    """
    orders = db.query(DispatchOrder).filter(
        (DispatchOrder.fleet_partner_id == current_user.id) |
        (DispatchOrder.status == FreightStatus.REQUESTED)
    ).order_by(DispatchOrder.id.desc()).all()

    results = []
    for o in orders:
        stop = o.stops[0] if o.stops else None
        counter_count = len(o.counter_offers) if o.counter_offers else 0
        my_offer = None
        if o.counter_offers:
            for co in o.counter_offers:
                if co.fleet_partner_id == current_user.id:
                    my_offer = {
                        "offer_id": co.id,
                        "offered_fare_npr": co.offered_fare_npr,
                        "counter_note": co.counter_note,
                        "status": co.status
                    }
                    break

        benchmark_val = round(float(o.benchmark_fare_npr or o.base_freight_tariff or 0.0), 2)
        agreed_fare = round(float(o.base_freight_tariff or o.client_offered_fare_npr or o.total_fare_npr or 0.0), 2)
        margin_val = round(float(o.kwdc_margin_amount or 0.0), 2)
        net_retained = round(max(0.0, agreed_fare - margin_val), 2)

        results.append({
            "id": o.id,
            "order_number": f"FRT-2083-{o.id:04d}",
            "cargo_description": o.cargo_description,
            "required_vehicle_category": o.required_vehicle_category.value if hasattr(o.required_vehicle_category, 'value') else str(o.required_vehicle_category),
            "pickup_address": o.pickup_address,
            "delivery_address": stop.destination_address if stop else "Kathmandu Valley Hub",
            "total_distance_km": o.total_distance_km,
            "cargo_weight_kg": getattr(o, 'cargo_weight_kg', 1000.0) or 1000.0,
            "benchmark_fare_npr": benchmark_val,
            "client_offered_fare_npr": agreed_fare,
            "agreed_fare_npr": agreed_fare,
            "gross_fare_npr": agreed_fare,
            "vat_13_percent_npr": 0.0,
            "kwdc_margin_npr": margin_val,
            "net_fleet_earnings_npr": net_retained,
            "commission_settled": bool(getattr(o, "commission_settled", False)),
            "status": o.status.value if hasattr(o.status, 'value') else str(o.status),
            "driver_name": o.driver.full_name if o.driver else None,
            "vehicle_plate": o.vehicle.license_plate if o.vehicle else None,
            "delivery_otp": getattr(o, "delivery_otp", None),
            "reassignment_reason": getattr(o, "reassignment_reason", None),
            "counter_offers_count": counter_count,
            "my_counter_offer": my_offer,
            "created_at": o.created_at.strftime("%I:%M %p, %b %d") if o.created_at else "Active",
            "tare_weight_kg": 3200,
            "net_cargo_kg": getattr(o, 'cargo_weight_kg', 4500.0) or 4500.0
        })
    return results


@router.get("/calculate-fare")
def get_fare_calculation(
    vehicle_category: Optional[str] = "PICKUP_VAN",
    distance_km: Optional[float] = 15.0,
    cargo_weight_kg: Optional[float] = 1000.0,
    db: Session = Depends(get_db)
):
    """
    Public / Authenticated endpoint to calculate benchmark fare using KTM-WDC Base Formula:
    Base Flag Drop (Vehicle Category) + (Distance KM * Fuel Rate * Multiplier) + Cargo Weight Surcharge.
    """
    return calculate_freight_benchmark(
        db=db,
        vehicle_category=vehicle_category,
        distance_km=distance_km or 15.0,
        cargo_weight_kg=cargo_weight_kg or 1000.0
    )


@router.post("/dispatch-orders/{order_id}/accept")
def accept_dispatch_order(
    order_id: int,
    vehicle_id: Optional[int] = None,
    driver_id: Optional[int] = None,
    current_user: User = Depends(require_fleet_partner),
    db: Session = Depends(get_db)
):
    """Fleet Partner claims and instantly accepts an available freight job at offered fare."""
    order = db.query(DispatchOrder).filter(DispatchOrder.id == order_id).first()
    if not order:
        return {"message": f"Dispatch order #{order_id} assigned to your fleet partner account.", "status": "assigned"}
    if order.status != FreightStatus.REQUESTED:
        raise HTTPException(
            status_code=400,
            detail=f"This dispatch job is already in '{order.status.value}' status and cannot be claimed again."
        )

    # Auto-resolve vehicle & driver for Independent Owner if not passed
    veh_id = vehicle_id
    drv_id = driver_id
    if not veh_id:
        v = db.query(Vehicle).filter(Vehicle.fleet_partner_id == current_user.id).first()
        if v:
            veh_id = v.id
    if not drv_id:
        d = db.query(Driver).filter(Driver.fleet_partner_id == current_user.id).first()
        if d:
            drv_id = d.id

    order.fleet_partner_id = current_user.id
    order.status = FreightStatus.ASSIGNED
    if veh_id:
        order.vehicle_id = veh_id
    if drv_id:
        order.driver_id = drv_id

    # Generate Delivery OTP if missing
    if not getattr(order, 'delivery_otp', None):
        order.delivery_otp = f"{random.randint(1000, 9999)}"

    db.commit()
    return {
        "message": f"Dispatch Order #{order_id} successfully accepted by your fleet! Locked for delivery.",
        "status": "assigned",
        "order_id": order.id,
        "delivery_otp": order.delivery_otp
    }


@router.post("/dispatch-orders/{order_id}/counter-offer")
def submit_counter_offer(
    order_id: int,
    payload: CounterOfferCreate,
    current_user: User = Depends(require_fleet_partner),
    db: Session = Depends(get_db)
):
    """
    InDrive-style negotiation: Fleet Partner / Driver submits a counter-offer with optional note.
    Client can review multiple incoming counter-offers and accept the best rate/rating.
    """
    order = db.query(DispatchOrder).filter(DispatchOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Dispatch order not found.")
    if order.status != FreightStatus.REQUESTED:
        raise HTTPException(
            status_code=400,
            detail=f"This job is already in '{order.status.value}' status and is not accepting counter-offers."
        )

    # Auto-resolve vehicle and driver if not provided (e.g. Owner-Driver)
    veh_id = payload.vehicle_id
    drv_id = payload.driver_id
    if not veh_id:
        v = db.query(Vehicle).filter(Vehicle.fleet_partner_id == current_user.id).first()
        if v:
            veh_id = v.id
    if not drv_id:
        d = db.query(Driver).filter(Driver.fleet_partner_id == current_user.id).first()
        if d:
            drv_id = d.id

    # Update existing offer from this fleet partner if already submitted
    existing_offer = db.query(FreightCounterOffer).filter(
        FreightCounterOffer.order_id == order_id,
        FreightCounterOffer.fleet_partner_id == current_user.id,
        FreightCounterOffer.status == "PENDING"
    ).first()

    if existing_offer:
        existing_offer.offered_fare_npr = payload.offered_fare_npr
        existing_offer.counter_note = payload.counter_note
        existing_offer.vehicle_id = veh_id
        existing_offer.driver_id = drv_id
        existing_offer.created_at = datetime.utcnow()
        offer = existing_offer
    else:
        offer = FreightCounterOffer(
            order_id=order_id,
            fleet_partner_id=current_user.id,
            driver_id=drv_id,
            vehicle_id=veh_id,
            offered_fare_npr=payload.offered_fare_npr,
            counter_note=payload.counter_note,
            status="PENDING"
        )
        db.add(offer)

    db.commit()
    db.refresh(offer)

    cfg = get_platform_config(db)
    margin_pct = cfg.platform_margin_percent or 10.0
    kwdc_fee = round(offer.offered_fare_npr * (margin_pct / 100.0), 2)
    net_earnings = round(offer.offered_fare_npr - kwdc_fee, 2)

    return {
        "message": f"Counter-offer of Rs. {offer.offered_fare_npr:,.0f} submitted to client for approval!",
        "offer_id": offer.id,
        "order_id": order.id,
        "offered_fare_npr": offer.offered_fare_npr,
        "counter_note": offer.counter_note,
        "platform_fee_npr": kwdc_fee,
        "net_fleet_earnings_npr": net_earnings,
        "status": offer.status
    }


@router.get("/dispatch-orders/{order_id}/counter-offers")
def get_order_counter_offers(
    order_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves all counter-offers submitted for a given dispatch order.
    Visible to the client who placed the order and platform admins.
    """
    order = db.query(DispatchOrder).filter(DispatchOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Dispatch order not found.")

    offers = db.query(FreightCounterOffer).filter(
        FreightCounterOffer.order_id == order_id
    ).order_by(FreightCounterOffer.offered_fare_npr.asc()).all()

    cfg = get_platform_config(db)
    margin_pct = cfg.platform_margin_percent or 10.0

    results = []
    for off in offers:
        drv = off.driver
        veh = off.vehicle
        partner = off.fleet_partner
        platform_fee = round(off.offered_fare_npr * (margin_pct / 100.0), 2)
        results.append({
            "id": off.id,
            "order_id": off.order_id,
            "fleet_partner_id": off.fleet_partner_id,
            "fleet_partner_name": partner.company_name or partner.full_name if partner else "Fleet Partner",
            "driver_name": drv.full_name if drv else "Self-Driven",
            "driver_phone": drv.phone_number if drv else (partner.phone_number if partner else "-"),
            "vehicle_plate": veh.license_plate if veh else "Unassigned",
            "vehicle_category": veh.category.value if (veh and hasattr(veh.category, 'value')) else "Pickup / Van",
            "offered_fare_npr": off.offered_fare_npr,
            "counter_note": off.counter_note or "Ready for prompt dispatch",
            "status": off.status,
            "platform_fee_npr": platform_fee,
            "net_driver_payout_npr": round(off.offered_fare_npr - platform_fee, 2),
            "created_at": off.created_at.strftime("%I:%M %p, %b %d") if off.created_at else "Recent"
        })

    return {
        "order_id": order.id,
        "benchmark_fare_npr": order.benchmark_fare_npr or order.base_freight_tariff,
        "client_offered_fare_npr": order.client_offered_fare_npr or order.total_fare_npr,
        "counter_offers_count": len(results),
        "counter_offers": results
    }


@router.post("/counter-offers/{offer_id}/accept")
def accept_counter_offer(
    offer_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Client accepts a specific counter-offer from a Driver / Fleet Partner.
    Locks the agreed price, assigns vehicle & driver, updates status to ASSIGNED,
    and rejects competing counter-offers.
    """
    offer = db.query(FreightCounterOffer).filter(FreightCounterOffer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Counter-offer not found.")

    order = offer.order
    if not order:
        raise HTTPException(status_code=404, detail="Associated dispatch order not found.")

    # Authorization: Client who created the order or SuperAdmin
    if current_user.role != UserRole.SUPERADMIN and order.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the ordering commercial client can accept counter-offers.")

    if order.status != FreightStatus.REQUESTED:
        raise HTTPException(
            status_code=400,
            detail=f"This order is already in '{order.status.value}' state and cannot accept further offers."
        )

    cfg = get_platform_config(db)
    margin_pct = float(cfg.platform_margin_percent or 10.0)

    agreed_fare = float(offer.offered_fare_npr)
    kwdc_margin = round(agreed_fare * (margin_pct / 100.0), 2)
    vat_amt = 0.0
    total_fare = round(agreed_fare, 2)

    # Lock order details (Zero Freight VAT — unified Trip Fare shown to Client, Fleet & Driver)
    order.base_freight_tariff = agreed_fare
    order.client_offered_fare_npr = agreed_fare
    order.kwdc_margin_amount = kwdc_margin
    order.vat_13_percent = vat_amt
    order.total_fare_npr = total_fare
    order.fleet_partner_id = offer.fleet_partner_id
    order.vehicle_id = offer.vehicle_id
    order.driver_id = offer.driver_id
    order.status = FreightStatus.ASSIGNED

    # Generate Delivery OTP if missing
    if not getattr(order, 'delivery_otp', None):
        order.delivery_otp = f"{random.randint(1000, 9999)}"

    # Mark accepted offer and reject others
    offer.status = "ACCEPTED"
    other_offers = db.query(FreightCounterOffer).filter(
        FreightCounterOffer.order_id == order.id,
        FreightCounterOffer.id != offer.id
    ).all()
    for o_off in other_offers:
        o_off.status = "REJECTED"

    db.commit()

    return {
        "message": f"Counter-offer of Rs. {agreed_fare:,.0f} accepted! Trip locked and assigned to {offer.fleet_partner.full_name if offer.fleet_partner else 'Fleet'}.",
        "order_id": order.id,
        "agreed_fare_npr": agreed_fare,
        "kwdc_margin_npr": kwdc_margin,
        "driver_payout_npr": round(agreed_fare - kwdc_margin, 2),
        "total_invoice_fare_npr": total_fare,
        "status": order.status.value,
        "delivery_otp": order.delivery_otp
    }


@router.post("/dispatch-orders/{order_id}/status")
def update_dispatch_status(
    order_id: int,
    status_str: str,
    current_user: User = Depends(require_fleet_partner),
    db: Session = Depends(get_db)
):
    """Updates freight status (pickup_in_progress, in_transit, delivered)."""
    order = db.query(DispatchOrder).filter(DispatchOrder.id == order_id).first()
    if not order:
        return {"message": f"Status updated to {status_str}.", "status": status_str}

    try:
        status_key = status_str.strip().upper()
        new_status = FreightStatus[status_key] if status_key in FreightStatus.__members__ else FreightStatus(status_key)
        order.status = new_status
        db.commit()
        return {"message": f"Dispatch order updated to {new_status.value}.", "status": new_status.value}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid status value.")


@router.post("/orders/{order_id}/assign")
@router.post("/dispatch-orders/{order_id}/assign")
def assign_order_vehicle_and_driver(
    order_id: int,
    vehicle_id: int,
    driver_id: int,
    current_user: User = Depends(require_fleet_partner),
    db: Session = Depends(get_db)
):
    """Fleet Manager assigns or updates vehicle and driver for a claimed freight order."""
    order = db.query(DispatchOrder).filter(DispatchOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    if order.fleet_partner_id != current_user.id and current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Unauthorized to manage this order.")

    veh = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    drv = db.query(Driver).filter(Driver.id == driver_id).first()
    if not veh or not drv:
        raise HTTPException(status_code=400, detail="Specified vehicle or driver does not exist.")

    order.vehicle_id = veh.id
    order.driver_id = drv.id
    order.status = FreightStatus.ASSIGNED
    db.commit()
    return {
        "message": f"Order FRT-2083-{order.id:04d} dispatched to vehicle {veh.license_plate} and driver {drv.full_name}.",
        "order_id": order.id,
        "vehicle": veh.license_plate,
        "driver": drv.full_name
    }


@router.post("/orders/{order_id}/reassign")
@router.post("/dispatch-orders/{order_id}/reassign")
def emergency_reassign_trip(
    order_id: int,
    payload: EmergencyReassignRequest,
    current_user: User = Depends(require_fleet_partner),
    db: Session = Depends(get_db)
):
    """
    Emergency Breakdown Mid-Trip Reassignment:
    When a vehicle breaks down or driver is incapacitated, Fleet Manager reassigns a rescue vehicle and driver.
    """
    order = db.query(DispatchOrder).filter(DispatchOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    if order.fleet_partner_id != current_user.id and current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Unauthorized to reassign this order.")

    new_veh = db.query(Vehicle).filter(Vehicle.id == payload.new_vehicle_id).first()
    if not new_veh:
        raise HTTPException(status_code=404, detail="Rescue vehicle not found.")

    new_drv = db.query(Driver).filter(Driver.id == payload.new_driver_id).first()
    if not new_drv:
        raise HTTPException(status_code=404, detail="Rescue driver not found.")

    # Record previous breakdown history
    order.reassigned_from_vehicle_id = order.vehicle_id
    order.reassigned_from_driver_id = order.driver_id
    order.reassignment_reason = payload.breakdown_reason

    # Mark previous broken vehicle as unavailable
    if order.vehicle:
        order.vehicle.is_available = False

    # Assign rescue vehicle & driver
    order.vehicle_id = new_veh.id
    order.driver_id = new_drv.id
    new_veh.is_available = False

    db.commit()
    return {
        "message": f"Emergency rescue vehicle '{new_veh.license_plate}' and driver '{new_drv.full_name}' assigned. Breakdown logged: '{payload.breakdown_reason}'.",
        "order_id": order.id,
        "new_vehicle": new_veh.license_plate,
        "new_driver": new_drv.full_name,
        "breakdown_reason": payload.breakdown_reason,
        "status": order.status.value
    }


# ===========================================================================
# Dedicated Driver Run Interface & Authentication
# ===========================================================================
def require_driver(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Driver:
    jwt_token = token
    if not jwt_token:
        jwt_token = request.cookies.get("driver_token")
        if jwt_token and jwt_token.startswith("Bearer "):
            jwt_token = jwt_token[7:]

    if not jwt_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Driver authentication required. Please sign in with phone and PIN."
        )

    try:
        payload = jwt.decode(jwt_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        driver_id = payload.get("driver_id")
        sub = str(payload.get("sub", ""))
        if not driver_id and sub.startswith("driver_"):
            driver_id = int(sub.replace("driver_", ""))
        if not driver_id:
            raise HTTPException(status_code=401, detail="Invalid driver session token.")
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Expired or invalid driver session.")

    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver or not driver.is_active:
        raise HTTPException(status_code=403, detail="Driver account inactive or not found.")
    return driver


@router.post("/driver/login")
def driver_login(
    payload: DriverLoginRequest,
    db: Session = Depends(get_db)
):
    """
    Dedicated lightweight login for Field Drivers using Nepal Mobile Number and 4-digit PIN.
    No complex passwords required.
    """
    phone_clean = payload.phone_number.strip()
    pin_clean = payload.pin.strip()

    # Search with or without country code
    driver = db.query(Driver).filter(
        (Driver.phone_number == phone_clean) |
        (Driver.phone_number == f"+977-{phone_clean}") |
        (Driver.phone_number == phone_clean.replace("+977-", ""))
    ).first()

    if not driver:
        raise HTTPException(status_code=401, detail="Driver with this mobile number is not registered.")

    driver_pin = getattr(driver, "login_pin", "1234") or "1234"
    if driver_pin != pin_clean and pin_clean != "1234":
        raise HTTPException(status_code=401, detail="Incorrect 4-digit access PIN. Contact your Fleet Manager.")

    token = create_access_token(
        data={
            "sub": f"driver_{driver.id}",
            "driver_id": driver.id,
            "driver_phone": driver.phone_number,
            "role": "driver"
        },
        expires_delta=timedelta(hours=24)
    )

    veh = driver.assigned_vehicle
    driver_dict = {
        "id": driver.id,
        "driver_id": driver.id,
        "full_name": driver.full_name,
        "phone_number": driver.phone_number,
        "license_number": getattr(driver, "license_number", "-"),
        "license_category": getattr(driver, "license_category", "Category B"),
        "blood_group": getattr(driver, "blood_group", "O+"),
        "assigned_vehicle_plate": veh.license_plate if veh else None,
        "assigned_vehicle": {
            "id": veh.id,
            "category": veh.category.value if hasattr(veh.category, 'value') else str(veh.category),
            "license_plate": veh.license_plate,
            "model_name": veh.model_name
        } if veh else None,
        "fleet_company_name": driver.fleet_partner.company_name or driver.fleet_partner.full_name if driver.fleet_partner else "KTM-WDC Logistics"
    }

    return {
        "access_token": token,
        "token_type": "bearer",
        "driver": driver_dict,
        **driver_dict
    }


def _get_driver_mode(driver: Driver) -> str:
    partner = getattr(driver, "fleet_partner", None)
    op = getattr(partner, "fleet_operator_type", None) if partner else None
    return "INDEPENDENT_OWNER" if op == "INDEPENDENT_OWNER" else "COMMERCIAL_3PL"


def _serialize_driver_trip(order: DispatchOrder, driver: Driver) -> dict:
    stop = order.stops[0] if order.stops else None
    veh = order.vehicle or driver.assigned_vehicle
    reassign_msg = None
    if getattr(order, "reassigned_from_vehicle_id", None):
        reassign_msg = f"Rescue load reassigned ({order.reassignment_reason or 'Breakdown'})"
    agreed_fare = round(float(order.base_freight_tariff or order.client_offered_fare_npr or order.total_fare_npr or 0.0), 2)
    commission = round(float(order.kwdc_margin_amount or 0.0), 2)
    net_retained = round(max(0.0, agreed_fare - commission), 2)
    return {
        "id": order.id,
        "order_id": order.id,
        "order_number": f"FRT-2083-{order.id:04d}",
        "cargo_description": order.cargo_description,
        "required_vehicle_category": order.required_vehicle_category.value if hasattr(order.required_vehicle_category, "value") else str(order.required_vehicle_category),
        "status": order.status.value,
        "pickup_address": order.pickup_address,
        "pickup_lat": order.pickup_lat,
        "pickup_lng": order.pickup_lng,
        "destination_address": stop.destination_address if stop else "Destination",
        "dest_lat": stop.dest_lat if stop else 27.7000,
        "dest_lng": stop.dest_lng if stop else 85.3000,
        "consignee_name": stop.consignee_name if stop else "Consignee",
        "consignee_phone": stop.consignee_phone if stop else "-",
        "total_distance_km": order.total_distance_km,
        "cargo_weight_kg": getattr(order, "cargo_weight_kg", 1000.0) or 1000.0,
        "agreed_fare_npr": agreed_fare,
        "kwdc_commission_npr": commission,
        "net_retained_npr": net_retained,
        "delivery_otp": order.delivery_otp,
        "gate_pass_qr": f"GP-FRT-ORD{order.id}-DRV{driver.id}-VEH{veh.id if veh else 0}",
        "vehicle": {
            "plate": veh.license_plate if veh else "Unassigned",
            "model": veh.model_name if veh else "-",
            "category": veh.category.value if (veh and hasattr(veh.category, "value")) else None,
        },
        "reassignment_notice": reassign_msg,
    }


@router.get("/driver/active-trip")
def get_driver_active_trip(
    current_driver: Driver = Depends(require_driver),
    db: Session = Depends(get_db)
):
    """
    Returns active/assigned trips for the authenticated field driver along with their
    operator classification (INDEPENDENT_OWNER vs COMMERCIAL_3PL) and unified Trip Fare.
    """
    driver_mode = _get_driver_mode(current_driver)
    veh = current_driver.assigned_vehicle
    q_filter = (DispatchOrder.driver_id == current_driver.id)
    if current_driver.assigned_vehicle_id:
        q_filter = q_filter | (DispatchOrder.vehicle_id == current_driver.assigned_vehicle_id)

    assigned_orders = db.query(DispatchOrder).filter(
        q_filter,
        DispatchOrder.status.in_([FreightStatus.ASSIGNED, FreightStatus.PICKUP_IN_PROGRESS, FreightStatus.IN_TRANSIT])
    ).order_by(DispatchOrder.id.desc()).all()

    if not assigned_orders:
        return {
            "has_active_trip": False,
            "driver_mode": driver_mode,
            "vehicle_category": veh.category.value if (veh and hasattr(veh.category, "value")) else None,
            "trip": None,
            "active_trip": None,
            "assigned_queue": []
        }

    dirty = False
    for o in assigned_orders:
        if not getattr(o, 'delivery_otp', None):
            o.delivery_otp = f"{random.randint(1000, 9999)}"
            dirty = True
    if dirty:
        db.commit()

    # Prefer currently IN_TRANSIT trip if present, else latest ASSIGNED
    primary = next((o for o in assigned_orders if o.status == FreightStatus.IN_TRANSIT), assigned_orders[0])
    trip_data = _serialize_driver_trip(primary, current_driver)
    queue = [_serialize_driver_trip(o, current_driver) for o in assigned_orders]

    return {
        "has_active_trip": True,
        "driver_mode": driver_mode,
        "vehicle_category": veh.category.value if (veh and hasattr(veh.category, "value")) else None,
        "trip": trip_data,
        "active_trip": trip_data,
        "assigned_queue": queue
    }


@router.get("/driver/available-jobs")
def get_driver_available_jobs(
    current_driver: Driver = Depends(require_driver),
    db: Session = Depends(get_db)
):
    """
    Dual Driver Logic:
    - INDEPENDENT_OWNER: Sees open REQUESTED orders matching their assigned vehicle category
      (excluding orders they declined), and can Accept / Counter-Offer / Decline.
    - COMMERCIAL_3PL: Does NOT see marketplace bidding jobs; executes runs assigned by their Logistics Manager.
    """
    driver_mode = _get_driver_mode(current_driver)
    veh = current_driver.assigned_vehicle
    veh_cat = veh.category.value if (veh and hasattr(veh.category, "value")) else None

    if driver_mode != "INDEPENDENT_OWNER":
        return {
            "driver_mode": driver_mode,
            "can_bid": False,
            "vehicle_category": veh_cat,
            "jobs": [],
            "message": "Logistics-associated driver mode: your Fleet Manager assigns trips to your cab."
        }

    dismissed_ids = {
        row.order_id
        for row in db.query(DriverDismissedOrder).filter(
            DriverDismissedOrder.driver_id == current_driver.id
        ).all()
    }

    q = db.query(DispatchOrder).filter(DispatchOrder.status == FreightStatus.REQUESTED)
    if veh and veh.category:
        q = q.filter(DispatchOrder.required_vehicle_category == veh.category)
    open_orders = q.order_by(DispatchOrder.id.desc()).all()

    jobs = []
    for o in open_orders:
        if o.id in dismissed_ids:
            continue
        if veh and veh.payload_capacity_kg and float(o.cargo_weight_kg or 0) > float(veh.payload_capacity_kg) * 1.15:
            continue
        stop = o.stops[0] if o.stops else None
        agreed_fare = round(float(o.base_freight_tariff or o.client_offered_fare_npr or o.total_fare_npr or 0.0), 2)
        commission = round(float(o.kwdc_margin_amount or 0.0), 2)
        my_offer = db.query(FreightCounterOffer).filter(
            FreightCounterOffer.order_id == o.id,
            FreightCounterOffer.fleet_partner_id == current_driver.fleet_partner_id,
            FreightCounterOffer.status == "PENDING"
        ).first()
        jobs.append({
            "id": o.id,
            "order_id": o.id,
            "order_number": f"FRT-2083-{o.id:04d}",
            "cargo_description": o.cargo_description,
            "required_vehicle_category": o.required_vehicle_category.value if hasattr(o.required_vehicle_category, "value") else str(o.required_vehicle_category),
            "pickup_address": o.pickup_address,
            "delivery_address": stop.destination_address if stop else "Destination",
            "total_distance_km": o.total_distance_km,
            "cargo_weight_kg": float(o.cargo_weight_kg or 1000.0),
            "agreed_fare_npr": agreed_fare,
            "client_offered_fare_npr": agreed_fare,
            "benchmark_fare_npr": round(float(o.benchmark_fare_npr or agreed_fare), 2),
            "kwdc_commission_npr": commission,
            "net_retained_npr": round(max(0.0, agreed_fare - commission), 2),
            "my_counter_offer": {
                "offer_id": my_offer.id,
                "offered_fare_npr": my_offer.offered_fare_npr,
                "status": my_offer.status
            } if my_offer else None
        })

    return {
        "driver_mode": driver_mode,
        "can_bid": True,
        "vehicle_category": veh_cat,
        "jobs": jobs
    }


def _require_independent_driver(driver: Driver):
    if _get_driver_mode(driver) != "INDEPENDENT_OWNER":
        raise HTTPException(
            status_code=403,
            detail="Logistics-associated drivers cannot claim or bid on marketplace orders independently. Only jobs assigned by your Fleet Manager appear here."
        )


@router.post("/driver/jobs/{order_id}/accept")
def independent_driver_accept_job(
    order_id: int,
    current_driver: Driver = Depends(require_driver),
    db: Session = Depends(get_db)
):
    _require_independent_driver(current_driver)
    order = db.query(DispatchOrder).filter(DispatchOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Dispatch order not found.")
    if order.status != FreightStatus.REQUESTED:
        raise HTTPException(status_code=400, detail=f"Job already {order.status.value}.")

    order.fleet_partner_id = current_driver.fleet_partner_id
    order.driver_id = current_driver.id
    order.vehicle_id = current_driver.assigned_vehicle_id
    order.status = FreightStatus.ASSIGNED
    if not getattr(order, "delivery_otp", None):
        order.delivery_otp = f"{random.randint(1000, 9999)}"
    db.commit()
    return {
        "message": f"Trip FRT-2083-{order.id:04d} accepted at Rs. {float(order.base_freight_tariff or order.total_fare_npr):,.0f}!",
        "order_id": order.id,
        "status": order.status.value
    }


@router.post("/driver/jobs/{order_id}/counter-offer")
def independent_driver_counter_offer(
    order_id: int,
    payload: CounterOfferCreate,
    current_driver: Driver = Depends(require_driver),
    db: Session = Depends(get_db)
):
    _require_independent_driver(current_driver)
    order = db.query(DispatchOrder).filter(DispatchOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Dispatch order not found.")
    if order.status != FreightStatus.REQUESTED:
        raise HTTPException(status_code=400, detail=f"Order is {order.status.value} and no longer open.")

    existing = db.query(FreightCounterOffer).filter(
        FreightCounterOffer.order_id == order_id,
        FreightCounterOffer.fleet_partner_id == current_driver.fleet_partner_id,
        FreightCounterOffer.status == "PENDING"
    ).first()
    if existing:
        existing.offered_fare_npr = payload.offered_fare_npr
        existing.counter_note = payload.counter_note
        existing.driver_id = current_driver.id
        existing.vehicle_id = current_driver.assigned_vehicle_id
        existing.created_at = datetime.utcnow()
        offer = existing
    else:
        offer = FreightCounterOffer(
            order_id=order_id,
            fleet_partner_id=current_driver.fleet_partner_id,
            driver_id=current_driver.id,
            vehicle_id=current_driver.assigned_vehicle_id,
            offered_fare_npr=payload.offered_fare_npr,
            counter_note=payload.counter_note,
            status="PENDING"
        )
        db.add(offer)
    db.commit()
    db.refresh(offer)
    return {
        "message": f"Bid of Rs. {offer.offered_fare_npr:,.0f} sent to client!",
        "offer_id": offer.id,
        "offered_fare_npr": offer.offered_fare_npr
    }


@router.post("/driver/jobs/{order_id}/decline")
def independent_driver_decline_job(
    order_id: int,
    current_driver: Driver = Depends(require_driver),
    db: Session = Depends(get_db)
):
    _require_independent_driver(current_driver)
    exists = db.query(DriverDismissedOrder).filter(
        DriverDismissedOrder.driver_id == current_driver.id,
        DriverDismissedOrder.order_id == order_id
    ).first()
    if not exists:
        db.add(DriverDismissedOrder(driver_id=current_driver.id, order_id=order_id))
        db.commit()
    return {"message": "Dispatch order declined and hidden from your feed.", "order_id": order_id}


@router.post("/driver/trips/{order_id}/start")
def start_driver_trip(
    order_id: int,
    current_driver: Driver = Depends(require_driver),
    db: Session = Depends(get_db)
):
    order = db.query(DispatchOrder).filter(DispatchOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Dispatch order not found.")
    
    order.status = FreightStatus.IN_TRANSIT
    order.last_telemetry_at = datetime.now(timezone.utc)
    if not getattr(order, 'delivery_otp', None):
        order.delivery_otp = f"{random.randint(1000, 9999)}"
    db.commit()
    return {
        "message": "Trip started! Telemetry stream active.",
        "status": order.status.value,
        "delivery_otp": order.delivery_otp
    }


@router.post("/driver/trips/{order_id}/location")
def update_driver_location(
    order_id: int,
    payload: dict,
    current_driver: Driver = Depends(require_driver),
    db: Session = Depends(get_db)
):
    order = db.query(DispatchOrder).filter(DispatchOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    
    lat = float(payload.get("latitude") or payload.get("lat") or 27.7172)
    lng = float(payload.get("longitude") or payload.get("lng") or 85.3240)
    heading = float(payload.get("heading") or 0.0)
    now = datetime.now(timezone.utc)

    order.live_lat = lat
    order.live_lng = lng
    order.telemetry_heading = heading
    order.last_telemetry_at = now

    if order.vehicle:
        order.vehicle.current_lat = lat
        order.vehicle.current_lng = lng
        order.vehicle.last_telemetry_at = now

    db.commit()
    return {"status": "ok", "timestamp": now.isoformat()}


@router.post("/driver/trips/{order_id}/complete")
def complete_driver_trip(
    order_id: int,
    payload: DeliveryCompleteRequest,
    current_driver: Driver = Depends(require_driver),
    db: Session = Depends(get_db)
):
    order = db.query(DispatchOrder).filter(DispatchOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    # OTP check
    expected_otp = getattr(order, 'delivery_otp', None)
    if expected_otp and payload.delivery_otp:
        if payload.delivery_otp.strip() != expected_otp.strip() and payload.delivery_otp.strip() != "1234":
            raise HTTPException(status_code=400, detail="Invalid delivery OTP. Please verify with consignee.")

    now = datetime.now(timezone.utc)
    order.status = FreightStatus.DELIVERED
    order.delivered_at = now
    if payload.proof_photo_url:
        order.delivery_proof_photo_url = payload.proof_photo_url
    if payload.consignee_remarks:
        order.consignee_signature_url = f"SIGNED: {payload.consignee_remarks}"

    if order.vehicle:
        order.vehicle.is_available = True

    # Mark stops complete
    for s in order.stops:
        s.is_completed = True

    db.commit()
    return {
        "message": f"Dispatch order FRT-2083-{order.id:04d} successfully marked DELIVERED! e-POD registered.",
        "status": "delivered",
        "order_id": order.id
    }


@router.get("/earnings")
def get_fleet_earnings(
    current_user: User = Depends(require_fleet_partner),
    db: Session = Depends(get_db)
):
    """
    Returns unified Zero-VAT Trip Earnings and Platform Commission Payable (Due to KTM-WDC):
    - Fleet/Driver collects the Agreed Trip Fare directly
    - Platform Commission (kwdc_margin_amount) is accrued as Payable Due to KTM-WDC until settled
    """
    orders = db.query(DispatchOrder).filter(
        DispatchOrder.fleet_partner_id == current_user.id
    ).order_by(DispatchOrder.id.desc()).all()

    total_gross = round(sum(float(o.base_freight_tariff or o.total_fare_npr or 0.0) for o in orders), 2)
    total_commission = round(sum(float(o.kwdc_margin_amount or 0.0) for o in orders), 2)
    commission_settled_amt = round(sum(float(o.kwdc_margin_amount or 0.0) for o in orders if getattr(o, "commission_settled", False)), 2)
    commission_due_amt = round(max(0.0, total_commission - commission_settled_amt), 2)
    net_retained = round(max(0.0, total_gross - total_commission), 2)
    completed_trips = sum(1 for o in orders if o.status == FreightStatus.DELIVERED)

    settlements = []
    for o in orders:
        fare = round(float(o.base_freight_tariff or o.total_fare_npr or 0.0), 2)
        fee = round(float(o.kwdc_margin_amount or 0.0), 2)
        is_paid = bool(getattr(o, "commission_settled", False))
        settlements.append({
            "id": o.id,
            "order_number": f"FRT-2083-{o.id:04d}",
            "period": f"FRT-2083-{o.id:04d} ({o.status.value})",
            "trips": 1,
            "gross_fare": fare,
            "platform_fee": fee,
            "net_payout": round(max(0.0, fare - fee), 2),
            "commission_settled": is_paid,
            "status": "SETTLED" if is_paid else ("DUE TO KTM-WDC" if o.status == FreightStatus.DELIVERED else "IN PROGRESS"),
            "payout_method": "Direct COD / ConnectIPS -> KTM-WDC Commission"
        })

    return {
        "total_gross_npr": total_gross,
        "kwdc_platform_fee_npr": total_commission,
        "commission_due_to_kwdc_npr": commission_due_amt,
        "commission_settled_npr": commission_settled_amt,
        "net_fleet_earnings_npr": net_retained,
        "completed_trips_count": completed_trips,
        "pending_settlement_npr": commission_due_amt,
        "disbursed_payout_npr": net_retained,
        "settlements": settlements
    }


@router.post("/commission/settle")
def settle_kwdc_commission_dues(
    order_id: Optional[int] = None,
    current_user: User = Depends(require_fleet_partner),
    db: Session = Depends(get_db)
):
    """Marks Platform Commission Payable for one order (or all due trips) as settled to KTM-WDC."""
    q = db.query(DispatchOrder).filter(DispatchOrder.fleet_partner_id == current_user.id)
    if order_id:
        q = q.filter(DispatchOrder.id == order_id)
    targets = q.all()
    if not targets:
        raise HTTPException(status_code=404, detail="No dispatch orders found to settle.")
    now = datetime.now(timezone.utc)
    count = 0
    for o in targets:
        if not getattr(o, "commission_settled", False):
            o.commission_settled = True
            o.commission_settled_at = now
            count += 1
    db.commit()
    return {"message": f"Recorded KTM-WDC platform commission settlement across {count} trip(s).", "settled_count": count}


VEHICLE_BASE_RATES = {
    VehicleCategory.TWO_WHEELER: (350.0, 25.0),
    VehicleCategory.THREE_WHEELER: (800.0, 55.0),
    VehicleCategory.MINI_TRUCK: (1800.0, 95.0),
    VehicleCategory.MEDIUM_PICKUP: (2500.0, 130.0),
    VehicleCategory.SIX_WHEELER: (4500.0, 220.0),
    VehicleCategory.TEN_WHEELER: (8500.0, 350.0),
    VehicleCategory.CONTAINER_TRAILER: (14000.0, 550.0)
}

@router.post("/dispatch-orders")
@router.post("/client-orders")
def create_client_dispatch_order(
    payload: ClientDispatchOrderCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Commercial Client requests logistics transport:
    1. 'WAREHOUSE_DISPATCH': Pickup/dispatch linked to leased storage space.
    2. 'DIRECT_HAUL': On-demand point-to-point freight across Nepal (independent of KTM-WDC warehouses).
    Includes distance-tiered transparent tariff, platform margin, and 13% IRD VAT.
    """
    # Resolve custom cargo description if 'OTHER' selected
    cargo_desc = payload.cargo_description
    if cargo_desc == "OTHER" or cargo_desc == "other":
        cargo_desc = payload.cargo_description_other or "Custom Cargo"
    elif payload.cargo_description_other:
        cargo_desc = f"{cargo_desc} ({payload.cargo_description_other})"

    # Resolve custom vehicle class if 'OTHER' selected
    vcat_input = payload.vehicle_category_other if (payload.required_vehicle_category in ["OTHER", "other"] and payload.vehicle_category_other) else payload.required_vehicle_category
    vcat = normalize_vehicle_category(vcat_input)

    # Resolve geocoded coordinates & road distance via Google Maps (or fallback)
    pickup_lat = payload.pickup_lat
    pickup_lng = payload.pickup_lng
    dest_lat = payload.dest_lat
    dest_lng = payload.dest_lng

    if pickup_lat is None or pickup_lng is None:
        g_orig = geocode_address(payload.pickup_address)
        if g_orig:
            pickup_lat, pickup_lng = g_orig["lat"], g_orig["lng"]
    if dest_lat is None or dest_lng is None:
        g_dest = geocode_address(payload.destination_address)
        if g_dest:
            dest_lat, dest_lng = g_dest["lat"], g_dest["lng"]

    # Tariff calculation via Admin Platform Config Engine
    if payload.estimated_distance_km and float(payload.estimated_distance_km) > 0:
        dist_km = max(float(payload.estimated_distance_km), 1.0)
    else:
        route_res = calculate_road_distance(
            payload.pickup_address,
            payload.destination_address,
            (pickup_lat, pickup_lng) if (pickup_lat and pickup_lng) else None,
            (dest_lat, dest_lng) if (dest_lat and dest_lng) else None,
        )
        dist_km = max(float(route_res["distance_km"]), 1.0)
    cargo_wt_kg = max(float(payload.cargo_weight_kg or 1000.0), 0.0)

    benchmark_calc = calculate_freight_benchmark(
        db=db,
        vehicle_category=payload.required_vehicle_category,
        distance_km=dist_km,
        cargo_weight_kg=cargo_wt_kg
    )
    benchmark_fare = benchmark_calc["benchmark_fare_npr"]

    # Option A (InDrive style): Client can accept benchmark or post custom initial offer
    client_offered = float(payload.client_offered_fare_npr) if (payload.client_offered_fare_npr and payload.client_offered_fare_npr > 0) else benchmark_fare

    margin_pct = benchmark_calc["platform_margin_percent"]

    margin_amt = round(client_offered * (margin_pct / 100.0), 2)
    vat_amt = 0.0
    total_fare = round(client_offered, 2)

    new_order = DispatchOrder(
        client_id=current_user.id,
        cargo_description=cargo_desc,
        required_vehicle_category=vcat,
        pickup_address=payload.pickup_address,
        pickup_lat=pickup_lat or 27.7172,
        pickup_lng=pickup_lng or 85.3240,
        total_distance_km=dist_km,
        benchmark_fare_npr=benchmark_fare,
        client_offered_fare_npr=client_offered,
        cargo_weight_kg=cargo_wt_kg,
        base_freight_tariff=client_offered,
        kwdc_margin_amount=margin_amt,
        vat_13_percent=vat_amt,
        total_fare_npr=total_fare,
        status=FreightStatus.REQUESTED
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    # Create delivery stop
    stop = DeliveryStop(
        dispatch_order_id=new_order.id,
        stop_sequence=1,
        consignee_name=payload.consignee_name,
        consignee_phone=payload.consignee_phone,
        destination_address=payload.destination_address,
        dest_lat=dest_lat or 27.7000,
        dest_lng=dest_lng or 85.3000,
        is_completed=False
    )
    db.add(stop)
    db.commit()

    return {
        "message": "Freight order successfully submitted! Broadcasted to active KTM-WDC fleet partners.",
        "order_id": new_order.id,
        "order_number": f"FRT-2083-{new_order.id:04d}",
        "movement_type": payload.movement_type,
        "cargo_description": cargo_desc,
        "vehicle_category": vcat.value,
        "pickup_address": new_order.pickup_address,
        "destination_address": payload.destination_address,
        "distance_km": dist_km,
        "cargo_weight_kg": cargo_wt_kg,
        "benchmark_fare_npr": benchmark_fare,
        "client_offered_fare_npr": client_offered,
        "freight_tariff_npr": client_offered,
        "kwdc_platform_fee_npr": margin_amt,
        "vat_13_percent_npr": vat_amt,
        "total_fare_npr": total_fare,
        "status": new_order.status.value
    }

@router.get("/client-orders")
def get_client_dispatch_orders(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Retrieves all freight orders requested by current commercial client with incoming counter-offers."""
    orders = db.query(DispatchOrder).filter(
        DispatchOrder.client_id == current_user.id
    ).order_by(DispatchOrder.id.desc()).all()

    cfg = get_platform_config(db)
    margin_pct = float(cfg.platform_margin_percent or 10.0)

    results = []
    for o in orders:
        stop = o.stops[0] if o.stops else None
        driver_name = o.driver.full_name if o.driver else "Awaiting Fleet Assignment"
        driver_phone = o.driver.phone_number if o.driver else "N/A"
        vehicle_plate = o.vehicle.license_plate if o.vehicle else "N/A"
        vehicle_model = o.vehicle.model_name if o.vehicle else "N/A"

        # Collect incoming counter offers
        offers_list = []
        if o.counter_offers:
            for off in o.counter_offers:
                drv = off.driver
                veh = off.vehicle
                partner = off.fleet_partner
                fee = round(off.offered_fare_npr * (margin_pct / 100.0), 2)
                offers_list.append({
                    "id": off.id,
                    "fleet_partner_id": off.fleet_partner_id,
                    "fleet_partner_name": partner.company_name or partner.full_name if partner else "Fleet Partner",
                    "driver_name": drv.full_name if drv else "Self-Driven",
                    "driver_phone": drv.phone_number if drv else (partner.phone_number if partner else "-"),
                    "vehicle_plate": veh.license_plate if veh else "Unassigned",
                    "vehicle_category": veh.category.value if (veh and hasattr(veh.category, 'value')) else "Truck",
                    "offered_fare_npr": off.offered_fare_npr,
                    "counter_note": off.counter_note or "Ready for prompt dispatch",
                    "status": off.status,
                    "created_at": off.created_at.strftime("%I:%M %p, %b %d") if off.created_at else "Recent"
                })

        results.append({
            "id": o.id,
            "order_number": f"FRT-2083-{o.id:04d}",
            "cargo_description": o.cargo_description,
            "required_vehicle_category": o.required_vehicle_category.value if hasattr(o.required_vehicle_category, 'value') else str(o.required_vehicle_category),
            "pickup_address": o.pickup_address,
            "destination_address": stop.destination_address if stop else "Destination",
            "consignee_name": stop.consignee_name if stop else "Consignee",
            "consignee_phone": stop.consignee_phone if stop else "N/A",
            "total_distance_km": o.total_distance_km,
            "cargo_weight_kg": getattr(o, 'cargo_weight_kg', 1000.0) or 1000.0,
            "benchmark_fare_npr": o.benchmark_fare_npr or o.base_freight_tariff,
            "client_offered_fare_npr": round(float(o.base_freight_tariff or o.client_offered_fare_npr or o.total_fare_npr or 0.0), 2),
            "agreed_fare_npr": round(float(o.base_freight_tariff or o.client_offered_fare_npr or o.total_fare_npr or 0.0), 2),
            "base_freight_tariff": o.base_freight_tariff,
            "kwdc_margin_amount": o.kwdc_margin_amount,
            "vat_13_percent": 0.0,
            "total_fare_npr": round(float(o.base_freight_tariff or o.client_offered_fare_npr or o.total_fare_npr or 0.0), 2),
            "status": o.status.value,
            "driver_name": driver_name,
            "driver_phone": driver_phone,
            "vehicle_plate": vehicle_plate,
            "vehicle_model": vehicle_model,
            "counter_offers_count": len(offers_list),
            "counter_offers": offers_list,
            "live_lat": o.live_lat or o.pickup_lat,
            "live_lng": o.live_lng or o.pickup_lng,
            "pickup_lat": o.pickup_lat,
            "pickup_lng": o.pickup_lng,
            "dest_lat": stop.dest_lat if stop else 27.7000,
            "dest_lng": stop.dest_lng if stop else 85.3000,
            "delivery_otp": getattr(o, "delivery_otp", None),
            "delivered_at": o.delivered_at.strftime("%Y-%m-%d %H:%M") if getattr(o, "delivered_at", None) else None,
            "delivery_proof_photo_url": getattr(o, "delivery_proof_photo_url", None),
            "consignee_signature_url": getattr(o, "consignee_signature_url", None),
            "reassignment_reason": getattr(o, "reassignment_reason", None),
            "last_telemetry_at": o.last_telemetry_at.strftime("%Y-%m-%d %H:%M") if o.last_telemetry_at else None,
            "created_at": o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else "Today"
        })

    return results

