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
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
from backend.database import get_db
from backend.models import (
    Warehouse, WarehouseRequest, WarehousePhoto, User, UserRole,
    BookingStatus, SpaceType, AreaUnit, TaxInvoice, PaymentStatus
)
from backend.schemas import WarehouseCreate, MaintenanceHoldRequest, BookingRequestCreate
from backend.auth_utils import require_user, get_current_user
from backend.services.unit_converter import to_sqft, from_sqft_to_all, get_warehouse_usable_capacity
from backend.services.vat_service import generate_ird_tax_invoice
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
        results.append({
            "id": w.id,
            "title": w.title,
            "space_type": w.space_type.value,
            "total_sqft": w.total_sqft,
            "available_sqft": w.available_sqft,
            "monthly_rate_per_sqft": w.monthly_rate_per_sqft,
            "base_rate_per_sqft": w.monthly_rate_per_sqft,
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
            "contract_executed": bool(w.lease_contract_url)
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

@router.post("/book")
def book_warehouse_space(
    payload: BookingRequestCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Client books commercial storage:
    - Billed directly on requested square footage.
    - Generates IRD Schedule 13 Tax Invoice with 13% statutory VAT.
    - Status set to PENDING_REVIEW for Admin approval.
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

    # Direct Billed Allocation
    allocated_sqft = payload.requested_sqft

    # Base Rent + KWDC Margin (10%) + 13% IRD VAT
    monthly_base_rent = round(allocated_sqft * warehouse.monthly_rate_per_sqft, 2)
    kwdc_margin_amount = round(monthly_base_rent * 0.10, 2)
    taxable_amount = monthly_base_rent + kwdc_margin_amount
    vat_13_percent = round(taxable_amount * 0.13, 2)
    total_monthly_bill = round(taxable_amount + vat_13_percent, 2)

    booking = WarehouseRequest(
        client_id=current_user.id,
        warehouse_id=warehouse.id,
        requested_sqft=payload.requested_sqft,
        allocated_billed_sqft=allocated_sqft,
        monthly_base_rent=monthly_base_rent,
        kwdc_margin_amount=kwdc_margin_amount,
        vat_13_percent=vat_13_percent,
        total_monthly_bill=total_monthly_bill,
        status=BookingStatus.PENDING_REVIEW
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Create IRD Schedule 13 Invoice
    inv_number = f"KWDC-2083-{booking.id:04d}"
    inv_data = generate_ird_tax_invoice(
        invoice_number=inv_number,
        buyer_name=current_user.full_name,
        buyer_pan=payload.buyer_pan,
        service_type="STORAGE_RESERVATION",
        base_tariff=monthly_base_rent,
        margin_percent=0.10
    )

    invoice = TaxInvoice(
        invoice_number=inv_number,
        storage_booking_id=booking.id,
        buyer_name=current_user.full_name,
        buyer_pan_vat=payload.buyer_pan,
        taxable_base_amount=inv_data["taxable_amount"],
        kwdc_admin_margin=inv_data["kwdc_admin_margin"],
        vat_13_percent=inv_data["vat_13_percent"],
        gross_total_npr=inv_data["gross_total_npr"],
        qr_payload=inv_data["qr_payload"],
        payment_status=PaymentStatus.UNPAID
    )
    db.add(invoice)
    db.commit()

    return {
        "message": "Storage booking request submitted for Admin verification!",
        "booking_id": booking.id,
        "requested_sqft": payload.requested_sqft,
        "allocated_billed_sqft": allocated_sqft,
        "monthly_base_rent_npr": monthly_base_rent,
        "kwdc_margin_npr": kwdc_margin_amount,
        "vat_13_percent_npr": vat_13_percent,
        "gross_monthly_total_npr": total_monthly_bill,
        "invoice_number": inv_number,
        "qr_data_uri": inv_data["qr_data_uri"],
        "status": "PENDING_ADMIN_ACTIVATION"
    }

@router.get("/my-bookings")
def get_client_bookings(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Returns all storage reservations and active leases for the authenticated commercial client.
    """
    bookings = db.query(WarehouseRequest).filter(WarehouseRequest.client_id == current_user.id).order_by(WarehouseRequest.created_at.desc()).all()
    results = []
    for b in bookings:
        results.append({
            "id": b.id,
            "warehouse_id": b.warehouse_id,
            "warehouse_title": b.warehouse.title if b.warehouse else "KTM Commercial Storage",
            "neighborhood_landmark": b.warehouse.neighborhood_landmark if b.warehouse else "Kathmandu",
            "district": b.warehouse.district if b.warehouse else "Kathmandu",
            "requested_sqft": b.requested_sqft,
            "allocated_billed_sqft": b.allocated_billed_sqft,
            "monthly_base_rent": b.monthly_base_rent,
            "kwdc_margin_amount": b.kwdc_margin_amount,
            "vat_13_percent": b.vat_13_percent,
            "total_monthly_bill": b.total_monthly_bill,
            "status": b.status.value,
            "lease_start_date": b.lease_start_date.strftime("%Y-%m-%d") if b.lease_start_date else None,
            "lease_end_date": b.lease_end_date.strftime("%Y-%m-%d") if b.lease_end_date else None,
            "invoice_number": b.invoice.invoice_number if b.invoice else f"KWDC-2083-{b.id:04d}",
            "payment_status": b.invoice.payment_status.value if b.invoice else "unpaid",
            "created_at": b.created_at.strftime("%Y-%m-%d %H:%M")
        })
    return results

@router.get("/owner-leases")
def get_owner_active_leases(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Returns active tenant leases across all properties owned by the authenticated owner.
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
            "warehouse_title": l.warehouse.title if l.warehouse else "Storage Facility",
            "allocated_sqft": l.allocated_billed_sqft,
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
    Returns monthly rental payout statements for the authenticated property owner.
    90% Net disbursement after deducting 10% KWDC platform margin.
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
        gross_rent = l.monthly_base_rent or 0.0
        margin_fee = round(gross_rent * 0.10, 2)
        net_owner_payout = round(gross_rent - margin_fee, 2)
        is_paid = l.invoice and l.invoice.payment_status == PaymentStatus.PAID
        results.append({
            "lease_number": f"KWDC-LEASE-{l.id:04d}",
            "warehouse_title": l.warehouse.title if l.warehouse else "Storage Facility",
            "allocated_sqft": l.allocated_billed_sqft,
            "monthly_gross_rent": gross_rent,
            "platform_fee_10pct": margin_fee,
            "net_payout_90pct": net_owner_payout,
            "payout_status": "DISBURSED" if is_paid else "SCHEDULED_EOM",
            "settlement_channel": "ConnectIPS / Direct Bank",
            "created_at": l.created_at.strftime("%Y-%m-%d")
        })
    return results
