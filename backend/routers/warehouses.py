"""
Warehouse & Real Estate Router for KTM-WDC
Enforces:
1. 10% Floor Block Partitioning Engine
2. Zero Holding Liability for KWDC when idle
3. Property Owner listing in pending state
4. Permanent lockout of owner modifications once approved by Admin
5. Maintenance hold with mandatory reason note
6. Privacy Shield (Owner & Client identities masked)
"""
import math
import random
import hashlib
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from backend.database import get_db
from backend.models import (
    Warehouse, WarehouseRequest, WarehousePhoto, User, UserRole,
    BookingStatus, SpaceType, AreaUnit, TaxInvoice, PaymentStatus,
    StockItem, InventoryUnit, InventoryUnitType, ClientSavedAddress, LienNotificationLog,
    WarehouseChangeRequest, WarehouseActivityLog, IncidentReport
)
from backend.schemas import (
    WarehouseCreate, MaintenanceHoldRequest, BookingRequestCreate,
    BookingModifyRequest, StockItemCreate, SavedAddressCreate, OwnerChangeRequestCreate
)
from backend.auth_utils import require_user, get_current_user
from backend.services.unit_converter import to_sqft, from_sqft_to_all, get_warehouse_usable_capacity
from backend.services.vat_service import generate_ird_tax_invoice
from backend.services.overdue_monitor import calculate_flexible_storage_cost
from backend.services.contract_service import generate_client_storage_contract, generate_master_lease_contract
from backend.config import settings

router = APIRouter(prefix="/api/warehouses", tags=["Warehouses & Storage"])

def normalize_space_type(val) -> SpaceType:
    if not val:
        return SpaceType.COVERED_GODOWN
    s = str(val.value if hasattr(val, "value") else val).upper()
    mapping = {
        "RESIDENTIAL_BASEMENT": SpaceType.RESIDENTIAL_BASEMENT,
        "COMMERCIAL_SHUTTER": SpaceType.COMMERCIAL_SHUTTER,
        "COVERED_GODOWN": SpaceType.COVERED_GODOWN,
        "WALLED_LAND_PLOT": SpaceType.WALLED_LAND_PLOT,
        "DRY_STORAGE": SpaceType.COVERED_GODOWN,
        "COLD_STORAGE": SpaceType.COVERED_GODOWN,
        "BONDED_WAREHOUSE": SpaceType.COVERED_GODOWN,
        "HEAVY_INDUSTRIAL": SpaceType.COVERED_GODOWN,
        "OPEN_YARD": SpaceType.WALLED_LAND_PLOT
    }
    return mapping.get(s, SpaceType.COVERED_GODOWN)

def normalize_area_unit(val) -> AreaUnit:
    if not val:
        return AreaUnit.SQFT
    if isinstance(val, AreaUnit):
        return val
    s = str(val.value if hasattr(val, "value") else val).upper()
    try:
        return AreaUnit[s]
    except KeyError:
        return AreaUnit.SQFT

