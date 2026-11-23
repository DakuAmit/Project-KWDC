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
    normalized_sqft = to_sqft(payload.input_value, payload.input_unit.value, payload.ceiling_height_ft)

    new_warehouse = Warehouse(
        owner_id=current_user.id,
        title=payload.title,
        space_type=payload.space_type,
        total_sqft=normalized_sqft,
        available_sqft=normalized_sqft,
        clear_ceiling_height_ft=payload.ceiling_height_ft,
        original_input_unit=payload.input_unit,
        original_input_value=payload.input_value,
        monthly_rate_per_sqft=payload.monthly_rate_per_sqft,
        min_lease_months=payload.min_lease_months,
        province=payload.province,
        district=payload.district,
        municipality=payload.municipality,
        ward_no=payload.ward_no,
        neighborhood_landmark=payload.neighborhood_landmark,
        latitude=payload.latitude,
        longitude=payload.longitude,
        road_access_ft=payload.road_access_ft,
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

@router.get("/catalog")
def get_public_catalog(
    space_type: Optional[str] = None,
    min_sqft: Optional[float] = None,
    cold_storage_only: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """
    Public Catalog enforcing:
    1. Only approved and active spaces shown.
    2. Privacy Shield: Owner identities masked.
    """
    query = db.query(Warehouse).filter(
        Warehouse.is_approved == True,
        Warehouse.is_available == True,
        Warehouse.is_on_maintenance_hold == False
    )

    if space_type:
        query = query.filter(Warehouse.space_type == space_type)
    if min_sqft:
        query = query.filter(Warehouse.available_sqft >= min_sqft)
    if cold_storage_only:
        query = query.filter(Warehouse.has_cold_storage == True)

    warehouses = query.all()
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
            "district": w.district,
            "municipality": w.municipality,
            "neighborhood_landmark": w.neighborhood_landmark,
            "latitude": w.latitude,
            "longitude": w.longitude,
            "road_access_ft": w.road_access_ft,
            "has_three_phase_power": w.has_three_phase_power,
            "has_forklift_ramp": w.has_forklift_ramp,
            "has_cctv": w.has_cctv,
            "has_cold_storage": w.has_cold_storage,
            "units": units,
            "privacy_shield_note": "Direct owner contact is protected. KTM-WDC acts as your verified corporate counterparty."
        })
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