@router.post("/list-space")
def list_warehouse_space(
    payload: WarehouseCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Property Owner registers empty space.
    - Accepts any unit (sqft, sqm, aana, ropani, bigha, kattha, cuft) and converts to sqft.
    - Initial state: PENDING APPROVAL (is_approved=False, is_available=False).
    - KWDC Holding liability = Rs. 0.
    """
    if current_user.role not in [UserRole.PROPERTY_OWNER, UserRole.SUPERADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Property Owners can list physical spaces."
        )

    # Convert entered unit to standard sqft
    raw_val = payload.input_value if payload.input_value is not None else (payload.total_sqft if payload.total_sqft is not None else 1000.0)
    unit_str = payload.input_unit.value if hasattr(payload.input_unit, "value") else str(payload.input_unit or "sqft")
    normalized_sqft = to_sqft(raw_val, unit_str, payload.ceiling_height_ft)
    rate = payload.monthly_rate_per_sqft if payload.monthly_rate_per_sqft is not None else (payload.base_rate_per_sqft if payload.base_rate_per_sqft is not None else 45.0)
    road_width = payload.road_access_width_ft if payload.road_access_width_ft is not None else (payload.road_access_ft if payload.road_access_ft is not None else 20.0)
    stype = normalize_space_type(payload.space_type)
    ceiling_ht = 0.0 if stype == SpaceType.WALLED_LAND_PLOT else float(payload.ceiling_height_ft or 12.0)

    new_warehouse = Warehouse(
        owner_id=current_user.id,
        title=payload.title,
        space_type=stype,
        total_sqft=normalized_sqft,
        available_sqft=normalized_sqft,
        clear_ceiling_height_ft=ceiling_ht,
        original_input_unit=normalize_area_unit(payload.input_unit),
        original_input_value=raw_val,
        monthly_rate_per_sqft=rate,
        min_lease_months=payload.min_lease_months,
        province=payload.province or "Bagmati",
        district=payload.district or "Kathmandu",
        municipality=payload.municipality or "Kathmandu",
        ward_no=payload.ward_no or 1,
        neighborhood_landmark=payload.neighborhood_landmark or "Kathmandu Valley Hub",
        latitude=payload.latitude or 27.7172,
        longitude=payload.longitude or 85.3240,
        road_access_ft=road_width,
        has_three_phase_power=payload.has_three_phase_power,
        has_forklift_ramp=payload.has_forklift_ramp,
        has_cctv=payload.has_cctv,
        has_cold_storage=payload.has_cold_storage,
        temp_min_c=payload.temp_min_c,
        temp_max_c=payload.temp_max_c,
        is_approved=False, # Strictly pending admin audit
        is_available=False,
        is_on_maintenance_hold=False
    )
    db.add(new_warehouse)
    db.commit()
    db.refresh(new_warehouse)

    # Save property gallery photos if provided
    if payload.photo_urls:
        for idx, p_url in enumerate(payload.photo_urls):
            clean_url = (p_url or "").strip()
            if clean_url:
                db.add(WarehousePhoto(
                    warehouse_id=new_warehouse.id,
                    photo_url=clean_url,
                    caption=f"Facility View #{idx + 1}"
                ))
        db.commit()

    return {
        "message": "Property submitted for verification! Our team will audit the specs and dispatch your Master Commercial Agreement.",
        "warehouse_id": new_warehouse.id,
        "total_sqft": new_warehouse.total_sqft,
        "status": "PENDING_ADMIN_REVIEW",
        "holding_liability": "NPR 0.00 (Zero Holding Liability until rented)"
    }

@router.put("/{warehouse_id}/owner-edit")
def edit_warehouse_space(
    warehouse_id: int,
    payload: WarehouseCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Enforces Non-Negotiable Lockout Rule:
    Once approved by Admin, all operations like modifying warehouse features,
    assigning to client, and availability changes are strictly governed by Admin.
    """
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found.")

    if warehouse.owner_id != current_user.id and current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Unauthorized access.")

    # Permanent Lockout Check
    if warehouse.is_approved and current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "LOCKOUT ENFORCED: This facility has been audited and approved. "
                "To protect contracted commercial tenants, modifications to features, "
                "capacity, or tariffs are governed exclusively by KTM-WDC Admin."
            )
        )

    # If still pending review, allow edits
    normalized_sqft = to_sqft(payload.input_value, payload.input_unit.value, payload.ceiling_height_ft)
    warehouse.title = payload.title
    warehouse.space_type = payload.space_type
    warehouse.total_sqft = normalized_sqft
    warehouse.available_sqft = normalized_sqft
    warehouse.clear_ceiling_height_ft = payload.ceiling_height_ft
    warehouse.original_input_unit = payload.input_unit
    warehouse.original_input_value = payload.input_value
    warehouse.monthly_rate_per_sqft = payload.monthly_rate_per_sqft
    warehouse.road_access_ft = payload.road_access_ft
    warehouse.neighborhood_landmark = payload.neighborhood_landmark
    warehouse.latitude = payload.latitude
    warehouse.longitude = payload.longitude
    warehouse.has_three_phase_power = payload.has_three_phase_power
    warehouse.has_forklift_ramp = payload.has_forklift_ramp
    warehouse.has_cctv = payload.has_cctv
    warehouse.has_cold_storage = payload.has_cold_storage
    
    db.commit()
    return {"message": "Pending listing updated successfully."}

@router.post("/{warehouse_id}/request-maintenance-hold")
def request_maintenance_hold(
    warehouse_id: int,
    payload: MaintenanceHoldRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Rule 5: Maintenance Hold with Mandatory Reason Note.
    Owner notifies Admin to pause availability for necessary repairs.
    """
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found.")

    if warehouse.owner_id != current_user.id and current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Unauthorized.")

    if not payload.hold_reason_note or len(payload.hold_reason_note.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="A detailed Hold Reason Note (minimum 10 characters) is mandatory to alert Admin."
        )

    warehouse.is_on_maintenance_hold = payload.is_on_hold
    warehouse.hold_reason_note = payload.hold_reason_note
    # If on maintenance hold, remove from active public catalog
    if payload.is_on_hold:
        warehouse.is_available = False
    elif warehouse.is_approved:
        warehouse.is_available = True

    db.commit()
    return {
        "message": "Maintenance status updated and audit log transmitted to Admin.",
        "is_on_maintenance_hold": warehouse.is_on_maintenance_hold,
        "hold_reason_note": warehouse.hold_reason_note
    }

@router.get("/my-listings")
def get_my_listings(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    warehouses = db.query(Warehouse).filter(Warehouse.owner_id == current_user.id).all()
    results = []
    for w in warehouses:
        units = from_sqft_to_all(w.total_sqft, w.clear_ceiling_height_ft)
        tot = float(w.total_sqft or 0.0)
        avail = float(w.available_sqft or 0.0)
        occupied = round(max(0.0, tot - avail), 2)
        occ_pct = round((occupied / tot) * 100.0, 1) if tot > 0 else 0.0
        rate = float(w.monthly_rate_per_sqft or 45.0)
        potential_yield = round(tot * rate * 0.90, 2)
        realized_yield = round(occupied * rate * 0.90, 2)

        photos_list = [
            {"id": p.id, "url": p.photo_url, "caption": p.caption or "Facility Photo"}
            for p in (w.photos or [])
        ]
        cr_list = [
            {
                "id": cr.id,
                "request_type": cr.request_type,
                "requested_rate_per_sqft": cr.requested_rate_per_sqft,
                "reason_note": cr.reason_note,
                "status": cr.status,
                "admin_notes": cr.admin_notes,
                "created_at": cr.created_at.strftime("%Y-%m-%d") if cr.created_at else ""
            }
            for cr in (w.change_requests or [])
        ]

        results.append({
            "id": w.id,
            "title": w.title,
            "space_type": w.space_type.value,
            "total_sqft": tot,
            "available_sqft": avail,
            "occupied_sqft": occupied,
            "occupancy_percent": occ_pct,
            "potential_monthly_yield_npr": potential_yield,
            "realized_monthly_yield_npr": realized_yield,
            "monthly_rate_per_sqft": rate,
            "base_rate_per_sqft": rate,
            "clear_ceiling_height_ft": w.clear_ceiling_height_ft,
            "road_access_width_ft": w.road_access_ft,
            "municipality": w.municipality,
            "district": w.district,
            "is_approved": w.is_approved,
            "is_available": w.is_available,
            "is_on_maintenance_hold": w.is_on_maintenance_hold,
            "hold_reason_note": w.hold_reason_note,
            "neighborhood_landmark": w.neighborhood_landmark,
            "latitude": w.latitude,
            "longitude": w.longitude,
            "units": units,
            "photos": photos_list,
            "change_requests": cr_list,
            "contract_executed": bool(w.lease_contract_url or w.is_approved)
        })
    return results

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two GPS coordinates in kilometers."""
    R = 6371.0 # Earth's radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)

NEPAL_AREA_COORDINATES = {
    "balaju": (27.7333, 85.3000),
    "kalanki": (27.6937, 85.2816),
    "koteshwor": (27.6766, 85.3475),
    "chobhar": (27.6603, 85.2872),
    "satungal": (27.6894, 85.2442),
    "teku": (27.7010, 85.3050),
    "thapathali": (27.6917, 85.3204),
    "gongabu": (27.7371, 85.3142),
    "bhaktapur": (27.6710, 85.4298),
    "thimi": (27.6823, 85.3854),
    "lalitpur": (27.6683, 85.3206),
    "patan": (27.6683, 85.3206),
    "saneba": (27.6840, 85.3080),
    "birgunj": (27.0137, 84.8770),
    "bhairahawa": (27.5050, 83.4500),
    "butwal": (27.7006, 83.4484),
    "pokhara": (28.2096, 83.9856),
    "biratnagar": (26.4525, 87.2718),
    "hetauda": (27.4287, 85.0322),
    "chitwan": (27.5291, 84.3542),
    "narayangarh": (27.6939, 84.4281),
    "dhading": (27.8631, 84.9015),
    "banepa": (27.6298, 85.5214),
    "dhulikhel": (27.6253, 85.5561),
}

@router.get("/catalog")
def get_public_catalog(
    space_type: Optional[str] = None,
    min_sqft: Optional[float] = None,
    cold_storage_only: Optional[bool] = None,
    area: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: Optional[float] = None,
    db: Session = Depends(get_db)
):
    """
    Public Catalog enforcing:
    1. Only approved and active spaces shown.
    2. Spatial Distance Filter: Search by area or GPS with radius (km).
    3. Privacy Shield: Owner identities masked.
    """
    query = db.query(Warehouse).filter(
        Warehouse.is_approved == True,
        Warehouse.is_available == True,
        Warehouse.is_on_maintenance_hold == False
    )

    if space_type:
        stype = normalize_space_type(space_type)
        query = query.filter(Warehouse.space_type == stype)
    if min_sqft:
        query = query.filter(Warehouse.available_sqft >= min_sqft)
    if cold_storage_only:
        query = query.filter(Warehouse.has_cold_storage == True)

    # Determine reference coordinates for radius search
    ref_lat = lat
    ref_lng = lng
    clean_area = (area or "").strip().lower()

    if (ref_lat is None or ref_lng is None) and clean_area:
        for hub_name, coords in NEPAL_AREA_COORDINATES.items():
            if hub_name in clean_area or clean_area in hub_name:
                ref_lat, ref_lng = coords
                break

    warehouses = query.all()
    results = []

    for w in warehouses:
        units = from_sqft_to_all(w.total_sqft, w.clear_ceiling_height_ft)
        w_lat = float(w.latitude or 27.7172)
        w_lng = float(w.longitude or 85.3240)
        
        distance_km = None
        if ref_lat is not None and ref_lng is not None:
            distance_km = haversine_km(ref_lat, ref_lng, w_lat, w_lng)
            # If radius constraint is supplied, filter out spaces outside radius
            if radius_km is not None and radius_km > 0 and distance_km > radius_km:
                continue
        elif clean_area:
            # Fallback text match if coordinates not resolved
            loc_str = f"{w.title} {w.municipality or ''} {w.district or ''} {w.neighborhood_landmark or ''}".lower()
            if clean_area not in loc_str:
                continue

        results.append({
            "id": w.id,
            "title": w.title,
            "space_type": w.space_type.value,
            "total_sqft": w.total_sqft,
            "available_sqft": w.available_sqft,
            "monthly_rate_per_sqft": w.monthly_rate_per_sqft,
            "district": w.district,
            "municipality": w.municipality,
            "neighborhood_landmark": w.neighborhood_landmark,
            "latitude": w.latitude,
            "longitude": w.longitude,
            "distance_km": distance_km,
            "road_access_ft": w.road_access_ft,
            "has_three_phase_power": w.has_three_phase_power,
            "has_forklift_ramp": w.has_forklift_ramp,
            "has_cctv": w.has_cctv,
            "has_cold_storage": w.has_cold_storage,
            "units": units,
            "photos": [p.photo_url for p in (w.photos or [])],
            "privacy_shield_note": "Direct owner contact is protected. KTM-WDC acts as your verified corporate counterparty."
        })

    # Sort by distance if available, otherwise default by id
    if ref_lat is not None and ref_lng is not None:
        results.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 999999.0)

    return results

@router.get("/{warehouse_id}/capacity-breakdown")
def get_capacity_breakdown(warehouse_id: int, db: Session = Depends(get_db)):
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found.")
    return get_warehouse_usable_capacity(warehouse.total_sqft)

@router.get("/estimate-storage")
def estimate_storage_tariff(
    sqft: float = 2000.0,
    monthly_rate_per_sqft: float = 45.0,
    booking_duration_type: str = "MONTHLY",
    duration_value: int = 3
):
    """Calculates 3-tier storage pricing for DAILY (1-6 days), WEEKLY (1-3 weeks), or MONTHLY."""
    return calculate_flexible_storage_cost(
        allocated_sqft=sqft,
        monthly_rate_per_sqft=monthly_rate_per_sqft,
        booking_duration_type=booking_duration_type,
        duration_value=duration_value
    )

@router.post("/book")
def book_warehouse_space(
    payload: BookingRequestCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Client books commercial storage (DAILY 1-6 days, WEEKLY 1-3 weeks, or MONTHLY 1+ months):
    - Billed directly on continuous requested square footage.
    - Enforces Advance Payment covenant (Pay First).
    - Generates IRD Schedule 13 Tax Invoice with 13% statutory VAT & Storage Contract with Lien/Auction clause.
    """
    warehouse = db.query(Warehouse).filter(
        Warehouse.id == payload.warehouse_id,
        Warehouse.is_approved == True,
        Warehouse.is_available == True
    ).first()

    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found or currently unavailable.")

    if payload.requested_sqft > warehouse.available_sqft:
        raise HTTPException(status_code=400, detail=f"Requested space exceeds available capacity of {warehouse.available_sqft:,.2f} sq ft.")

    allocated_sqft = payload.requested_sqft
    dtype = (payload.booking_duration_type or "MONTHLY").upper()
    dval = payload.duration_value if payload.duration_value is not None else (payload.duration_months or 3)

    calc = calculate_flexible_storage_cost(
        allocated_sqft=allocated_sqft,
        monthly_rate_per_sqft=warehouse.monthly_rate_per_sqft,
        booking_duration_type=dtype,
        duration_value=dval
    )

    booking = WarehouseRequest(
        client_id=current_user.id,
        warehouse_id=warehouse.id,
        requested_sqft=payload.requested_sqft,
        allocated_billed_sqft=allocated_sqft,
        monthly_base_rent=calc["base_rent"],
        kwdc_margin_amount=calc["kwdc_margin_amount"],
        vat_13_percent=calc["vat_13_percent"],
        total_monthly_bill=calc["total_bill"],
        booking_duration_type=calc["booking_duration_type"],
        duration_value=calc["duration_value"],
        duration_days=calc["duration_days"],
        client_intended_use=payload.client_intended_use or "Commercial Freight",
        advance_payment_status="PAYMENT_DUE",
        status=BookingStatus.PENDING_REVIEW
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Create IRD Schedule 13 Invoice
    inv_number = f"KWDC-2083-{booking.id:04d}"
    pan_val = payload.buyer_pan or payload.client_pan_vat or current_user.kyc_pan_vat
    inv_data = generate_ird_tax_invoice(
        invoice_number=inv_number,
        buyer_name=current_user.full_name,
        buyer_pan=pan_val,
        service_type=f"STORAGE_{calc['booking_duration_type']}",
        base_tariff=calc["base_rent"],
        margin_percent=0.10
    )

    invoice = TaxInvoice(
        invoice_number=inv_number,
        storage_booking_id=booking.id,
        buyer_name=current_user.full_name,
        buyer_pan_vat=pan_val,
        taxable_base_amount=inv_data["taxable_amount"],
        kwdc_admin_margin=inv_data["kwdc_admin_margin"],
        vat_13_percent=inv_data["vat_13_percent"],
        gross_total_npr=inv_data["gross_total_npr"],
        qr_payload=inv_data["qr_payload"],
        payment_status=PaymentStatus.UNPAID
    )
    db.add(invoice)
    db.commit()

    contract = generate_client_storage_contract(booking, current_user, warehouse)

    return {
        "message": f"Storage booking ({calc['billing_label']}) submitted! Advance payment of Rs. {calc['total_bill']:,.2f} required to activate gate access.",
        "booking_id": booking.id,
        "requested_sqft": payload.requested_sqft,
        "allocated_billed_sqft": allocated_sqft,
        "booking_duration_type": calc["booking_duration_type"],
        "duration_value": calc["duration_value"],
        "duration_days": calc["duration_days"],
        "billing_label": calc["billing_label"],
        "monthly_base_rent_npr": calc["base_rent"],
        "kwdc_margin_npr": calc["kwdc_margin_amount"],
        "vat_13_percent_npr": calc["vat_13_percent"],
        "gross_monthly_total_npr": calc["total_bill"],
        "invoice_number": inv_number,
        "qr_data_uri": inv_data["qr_data_uri"],
        "contract_number": contract["contract_number"],
        "contract_text": contract["contract_text"],
        "status": "PENDING_ADMIN_ACTIVATION"
    }

@router.get("/my-bookings")
def get_client_bookings(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Returns all storage reservations and active leases for the authenticated commercial client,
    including 3-tier duration metadata, advance payment status, and 60-day lien countdowns.
    """
    bookings = db.query(WarehouseRequest).filter(WarehouseRequest.client_id == current_user.id).order_by(WarehouseRequest.created_at.desc()).all()
    now = datetime.now(timezone.utc)
    results = []
    for b in bookings:
        days_left = None
        if b.default_countdown_deadline:
            dl = b.default_countdown_deadline
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=timezone.utc)
            days_left = max(0, (dl - now).days)

        notifications = [
            {
                "stage": n.stage,
                "message": n.message,
                "sent_at": n.sent_at.strftime("%Y-%m-%d %H:%M") if n.sent_at else ""
            }
            for n in (b.lien_notifications or [])
        ]

        results.append({
            "id": b.id,
            "warehouse_id": b.warehouse_id,
            "warehouse_title": b.warehouse.title if b.warehouse else "KTM Commercial Storage",
            "neighborhood_landmark": b.warehouse.neighborhood_landmark if b.warehouse else "Kathmandu",
            "district": b.warehouse.district if b.warehouse else "Kathmandu",
            "warehouse_available_sqft": b.warehouse.available_sqft if b.warehouse else 0.0,
            "monthly_rate_per_sqft": b.warehouse.monthly_rate_per_sqft if b.warehouse else 45.0,
            "requested_sqft": b.requested_sqft,
            "allocated_billed_sqft": b.allocated_billed_sqft,
            "booking_duration_type": getattr(b, "booking_duration_type", "MONTHLY") or "MONTHLY",
            "duration_value": getattr(b, "duration_value", 3) or 3,
            "duration_days": getattr(b, "duration_days", 90) or 90,
            "client_intended_use": getattr(b, "client_intended_use", "Commercial Freight"),
            "monthly_base_rent": b.monthly_base_rent,
            "kwdc_margin_amount": b.kwdc_margin_amount,
            "vat_13_percent": b.vat_13_percent,
            "total_monthly_bill": b.total_monthly_bill,
            "status": b.status.value,
            "advance_payment_status": getattr(b, "advance_payment_status", "PAYMENT_DUE") or "PAYMENT_DUE",
            "is_gate_frozen": bool(getattr(b, "is_gate_frozen", False)),
            "is_forfeited": bool(getattr(b, "is_forfeited", False)),
            "days_to_forfeiture": days_left,
            "last_reminder_stage": getattr(b, "last_reminder_stage", None),
            "lien_notifications": notifications,
            "lease_start_date": b.lease_start_date.strftime("%Y-%m-%d") if b.lease_start_date else None,
            "lease_end_date": b.lease_end_date.strftime("%Y-%m-%d") if b.lease_end_date else None,
            "invoice_number": b.invoice.invoice_number if b.invoice else f"KWDC-2083-{b.id:04d}",
            "payment_status": b.invoice.payment_status.value if b.invoice else "unpaid",
            "created_at": b.created_at.strftime("%Y-%m-%d %H:%M")
        })
    return results

@router.post("/bookings/{booking_id}/pay-advance")
def pay_booking_advance(
    booking_id: int,
    payment_method: Optional[str] = "CONNECT_IPS",
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Client pays advance rent or clears overdue arrears (Pay First rule).
    Unfreezes gate passes if previously locked and activates pending space reservations.
    """
    booking = db.query(WarehouseRequest).filter(WarehouseRequest.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.client_id != current_user.id and current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Unauthorized.")
    if getattr(booking, "is_forfeited", False):
        raise HTTPException(status_code=400, detail="This lease was forfeited after 60 days non-payment and moved to auction.")

    now = datetime.now(timezone.utc)
    if booking.invoice:
        booking.invoice.payment_status = PaymentStatus.PAID

    booking.advance_payment_status = "PAID"
    booking.overdue_since = None
    booking.default_countdown_deadline = None
    booking.is_gate_frozen = False
    booking.last_reminder_stage = None

    # Auto-activate if pending
    if booking.status == BookingStatus.PENDING_REVIEW:
        wh = booking.warehouse
        if wh and wh.available_sqft >= booking.allocated_billed_sqft:
            wh.available_sqft = max(0.0, wh.available_sqft - booking.allocated_billed_sqft)
        booking.status = BookingStatus.ACTIVE_LEASED
        booking.lease_start_date = now
        booking.lease_end_date = now + timedelta(days=getattr(booking, "duration_days", 90) or 90)

    db.commit()
    return {
        "message": f"Advance payment confirmed via {payment_method}! Lease #{booking.id} is active and gate clearance unlocked.",
        "booking_id": booking.id,
        "advance_payment_status": "PAID",
        "is_gate_frozen": False,
        "status": booking.status.value
    }

@router.get("/bookings/{booking_id}/contract")
def get_client_booking_contract(
    booking_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    booking = db.query(WarehouseRequest).filter(WarehouseRequest.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.client_id != current_user.id and current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Unauthorized.")
    return generate_client_storage_contract(booking, booking.client or current_user, booking.warehouse)

@router.post("/bookings/{booking_id}/modify")
def modify_booking_lifecycle(
    booking_id: int,
    payload: BookingModifyRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Continuous Sq Ft Lifecycle Management: EXPAND (+sqft), DOWNSIZE (-sqft), or RENEW (+duration).
    """
    booking = db.query(WarehouseRequest).filter(WarehouseRequest.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.client_id != current_user.id and current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Unauthorized.")
    if getattr(booking, "is_forfeited", False):
        raise HTTPException(status_code=400, detail="Cannot modify a forfeited lease.")

    wh = booking.warehouse
    action = payload.action.upper()
    msg = ""

    if action == "EXPAND":
        delta = float(payload.delta_sqft or 0.0)
        if delta <= 0:
            raise HTTPException(status_code=400, detail="Expansion sq ft must be positive.")
        if wh.available_sqft < delta:
            raise HTTPException(status_code=400, detail=f"Only {wh.available_sqft:,.0f} sq ft available to expand.")
        wh.available_sqft = max(0.0, wh.available_sqft - delta)
        booking.requested_sqft += delta
        booking.allocated_billed_sqft += delta
        msg = f"Expanded continuous space by +{delta:,.0f} sq ft (Total: {booking.allocated_billed_sqft:,.0f} sq ft)."
    elif action == "DOWNSIZE":
        delta = float(payload.delta_sqft or 0.0)
        if delta <= 0 or (booking.allocated_billed_sqft - delta) < 100:
            raise HTTPException(status_code=400, detail="Must retain at least 100 sq ft minimum.")
        wh.available_sqft = min(wh.total_sqft, wh.available_sqft + delta)
        booking.requested_sqft -= delta
        booking.allocated_billed_sqft -= delta
        msg = f"Downsized continuous space by -{delta:,.0f} sq ft (Released back to catalog)."
    elif action == "RENEW":
        extra_val = max(1, int(payload.extra_duration_value or 1))
        dtype = (payload.duration_type or booking.booking_duration_type or "MONTHLY").upper()
        extra_days = extra_val if dtype == "DAILY" else (extra_val * 7 if dtype == "WEEKLY" else extra_val * 30)
        booking.duration_days = (booking.duration_days or 90) + extra_days
        if booking.lease_end_date:
            booking.lease_end_date = booking.lease_end_date + timedelta(days=extra_days)
        else:
            booking.lease_end_date = datetime.now(timezone.utc) + timedelta(days=extra_days)
        msg = f"Lease renewed for +{extra_days} days! New expiry: {booking.lease_end_date.strftime('%Y-%m-%d')}."
    else:
        raise HTTPException(status_code=400, detail="Action must be EXPAND, DOWNSIZE, or RENEW.")

    # Recalculate billing for updated sq ft
    calc = calculate_flexible_storage_cost(
        allocated_sqft=booking.allocated_billed_sqft,
        monthly_rate_per_sqft=wh.monthly_rate_per_sqft if wh else 45.0,
        booking_duration_type=booking.booking_duration_type or "MONTHLY",
        duration_value=booking.duration_value or 3
    )
    booking.monthly_base_rent = calc["base_rent"]
    booking.kwdc_margin_amount = calc["kwdc_margin_amount"]
    booking.vat_13_percent = calc["vat_13_percent"]
    booking.total_monthly_bill = calc["total_bill"]
    db.commit()

    return {
        "message": msg,
        "allocated_billed_sqft": booking.allocated_billed_sqft,
        "total_monthly_bill": booking.total_monthly_bill,
        "lease_end_date": booking.lease_end_date.strftime("%Y-%m-%d") if booking.lease_end_date else None
    }

@router.get("/my-inventory")
def get_client_stored_inventory(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Client Stored Inventory & SKU Stock Ledger + Capacity Utilization Gauge.
    """
    items = db.query(StockItem).filter(StockItem.client_id == current_user.id).order_by(StockItem.updated_at.desc()).all()
    bookings = db.query(WarehouseRequest).filter(
        WarehouseRequest.client_id == current_user.id,
        WarehouseRequest.is_forfeited == False
    ).all()

    total_leased_sqft = sum(b.allocated_billed_sqft for b in bookings)
    total_units = sum(i.total_quantity for i in items)
    # Approximate 12 sq ft footprint per pallet/master carton stack for utilization gauge
    est_occupied_sqft = min(total_leased_sqft, round(total_units * 8.5, 1)) if total_leased_sqft > 0 else 0.0
    utilization_pct = round((est_occupied_sqft / total_leased_sqft) * 100, 1) if total_leased_sqft > 0 else 0.0

    ledger = []
    for item in items:
        units_list = [
            {
                "id": u.id,
                "serial": u.serial_or_container_no,
                "qr_hash": u.qr_code_hash,
                "weight_kg": u.gross_weight_kg,
                "status": u.status,
                "bay_location": u.bay_rack_location
            }
            for u in (item.units or [])[:10]
        ]
        ledger.append({
            "id": item.id,
            "sku_code": item.sku_code,
            "item_name": item.item_name,
            "category": item.category,
            "warehouse_id": item.warehouse_id,
            "warehouse_title": item.warehouse.title if item.warehouse else f"Warehouse #{item.warehouse_id}",
            "unit_type": item.unit_type.value if hasattr(item.unit_type, "value") else str(item.unit_type),
            "total_quantity": item.total_quantity,
            "inward_date": item.inward_date.strftime("%Y-%m-%d") if item.inward_date else "Today",
            "sample_units": units_list
        })

    return {
        "summary": {
            "total_leased_sqft": total_leased_sqft,
            "estimated_occupied_sqft": est_occupied_sqft,
            "utilization_percent": utilization_pct,
            "total_skus": len(ledger),
            "total_stored_units": total_units
        },
        "items": ledger
    }

@router.post("/my-inventory")
def log_client_inventory_stock(
    payload: StockItemCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Registers stored SKUs/pallets/cartons with ISO/IEC 18004 QR hashes under client's ledger."""
    sku = (payload.sku_code or f"SKU-{random.randint(10000, 99999)}").strip().upper()
    existing = db.query(StockItem).filter(StockItem.sku_code == sku).first()
    if existing:
        existing.total_quantity += payload.quantity
        item = existing
    else:
        item = StockItem(
            client_id=current_user.id,
            warehouse_id=payload.warehouse_id,
            sku_code=sku,
            item_name=payload.item_name.strip(),
            category=payload.category or "General Merchandise",
            unit_type=payload.unit_type,
            total_quantity=payload.quantity
        )
        db.add(item)
        db.commit()
        db.refresh(item)

    # Create traceable ISO QR unit record representing this batch
    serial = f"{sku}-{random.randint(1000, 9999)}"
    qr_hash = hashlib.sha256(f"{serial}:{current_user.id}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:16].upper()
    unit = InventoryUnit(
        stock_item_id=item.id,
        unit_type=payload.unit_type,
        serial_or_container_no=serial,
        qr_code_hash=f"ISO18004-{qr_hash}",
        gross_weight_kg=payload.gross_weight_kg or 25.0,
        status="IN_STORAGE",
        bay_rack_location=payload.bay_rack_location or "Zone A / Bay-1"
    )
    db.add(unit)
    db.commit()

    return {
        "message": f"Added {payload.quantity} units of '{item.item_name}' (ISO QR: {unit.qr_code_hash}) to your stock ledger.",
        "stock_item_id": item.id,
        "sku_code": item.sku_code,
        "qr_code_hash": unit.qr_code_hash
    }

@router.get("/saved-addresses")
def list_saved_addresses(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    addrs = db.query(ClientSavedAddress).filter(ClientSavedAddress.client_id == current_user.id).order_by(ClientSavedAddress.id.desc()).all()
    return [
        {
            "id": a.id,
            "label": a.label,
            "address": a.address,
            "contact_name": a.contact_name,
            "contact_phone": a.contact_phone,
            "lat": a.lat,
            "lng": a.lng
        }
        for a in addrs
    ]

@router.post("/saved-addresses")
def create_saved_address(
    payload: SavedAddressCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    addr = ClientSavedAddress(
        client_id=current_user.id,
        label=payload.label.strip(),
        address=payload.address.strip(),
        contact_name=payload.contact_name.strip(),
        contact_phone=payload.contact_phone.strip(),
        lat=payload.lat or 27.7172,
        lng=payload.lng or 85.3240
    )
    db.add(addr)
    db.commit()
    db.refresh(addr)
    return {
        "message": f"Saved corridor address '{addr.label}' to your address book.",
        "id": addr.id
    }

@router.delete("/saved-addresses/{addr_id}")
def delete_saved_address(
    addr_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    addr = db.query(ClientSavedAddress).filter(
        ClientSavedAddress.id == addr_id,
        ClientSavedAddress.client_id == current_user.id
    ).first()
    if not addr:
        raise HTTPException(status_code=404, detail="Saved address not found.")
    db.delete(addr)
    db.commit()
    return {"message": "Saved address deleted."}

@router.get("/owner-leases")
def get_owner_active_leases(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Returns active tenant leases across all properties owned by the authenticated owner.
    Privacy Shield: Client personal details are never exposed to the Property Owner.
    """
    warehouses = db.query(Warehouse).filter(Warehouse.owner_id == current_user.id).all()
    warehouse_ids = [w.id for w in warehouses]
    if not warehouse_ids:
        return []
    
    leases = db.query(WarehouseRequest).filter(
        WarehouseRequest.warehouse_id.in_(warehouse_ids)
    ).order_by(WarehouseRequest.created_at.desc()).all()
    
    results = []
    for l in leases:
        results.append({
            "booking_id": l.id,
            "lease_ref": f"KWDC-LEASE-{l.id:04d}",
            "warehouse_title": l.warehouse.title if l.warehouse else "Storage Facility",
            "allocated_sqft": l.allocated_billed_sqft,
            "rate_per_sqft": l.warehouse.monthly_rate_per_sqft if l.warehouse else 45.0,
            "booking_duration_type": getattr(l, "booking_duration_type", "MONTHLY") or "MONTHLY",
            "duration_value": getattr(l, "duration_value", 3) or 3,
            "monthly_rent_disbursement": l.monthly_base_rent,
            "lease_start_date": l.lease_start_date.strftime("%Y-%m-%d") if l.lease_start_date else "Pending Activation",
            "lease_end_date": l.lease_end_date.strftime("%Y-%m-%d") if l.lease_end_date else "-",
            "status": l.status.value
        })
    return results

@router.get("/my-payouts")
def get_owner_payout_statements(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Returns rental payout statements for the authenticated property owner across DAILY, WEEKLY & MONTHLY leases:
    - Gross Base Rent
    - 10% KWDC Platform Commission
    - 10% Nepal House Rent TDS (Bahal Kar per Income Tax Act 2058)
    - Net Direct Bank Deposit
    """
    warehouses = db.query(Warehouse).filter(Warehouse.owner_id == current_user.id).all()
    warehouse_ids = [w.id for w in warehouses]
    if not warehouse_ids:
        return []

    leases = db.query(WarehouseRequest).filter(
        WarehouseRequest.warehouse_id.in_(warehouse_ids)
    ).order_by(WarehouseRequest.created_at.desc()).all()

    results = []
    for l in leases:
        gross_rent = round(float(l.monthly_base_rent or 0.0), 2)
        margin_fee = round(gross_rent * 0.10, 2)
        owner_share_90pct = round(gross_rent - margin_fee, 2)
        tds_10pct = round(gross_rent * 0.10, 2)
        net_bank_deposit = round(owner_share_90pct - tds_10pct, 2)
        is_paid = l.invoice and l.invoice.payment_status == PaymentStatus.PAID
        results.append({
            "lease_number": f"KWDC-LEASE-{l.id:04d}",
            "tds_certificate_number": f"TDS-2083-{l.id:04d}",
            "warehouse_title": l.warehouse.title if l.warehouse else "Storage Facility",
            "booking_duration_type": getattr(l, "booking_duration_type", "MONTHLY") or "MONTHLY",
            "allocated_sqft": l.allocated_billed_sqft,
            "monthly_gross_rent": gross_rent,
            "platform_fee_10pct": margin_fee,
            "net_payout_90pct": owner_share_90pct,
            "tds_10pct": tds_10pct,
            "net_bank_deposit_npr": net_bank_deposit,
            "payout_status": "DISBURSED" if is_paid else "SCHEDULED_EOM",
            "settlement_channel": "ConnectIPS / NCHL Bank Wire",
            "created_at": l.created_at.strftime("%Y-%m-%d")
        })
    return results


@router.get("/{warehouse_id}/owner-contract")
def get_owner_executed_contract(
    warehouse_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Returns the digitally executed Master Commercial Real Estate Agreement (KWDC-MLA-2083-XXXX)."""
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found.")
    if warehouse.owner_id != current_user.id and current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Unauthorized.")
    return generate_master_lease_contract(warehouse=warehouse, owner=warehouse.owner or current_user)


@router.post("/{warehouse_id}/change-request")
def submit_owner_change_request(
    warehouse_id: int,
    payload: OwnerChangeRequestCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Sanctioned workflow for approved properties locked by Admin Governance:
    - DELISTING_15_DAYS: Formal 15-day notice to delist unleased space.
    - RATE_REVISION: Request tariff adjustment for Admin review.
    """
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found.")
    if warehouse.owner_id != current_user.id and current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Unauthorized.")

    rtype = payload.request_type.upper()
    if rtype not in ("DELISTING_15_DAYS", "RATE_REVISION"):
        raise HTTPException(status_code=400, detail="request_type must be 'DELISTING_15_DAYS' or 'RATE_REVISION'.")

    if rtype == "DELISTING_15_DAYS" and (warehouse.total_sqft - warehouse.available_sqft) > 0:
        raise HTTPException(status_code=400, detail="Cannot delist facility while commercial tenant leases are active.")

    req = WarehouseChangeRequest(
        warehouse_id=warehouse.id,
        owner_id=current_user.id,
        request_type=rtype,
        requested_rate_per_sqft=payload.requested_rate_per_sqft,
        reason_note=payload.reason_note.strip(),
        status="PENDING_REVIEW"
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    return {
        "message": f"Formal {rtype.replace('_', ' ')} request #{req.id} submitted to SuperAdmin for review.",
        "request_id": req.id,
        "status": req.status
    }


@router.get("/owner-facility-health")
def get_owner_facility_health_feed(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Anonymized Incharge Shift Logs & Incident Reports for the Property Owner's facilities.
    Privacy Shield: Exposes structural health & safety audits without leaking tenant identities.
    """
    warehouses = db.query(Warehouse).filter(Warehouse.owner_id == current_user.id).all()
    warehouse_ids = [w.id for w in warehouses]
    if not warehouse_ids:
        return {"activity_logs": [], "incidents": []}

    logs = db.query(WarehouseActivityLog).filter(
        WarehouseActivityLog.warehouse_id.in_(warehouse_ids)
    ).order_by(WarehouseActivityLog.created_at.desc()).limit(30).all()

    incidents = db.query(IncidentReport).filter(
        IncidentReport.warehouse_id.in_(warehouse_ids)
    ).order_by(IncidentReport.created_at.desc()).limit(30).all()

    return {
        "activity_logs": [
            {
                "id": l.id,
                "warehouse_title": l.warehouse.title if l.warehouse else f"Warehouse #{l.warehouse_id}",
                "log_type": l.log_type,
                "summary": l.summary,
                "detailed_notes": l.detailed_notes,
                "created_at": l.created_at.strftime("%Y-%m-%d %H:%M") if l.created_at else ""
            }
            for l in logs
        ],
        "incidents": [
            {
                "id": i.id,
                "warehouse_title": i.warehouse.title if i.warehouse else f"Warehouse #{i.warehouse_id}",
                "category": i.incident_category,
                "severity": i.severity.value if hasattr(i.severity, "value") else str(i.severity),
                "description": i.description,
                "action_taken": i.action_taken or "Audited by Facility Incharge",
                "created_at": i.created_at.strftime("%Y-%m-%d %H:%M") if i.created_at else ""
            }
            for i in incidents
        ]
    }
