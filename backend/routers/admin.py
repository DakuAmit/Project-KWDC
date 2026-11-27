"""
SuperAdmin Master Operations & Governance Router for KTM-WDC
Governs:
1. Auditing & Approving Property Listings (Lockout Rule enforcement)
2. Executing & Emailing Master Commercial Contracts via Brevo
3. Post-Approval Governance & Feature Overrides
4. Client Booking Activation (Starting Owner Cashflow)
5. Warehouse Incharge Staff Provisioning & Management (Internal staff under Admin)
6. Reviewing Facility Incharge Logs & Gate Pass Operations
7. Live Fleet Telemetry Radar (Central Dispatch Stream)
8. Space Owner Monthly Disbursements & Commission Settlement (90% Owner / 10% KWDC)
9. Maintenance Hold & Space Freeze Manager
10. Platform User Directory, RBAC & KYC Governance
"""
import random
import string
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db, get_db_info
from backend.models import (
    Warehouse, WarehouseRequest, User, UserRole,
    BookingStatus, TaxInvoice, PaymentStatus, WarehouseActivityLog,
    WarehouseInchargeAssignment, KycStatus, Vehicle, Driver, GatePass, IncidentReport, UserKycProfile,
    PlatformConfig, StockAuctionItem, LienNotificationLog, WarehouseChangeRequest, PhysicalAuditStatus,
    SmsOutboxLog, SecurityAgency, StockItem
)
from backend.auth_utils import require_user, require_roles, get_password_hash
from backend.services.sms_service import get_sms_provider_mode
from backend.services.contract_service import generate_master_lease_contract
from backend.services.email_service import send_contract_approval_email, send_otp_email
from backend.services.fare_service import get_platform_config, calculate_freight_benchmark
from backend.services.overdue_monitor import push_lien_notification, execute_stock_forfeiture_and_auction, run_overdue_sweep

router = APIRouter(prefix="/api/admin", tags=["SuperAdmin Governance"])

# ---------------------------------------------------------------------------
# Pydantic Request Models
# ---------------------------------------------------------------------------
class InchargeProvisionRequest(BaseModel):
    full_name: str
    email: str
    phone_number: str
    warehouse_id: Optional[int] = None
    password: Optional[str] = None

class InchargeReassignRequest(BaseModel):
    warehouse_id: int

class PayoutDisburseRequest(BaseModel):
    transaction_ref: str
    payment_method: str = "CONNECT_IPS"

class MaintenanceActionRequest(BaseModel):
    action: str  # "APPROVE" or "RELEASE"
    admin_notes: Optional[str] = None

class UserStatusUpdateRequest(BaseModel):
    is_active: bool

class UserKycUpdateRequest(BaseModel):
    kyc_status: str
    admin_notes: Optional[str] = None

class AssignInchargeAuditRequest(BaseModel):
    incharge_id: int
    notes: Optional[str] = None

class WarehouseTariffUpdateRequest(BaseModel):
    client_rate_per_sqft: float
    owner_rate_per_sqft: Optional[float] = None
    notes: Optional[str] = None

class FareConfigUpdateRequest(BaseModel):
    platform_margin_percent: Optional[float] = 10.0
    flag_drop_van_pickup: Optional[float] = 1200.0
    flag_drop_mini_truck: Optional[float] = 1800.0
    flag_drop_heavy_truck: Optional[float] = 3200.0
    flag_drop_container_trailer: Optional[float] = 5000.0
    rate_per_km_van_pickup: Optional[float] = 65.0
    rate_per_km_mini_truck: Optional[float] = 85.0
    rate_per_km_heavy_truck: Optional[float] = 125.0
    rate_per_km_container_trailer: Optional[float] = 175.0
    weight_rate_per_tonne: Optional[float] = 150.0
    vat_rate_percent: Optional[float] = 0.0
    fuel_multiplier: Optional[float] = 1.0


# ---------------------------------------------------------------------------
# 1. PROPERTY AUDITS & APPROVALS (RULE 1: PHYSICAL AUDIT & LOCKOUT)
# ---------------------------------------------------------------------------
@router.get("/pending-warehouses")
@router.get("/pending")
def get_pending_warehouses(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Lists all properties awaiting SuperAdmin / Incharge inspection & approval."""
    pending = db.query(Warehouse).filter(Warehouse.is_approved == False).order_by(Warehouse.created_at.desc()).all()
    results = []
    for w in pending:
        auditor = w.incharge_auditor or (
            db.query(User).filter(User.id == w.audited_by_incharge_id).first()
            if getattr(w, "audited_by_incharge_id", None) else None
        )
        client_rate = float(w.client_rate_per_sqft if getattr(w, "client_rate_per_sqft", None) is not None else w.monthly_rate_per_sqft)
        results.append({
            "id": w.id,
            "owner_name": w.owner.full_name if w.owner else "Property Owner",
            "owner_email": w.owner.email if w.owner else "-",
            "owner_phone": w.owner.phone_number if w.owner else "-",
            "title": w.title,
            "space_type": w.space_type.value if hasattr(w.space_type, "value") else str(w.space_type),
            "total_sqft": w.total_sqft,
            "monthly_rate_per_sqft": w.monthly_rate_per_sqft,
            "owner_rate_per_sqft": w.monthly_rate_per_sqft,
            "client_rate_per_sqft": client_rate,
            "neighborhood_landmark": w.neighborhood_landmark,
            "district": w.district,
            "latitude": w.latitude,
            "longitude": w.longitude,
            "road_access_ft": w.road_access_ft,
            "physical_audit_status": w.physical_audit_status.value if hasattr(w.physical_audit_status, "value") else str(w.physical_audit_status or "PENDING_INSPECTION"),
            "assigned_incharge_id": getattr(w, "audited_by_incharge_id", None),
            "assigned_incharge_name": auditor.full_name if auditor else None,
            "is_on_maintenance_hold": bool(w.is_on_maintenance_hold),
            "photos": [p.photo_url for p in (w.photos or []) if p.photo_url],
            "video_urls": [v.strip() for v in (getattr(w, "video_urls", None) or "").split(",") if v.strip()],
            "created_at": w.created_at.strftime("%Y-%m-%d %H:%M") if w.created_at else "Recent"
        })
    return results


@router.get("/warehouses")
def get_all_admin_warehouses(
    status_filter: Optional[str] = None,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    Lists ALL registered warehouses across the platform with operational status tags,
    occupancy metrics, Owner Rate vs Client Base Tariff, and assigned Incharge details.
    """
    all_wh = db.query(Warehouse).order_by(Warehouse.created_at.desc()).all()
    results = []
    for w in all_wh:
        tot = float(w.total_sqft or 0.0)
        avail = float(w.available_sqft or 0.0)
        occ = round(max(0.0, tot - avail), 2)
        occ_pct = round((occ / tot) * 100.0, 1) if tot > 0 else 0.0
        owner_rate = float(w.monthly_rate_per_sqft or 45.0)
        client_rate = float(w.client_rate_per_sqft if getattr(w, "client_rate_per_sqft", None) is not None else owner_rate)

        auditor = w.incharge_auditor or (
            db.query(User).filter(User.id == w.audited_by_incharge_id).first()
            if getattr(w, "audited_by_incharge_id", None) else None
        )
        if not auditor:
            active_assign = db.query(WarehouseInchargeAssignment).filter(
                WarehouseInchargeAssignment.warehouse_id == w.id,
                WarehouseInchargeAssignment.is_active == True
            ).first()
            if active_assign and active_assign.incharge:
                auditor = active_assign.incharge

        tags = []
        if w.is_approved:
            tags.append("verified")
        else:
            tags.append("pending_audit")
        if occ > 0:
            tags.append("on_lease")
        else:
            tags.append("empty")
        if w.is_on_maintenance_hold:
            tags.append("on_hold")

        if status_filter and status_filter != "all" and status_filter not in tags:
            continue

        results.append({
            "id": w.id,
            "title": w.title,
            "owner_name": w.owner.full_name if w.owner else "Property Owner",
            "owner_phone": w.owner.phone_number if w.owner else "-",
            "space_type": w.space_type.value if hasattr(w.space_type, "value") else str(w.space_type),
            "district": w.district,
            "neighborhood_landmark": w.neighborhood_landmark,
            "total_sqft": tot,
            "available_sqft": avail,
            "occupied_sqft": occ,
            "occupancy_percent": occ_pct,
            "owner_rate_per_sqft": owner_rate,
            "client_rate_per_sqft": client_rate,
            "is_approved": bool(w.is_approved),
            "is_available": bool(w.is_available),
            "is_on_maintenance_hold": bool(w.is_on_maintenance_hold),
            "hold_reason_note": w.hold_reason_note,
            "physical_audit_status": w.physical_audit_status.value if hasattr(w.physical_audit_status, "value") else str(w.physical_audit_status or "PENDING_INSPECTION"),
            "assigned_incharge_id": auditor.id if auditor else None,
            "assigned_incharge_name": auditor.full_name if auditor else None,
            "status_tags": tags,
            "photos": [p.photo_url for p in (w.photos or []) if p.photo_url],
            "video_urls": [v.strip() for v in (getattr(w, "video_urls", None) or "").split(",") if v.strip()],
            "created_at": w.created_at.strftime("%Y-%m-%d %H:%M") if w.created_at else "Recent"
        })
    return results


@router.post("/warehouses/{warehouse_id}/assign-incharge")
def assign_incharge_for_inspection(
    warehouse_id: int,
    payload: AssignInchargeAuditRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Assigns a Warehouse Incharge staff member to inspect a property before final approval."""
    wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Warehouse not found.")

    inc = db.query(User).filter(
        User.id == payload.incharge_id,
        User.role == UserRole.WAREHOUSE_INCHARGE
    ).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Warehouse Incharge staff member not found.")

    existing = db.query(WarehouseInchargeAssignment).filter(
        WarehouseInchargeAssignment.warehouse_id == wh.id,
        WarehouseInchargeAssignment.incharge_id == inc.id,
        WarehouseInchargeAssignment.is_active == True
    ).first()
    if not existing:
        db.add(WarehouseInchargeAssignment(
            warehouse_id=wh.id,
            incharge_id=inc.id,
            is_active=True
        ))

    wh.audited_by_incharge_id = inc.id
    if not wh.is_approved:
        wh.physical_audit_status = PhysicalAuditStatus.AUDIT_SCHEDULED
    if payload.notes:
        wh.physical_audit_notes = payload.notes.strip()

    db.add(WarehouseActivityLog(
        warehouse_id=wh.id,
        incharge_id=inc.id,
        log_type="PHYSICAL_INSPECTION_ASSIGNED",
        summary=f"Assigned {inc.full_name} for on-site physical audit of {wh.title}",
        detailed_notes=payload.notes or "SuperAdmin dispatched on-site inspector to verify area, access road & fire safety."
    ))
    db.commit()
    return {
        "message": f"Assigned '{inc.full_name}' to inspect '{wh.title}'.",
        "warehouse_id": wh.id,
        "incharge_id": inc.id,
        "incharge_name": inc.full_name,
        "physical_audit_status": wh.physical_audit_status.value
    }


@router.post("/warehouses/{warehouse_id}/set-tariff")
def set_warehouse_client_tariff(
    warehouse_id: int,
    payload: WarehouseTariffUpdateRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    Allows SuperAdmin to set the Client-facing Base Tariff Rate independently
    from the Property Owner's base rate (without reducing Owner payouts).
    """
    wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Warehouse not found.")
    if payload.client_rate_per_sqft < 5:
        raise HTTPException(status_code=400, detail="Client base tariff must be at least Rs. 5/sq ft.")

    wh.client_rate_per_sqft = round(float(payload.client_rate_per_sqft), 2)
    if payload.owner_rate_per_sqft is not None and payload.owner_rate_per_sqft >= 5:
        wh.monthly_rate_per_sqft = round(float(payload.owner_rate_per_sqft), 2)

    db.commit()
    return {
        "message": f"Updated '{wh.title}' — Client Tariff: Rs. {wh.client_rate_per_sqft}/sqft (Owner Rate: Rs. {wh.monthly_rate_per_sqft}/sqft).",
        "warehouse_id": wh.id,
        "client_rate_per_sqft": wh.client_rate_per_sqft,
        "owner_rate_per_sqft": wh.monthly_rate_per_sqft
    }

@router.post("/warehouses/{warehouse_id}/approve")
@router.post("/warehouses/{warehouse_id}/audit")
def approve_warehouse_listing(
    warehouse_id: int,
    payload: dict = None,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    SuperAdmin signs off on the physical audit.
    Generates Master Commercial Lease PDF, records the physical lockout, and sends email.
    """
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found.")

    if warehouse.is_approved:
        return {"message": "Warehouse is already approved."}

    # Generate master commercial contract
    owner = warehouse.owner or db.query(User).filter(User.id == warehouse.owner_id).first()
    contract_data = generate_master_lease_contract(warehouse, owner) if owner else {}
    contract_url = contract_data.get("contract_number", f"KWDC-MLA-2083-{warehouse.id:04d}")

    # Approve & Lock
    warehouse.is_approved = True
    warehouse.is_available = True
    warehouse.physical_lockout_enforced = True
    warehouse.lease_contract_url = contract_url
    db.commit()

    # Send Notification Email
    if owner:
        email_sent = send_contract_approval_email(
            to_email=owner.email,
            owner_name=owner.full_name,
            warehouse_title=warehouse.title,
            contract_url=contract_url
        )

    return {
        "message": f"Warehouse '{warehouse.title}' successfully audited and approved!",
        "warehouse_id": warehouse.id,
        "contract_url": contract_url,
        "email_dispatched": email_sent,
        "physical_lockout_enforced": True
    }

@router.put("/warehouses/{warehouse_id}/admin-override")
def admin_override_features(
    warehouse_id: int,
    total_sqft: Optional[float] = None,
    monthly_rate: Optional[float] = None,
    three_phase: Optional[bool] = None,
    forklift_ramp: Optional[bool] = None,
    cctv: Optional[bool] = None,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """SuperAdmin feature override."""
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found.")

    if total_sqft is not None:
        diff = total_sqft - warehouse.total_sqft
        warehouse.total_sqft = total_sqft
        warehouse.available_sqft = max(0.0, warehouse.available_sqft + diff)
    if monthly_rate is not None:
        warehouse.monthly_rate_per_sqft = monthly_rate
    if three_phase is not None:
        warehouse.has_three_phase_power = three_phase
    if forklift_ramp is not None:
        warehouse.has_forklift_ramp = forklift_ramp
    if cctv is not None:
        warehouse.has_cctv = cctv

    db.commit()
    return {
        "message": "Warehouse specifications updated successfully.",
        "warehouse_id": warehouse.id,
        "total_sqft": warehouse.total_sqft,
        "available_sqft": warehouse.available_sqft,
        "monthly_rate_per_sqft": warehouse.monthly_rate_per_sqft
    }


# ---------------------------------------------------------------------------
# 2. CLIENT LEASES & ACTIVATION (CONTINUOUS SQ FT CONTRACTING)
# ---------------------------------------------------------------------------
@router.get("/bookings")
def get_all_bookings(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Lists all client booking requests and active tenancies."""
    bookings = db.query(WarehouseRequest).order_by(WarehouseRequest.created_at.desc()).all()
    results = []
    for b in bookings:
        results.append({
            "id": b.id,
            "client_name": b.client.full_name,
            "client_email": b.client.email,
            "client_phone": b.client.phone_number,
            "warehouse_title": b.warehouse.title,
            "warehouse_id": b.warehouse_id,
            "requested_sqft": b.requested_sqft,
            "allocated_billed_sqft": b.allocated_billed_sqft,
            "monthly_base_rent": b.monthly_base_rent,
            "kwdc_margin_amount": b.kwdc_margin_amount,
            "vat_13_percent": b.vat_13_percent,
            "total_monthly_bill": b.total_monthly_bill,
            "status": b.status.value,
            "created_at": b.created_at.strftime("%Y-%m-%d %H:%M")
        })
    return results

@router.post("/bookings/{booking_id}/activate")
def activate_booking(
    booking_id: int,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    SuperAdmin verifies client payment and activates the storage tenancy:
    - Deducts contracted continuous sq ft from available capacity.
    - Sets lease start and end dates.
    - Triggers owner disbursement eligibility.
    """
    booking = db.query(WarehouseRequest).filter(WarehouseRequest.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking request not found.")

    if booking.status in (BookingStatus.ACTIVE_LEASED, BookingStatus.APPROVED_CONTRACT_DISPATCHED):
        return {"message": "Booking is already active."}

    warehouse = booking.warehouse
    if warehouse.available_sqft < booking.allocated_billed_sqft:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot activate: only {warehouse.available_sqft:,.2f} sq ft available."
        )

    # Deduct continuous square footage
    warehouse.available_sqft = max(0.0, warehouse.available_sqft - booking.allocated_billed_sqft)

    booking.status = BookingStatus.ACTIVE_LEASED
    now = datetime.now(timezone.utc)
    booking.lease_start_date = now
    booking.lease_end_date = now + timedelta(days=getattr(booking, "duration_days", 90) or 365)
    booking.advance_payment_status = "PAID"
    booking.is_gate_frozen = False

    if booking.invoice:
        booking.invoice.payment_status = PaymentStatus.PAID

    db.commit()

    return {
        "message": f"Booking #{booking.id} activated! {booking.allocated_billed_sqft:,.2f} sq ft leased.",
        "warehouse_available_sqft": warehouse.available_sqft,
        "status": "ACTIVE",
        "lease_start": booking.lease_start_date.strftime("%Y-%m-%d"),
        "lease_end": booking.lease_end_date.strftime("%Y-%m-%d")
    }


# ---------------------------------------------------------------------------
# 3. WAREHOUSE INCHARGE PROVISIONING & STAFF MANAGEMENT
# (Staff accounts created & provisioned by Admin and issued to Incharge)
# ---------------------------------------------------------------------------
@router.get("/incharges")
def get_all_incharges(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    Returns all Warehouse Incharge staff accounts provisioned by SuperAdmin,
    along with their assigned facility names and operational activity metrics.
    """
    incharges = db.query(User).filter(User.role == UserRole.WAREHOUSE_INCHARGE).order_by(User.created_at.desc()).all()
    results = []
    for inc in incharges:
        assignment = db.query(WarehouseInchargeAssignment).filter(
            WarehouseInchargeAssignment.incharge_id == inc.id,
            WarehouseInchargeAssignment.is_active == True
        ).first()

        assigned_warehouse_id = assignment.warehouse_id if assignment else None
        assigned_warehouse_title = assignment.warehouse.title if (assignment and assignment.warehouse) else "Unassigned / Roaming"
        assigned_date = assignment.assigned_date.strftime("%Y-%m-%d") if assignment else None
        logs_count = db.query(WarehouseActivityLog).filter(WarehouseActivityLog.incharge_id == inc.id).count()

        results.append({
            "id": inc.id,
            "full_name": inc.full_name,
            "email": inc.email,
            "phone_number": inc.phone_number,
            "is_active": inc.is_active,
            "is_verified": inc.is_verified,
            "kyc_status": inc.kyc_status.value,
            "assigned_warehouse_id": assigned_warehouse_id,
            "assigned_warehouse_title": assigned_warehouse_title,
            "assigned_date": assigned_date,
            "logs_count": logs_count,
            "created_at": inc.created_at.strftime("%Y-%m-%d %H:%M")
        })
    return results

@router.post("/incharges")
def provision_incharge_staff(
    payload: InchargeProvisionRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    SuperAdmin provisions a new Warehouse Incharge staff account:
    - Creates staff user with WAREHOUSE_INCHARGE role.
    - Assigns to specific warehouse facility.
    - Generates or sets temporary password.
    - Pre-verifies account (is_active=True, is_verified=True, kyc_status=APPROVED).
    - Returns credentials bundle for immediate sharing to incharge via SMS/WhatsApp/Email.
    """
    email_clean = payload.email.strip().lower()
    phone_clean = payload.phone_number.strip()

    if db.query(User).filter(User.email == email_clean).first():
        raise HTTPException(status_code=400, detail="A staff user with this email address already exists.")

    if db.query(User).filter(User.phone_number == phone_clean).first():
        raise HTTPException(status_code=400, detail="A staff user with this mobile number already exists.")

    warehouse = None
    if payload.warehouse_id:
        warehouse = db.query(Warehouse).filter(Warehouse.id == payload.warehouse_id).first()
        if not warehouse:
            raise HTTPException(status_code=404, detail="Selected warehouse facility does not exist.")

    # Determine password
    raw_password = payload.password.strip() if payload.password and payload.password.strip() else f"KTMwdc@{random.randint(1000, 9999)}"

    incharge_user = User(
        email=email_clean,
        phone_number=phone_clean,
        full_name=payload.full_name.strip(),
        company_name="KTM-WDC Facility Operations",
        operating_location=(warehouse.district or "Kathmandu") if warehouse else "Kathmandu Valley",
        hashed_password=get_password_hash(raw_password),
        role=UserRole.WAREHOUSE_INCHARGE,
        is_active=True,
        is_verified=True,
        kyc_status=KycStatus.VERIFIED
    )
    db.add(incharge_user)
    db.commit()
    db.refresh(incharge_user)

    if warehouse:
        assignment = WarehouseInchargeAssignment(
            incharge_id=incharge_user.id,
            warehouse_id=warehouse.id,
            is_active=True
        )
        db.add(assignment)
        db.commit()

    return {
        "message": f"Warehouse Incharge '{incharge_user.full_name}' provisioned successfully!",
        "incharge_id": incharge_user.id,
        "full_name": incharge_user.full_name,
        "email": incharge_user.email,
        "phone_number": incharge_user.phone_number,
        "temporary_password": raw_password,
        "assigned_facility_id": warehouse.id if warehouse else None,
        "assigned_facility_name": warehouse.title if warehouse else "Unassigned (Assign via Property Audits)",
        "login_portal_url": "https://ktmwdc.vercel.app/login"
    }

@router.put("/incharges/{incharge_id}/reassign")
def reassign_incharge_facility(
    incharge_id: int,
    payload: InchargeReassignRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    inc = db.query(User).filter(User.id == incharge_id, User.role == UserRole.WAREHOUSE_INCHARGE).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incharge staff member not found.")

    warehouse = db.query(Warehouse).filter(Warehouse.id == payload.warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Selected warehouse facility not found.")

    # Deactivate previous active assignments
    db.query(WarehouseInchargeAssignment).filter(
        WarehouseInchargeAssignment.incharge_id == inc.id
    ).update({"is_active": False})

    # Create new active assignment
    new_assign = WarehouseInchargeAssignment(
        incharge_id=inc.id,
        warehouse_id=warehouse.id,
        is_active=True
    )
    db.add(new_assign)
    db.commit()

    return {"message": f"Staff '{inc.full_name}' reassigned to '{warehouse.title}' successfully."}

@router.put("/incharges/{incharge_id}/status")
def toggle_incharge_status(
    incharge_id: int,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    inc = db.query(User).filter(User.id == incharge_id, User.role == UserRole.WAREHOUSE_INCHARGE).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incharge staff member not found.")

    inc.is_active = not inc.is_active
    db.commit()
    status_str = "Activated" if inc.is_active else "Suspended"
    return {"message": f"Incharge staff '{inc.full_name}' is now {status_str}.", "is_active": inc.is_active}


# ---------------------------------------------------------------------------
# 4. FACILITY LOGS & SECURITY OPERATIONS
# ---------------------------------------------------------------------------
@router.get("/incharge-logs")
def get_incharge_logs(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Lists all activity and inspection logs submitted by Warehouse Incharges."""
    logs = db.query(WarehouseActivityLog).order_by(WarehouseActivityLog.created_at.desc()).all()
    results = []
    for l in logs:
        wh = db.query(Warehouse).filter(Warehouse.id == l.warehouse_id).first()
        inc = db.query(User).filter(User.id == l.incharge_id).first()
        results.append({
            "id": l.id,
            "warehouse_title": wh.title if wh else "Storage Facility",
            "incharge_name": inc.full_name if inc else "Staff",
            "log_type": l.log_type,
            "summary": l.summary,
            "detailed_notes": l.detailed_notes,
            "admin_reviewed": l.admin_reviewed,
            "admin_feedback": l.admin_feedback,
            "timestamp": l.created_at.strftime("%Y-%m-%d %H:%M") if l.created_at else "Recent"
        })
    return results

@router.post("/incharge-logs/{log_id}/feedback")
def submit_admin_feedback(
    log_id: int,
    feedback: str,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    log = db.query(WarehouseActivityLog).filter(WarehouseActivityLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found.")

    log.admin_reviewed = True
    log.admin_feedback = feedback
    db.commit()
    return {"message": "Feedback submitted to Warehouse Incharge."}


# ---------------------------------------------------------------------------
# 5. LIVE FLEET TELEMETRY RADAR (CENTRAL DISPATCH RADAR)
# ---------------------------------------------------------------------------
@router.get("/fleet-radar")
def get_fleet_telemetry_radar(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    Returns all registered fleet vehicles and live GPS telemetry metrics for SuperAdmin central dispatch.
    """
    vehicles = db.query(Vehicle).all()
    results = []

    hubs = [
        {"node": "Teku Freight Terminal", "lat": 27.6950, "lng": 85.3060},
        {"node": "Balaju Industrial Ring Road", "lat": 27.7350, "lng": 85.3010},
        {"node": "Koteshwor Junction", "lat": 27.6785, "lng": 85.3490},
        {"node": "Kalimati Cargo Hub", "lat": 27.6985, "lng": 85.2930},
        {"node": "Birgunj ICD Corridor", "lat": 27.0330, "lng": 84.8580},
    ]

    for idx, v in enumerate(vehicles):
        driver_name = getattr(v, "assigned_driver", None).full_name if getattr(v, "assigned_driver", None) else "Unassigned / Fleet Pool"
        driver_phone = getattr(v, "assigned_driver", None).phone_number if getattr(v, "assigned_driver", None) else "-"
        partner_name = v.fleet_partner.company_name or v.fleet_partner.full_name if getattr(v, "fleet_partner", None) else "Independent Partner"

        hub = hubs[idx % len(hubs)]
        lat = getattr(v, "current_lat", None) or getattr(v, "current_latitude", None) or hub["lat"]
        lng = getattr(v, "current_lng", None) or getattr(v, "current_longitude", None) or hub["lng"]
        is_avail = getattr(v, "is_available", True) or getattr(v, "is_active", True)
        speed = getattr(v, "current_speed_kmh", None) or (32.0 if is_avail else 0.0)
        v_cat = getattr(v, "category", None) or getattr(v, "vehicle_category", "mini_truck")
        v_cat_str = v_cat.value if hasattr(v_cat, "value") else str(v_cat)
        payload_tons = round(getattr(v, "payload_capacity_kg", 5000.0) / 1000.0, 1)

        results.append({
            "id": v.id,
            "license_plate": v.license_plate,
            "vehicle_category": v_cat_str,
            "payload_capacity_tons": payload_tons,
            "bluebook_number": v.bluebook_number or f"BB-2081-{v.id:04d}",
            "is_active": is_avail,
            "driver_name": driver_name,
            "driver_phone": driver_phone,
            "partner_name": partner_name,
            "current_node": hub["node"],
            "latitude": lat,
            "longitude": lng,
            "speed_kmh": speed,
            "telemetry_status": "BROADCASTING_LIVE" if is_avail else "IDLE_OFFLINE"
        })
    return results


# ---------------------------------------------------------------------------
# 6. SPACE OWNER DISBURSEMENTS & PAYOUTS LEDGER (FIN-TECH RECONCILIATION)
# ---------------------------------------------------------------------------
@router.get("/payouts")
def get_owner_disbursement_ledger(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    Computes monthly rental payouts for Property Owners:
    - Gross Rent contracted from Client.
    - 10% KTM-WDC platform operating commission.
    - 90% Net Owner monthly disbursement (NPR).
    """
    bookings = db.query(WarehouseRequest).filter(
        WarehouseRequest.status.in_([BookingStatus.APPROVED_CONTRACT_DISPATCHED, BookingStatus.ACTIVE_LEASED])
    ).order_by(WarehouseRequest.created_at.desc()).all()

    results = []
    for b in bookings:
        wh = b.warehouse
        owner = wh.owner if wh else None

        gross_rent = b.monthly_base_rent or 0.0
        margin_fee = round(gross_rent * 0.10, 2)
        net_owner_payout = round(gross_rent - margin_fee, 2)

        is_paid = b.invoice and b.invoice.payment_status == PaymentStatus.PAID
        payout_status = "DISBURSED" if is_paid else "APPROVED_PENDING_DISBURSEMENT"

        results.append({
            "booking_id": b.id,
            "lease_number": f"KWDC-LEASE-{b.id:04d}",
            "warehouse_id": wh.id if wh else None,
            "warehouse_title": wh.title if wh else "Storage Space",
            "warehouse_location": f"{wh.district or 'Kathmandu'}, {wh.neighborhood_landmark or 'Bagmati'}" if wh else "-",
            "owner_name": owner.full_name if owner else "Verified Owner",
            "owner_email": owner.email if owner else "-",
            "owner_phone": owner.phone_number if owner else "-",
            "client_name": b.client.full_name if b.client else "Commercial Client",
            "allocated_sqft": b.allocated_billed_sqft,
            "monthly_gross_rent": gross_rent,
            "kwdc_platform_fee_10pct": margin_fee,
            "net_owner_payout_90pct": net_owner_payout,
            "payout_status": payout_status,
            "disbursement_cycle": "Monthly (End of Month)",
            "lease_start_date": b.lease_start_date.strftime("%Y-%m-%d") if b.lease_start_date else "Active"
        })
    return results

@router.post("/payouts/{booking_id}/disburse")
def disburse_owner_payout(
    booking_id: int,
    payload: PayoutDisburseRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    b = db.query(WarehouseRequest).filter(WarehouseRequest.id == booking_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Lease record not found.")

    if b.invoice:
        b.invoice.payment_status = PaymentStatus.PAID
    b.status = BookingStatus.ACTIVE_LEASED
    db.commit()

    return {
        "message": f"Owner payout for Lease #KWDC-LEASE-{b.id:04d} disbursed successfully via {payload.payment_method}.",
        "transaction_ref": payload.transaction_ref,
        "disbursement_status": "DISBURSED"
    }


# ---------------------------------------------------------------------------
# 7. MAINTENANCE HOLD & SPACE FREEZE MANAGER
# ---------------------------------------------------------------------------
@router.get("/maintenance-holds")
def get_maintenance_hold_requests(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Returns all warehouse maintenance holds requested by property owners."""
    holds = db.query(Warehouse).filter(
        (Warehouse.is_on_maintenance_hold == True) | (Warehouse.hold_reason_note.isnot(None))
    ).order_by(Warehouse.created_at.desc()).all()

    results = []
    for w in holds:
        results.append({
            "warehouse_id": w.id,
            "warehouse_title": w.title,
            "owner_name": w.owner.full_name,
            "owner_phone": w.owner.phone_number,
            "total_sqft": w.total_sqft,
            "available_sqft": w.available_sqft,
            "is_on_maintenance_hold": w.is_on_maintenance_hold,
            "hold_reason_note": w.hold_reason_note or "Routine inspection and maintenance.",
            "is_available": w.is_available,
            "created_at": w.created_at.strftime("%Y-%m-%d %H:%M")
        })
    return results

@router.post("/maintenance-holds/{warehouse_id}/action")
def manage_maintenance_hold(
    warehouse_id: int,
    payload: MaintenanceActionRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Warehouse not found.")

    action_upper = payload.action.upper()
    if action_upper == "APPROVE":
        wh.is_on_maintenance_hold = True
        wh.is_available = False
        msg = f"Maintenance hold on '{wh.title}' APPROVED. Space temporarily frozen from public marketplace."
    elif action_upper == "RELEASE":
        wh.is_on_maintenance_hold = False
        wh.hold_reason_note = None
        if wh.is_approved:
            wh.is_available = True
        msg = f"Maintenance hold on '{wh.title}' RELEASED. Space restored to active marketplace capacity."
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Must be 'APPROVE' or 'RELEASE'.")

    db.commit()
    return {"message": msg, "is_on_maintenance_hold": wh.is_on_maintenance_hold, "is_available": wh.is_available}


# ---------------------------------------------------------------------------
# 8. PLATFORM USER DIRECTORY & RBAC GOVERNANCE
# ---------------------------------------------------------------------------
@router.get("/users")
def get_all_users(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Lists all registered platform users with verification and KYC status."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    results = []
    for u in users:
        # SuperAdmin is the platform auditor/guarantor, inherently verified and exempt from operational KYC
        is_superadmin = (u.role == UserRole.SUPERADMIN)
        kyc_val = "EXEMPT" if is_superadmin else u.kyc_status.value
        results.append({
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "phone_number": u.phone_number,
            "role": u.role.value,
            "operating_location": u.operating_location,
            "is_active": u.is_active,
            "is_verified": True if is_superadmin else bool(u.is_verified),
            "kyc_status": kyc_val,
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "Recent"
        })
    return results

@router.post("/users/{user_id}/status")
def toggle_user_account_status(
    user_id: int,
    payload: UserStatusUpdateRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")
    if u.role == UserRole.SUPERADMIN and u.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate the active SuperAdmin session.")

    u.is_active = payload.is_active
    db.commit()
    state = "Active" if u.is_active else "Suspended"
    return {"message": f"User account '{u.full_name}' is now {state}.", "is_active": u.is_active}

@router.get("/users/{user_id}/kyc")
def get_user_kyc_dossier(
    user_id: int,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Retrieves full role-specific KYC dossier for SuperAdmin audit."""
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")

    profile = db.query(UserKycProfile).filter(UserKycProfile.user_id == u.id).first()
    fleet_vehicles = []
    fleet_drivers = []
    if u.role == UserRole.FLEET_PARTNER:
        for v in db.query(Vehicle).filter(Vehicle.fleet_partner_id == u.id).all():
            fleet_vehicles.append({
                "id": v.id,
                "category": v.category.value if hasattr(v.category, "value") else str(v.category),
                "model_name": v.model_name,
                "license_plate": v.license_plate,
                "bluebook_number": v.bluebook_number,
                "bluebook_photo_url": getattr(v, "bluebook_photo_url", None),
                "payload_capacity_kg": v.payload_capacity_kg,
                "is_verified": bool(v.is_verified),
            })
        for d in db.query(Driver).filter(Driver.fleet_partner_id == u.id).all():
            fleet_drivers.append({
                "id": d.id,
                "full_name": d.full_name,
                "phone_number": d.phone_number,
                "license_number": d.license_number,
                "license_category": d.license_category,
                "id_document_type": getattr(d, "id_document_type", "CITIZENSHIP"),
                "citizenship_no": d.citizenship_no,
                "license_photo_front_url": getattr(d, "license_photo_front_url", None) or getattr(d, "license_photo_url", None),
                "license_photo_back_url": getattr(d, "license_photo_back_url", None),
                "id_doc_front_url": getattr(d, "id_doc_front_url", None) or getattr(d, "citizenship_photo_url", None),
                "id_doc_back_url": getattr(d, "id_doc_back_url", None),
                "kyc_status": d.kyc_status.value if hasattr(d.kyc_status, "value") else str(d.kyc_status),
            })

    return {
        "user_id": u.id,
        "full_name": u.full_name,
        "email": u.email,
        "phone_number": u.phone_number,
        "role": u.role.value,
        "fleet_operator_type": getattr(u, "fleet_operator_type", None),
        "kyc_status": u.kyc_status.value,
        "is_verified": u.is_verified,
        "vehicles": fleet_vehicles,
        "drivers": fleet_drivers,
        "profile": {
            # Property Owner: strictly Citizenship and Bank Account proof
            "citizenship_number": profile.citizenship_number if profile else None,
            "citizenship_front_url": profile.citizenship_front_url if profile else None,
            "citizenship_back_url": profile.citizenship_back_url if profile else None,
            "bank_name": profile.bank_name if profile else None,
            "bank_account_number": profile.bank_account_number if profile else None,
            "bank_account_name": profile.bank_account_name if profile else None,
            "bank_branch": profile.bank_branch if profile else None,
            "bank_proof_doc_url": profile.bank_proof_doc_url if profile else None,
            # Commercial Client
            "company_name": profile.company_name if profile else u.company_name,
            "company_reg_number": profile.company_reg_number if profile else None,
            "company_pan_vat": profile.company_pan_vat or u.kyc_pan_vat if profile else u.kyc_pan_vat,
            "company_reg_doc_url": profile.company_reg_doc_url if profile else None,
            "company_pan_doc_url": profile.company_pan_doc_url if profile else None,
            "authorized_signatory_name": profile.authorized_signatory_name if profile else None,
            "authorized_signatory_doc_url": profile.authorized_signatory_doc_url if profile else None,
            # Fleet Partner
            "fleet_operator_pan_vat": profile.fleet_operator_pan_vat if profile else None,
            "fleet_operator_reg_no": profile.fleet_operator_reg_no if profile else None,
            "fleet_operator_doc_url": profile.fleet_operator_doc_url if profile else None,
            "admin_review_notes": profile.admin_review_notes if profile else None,
            "verified_at": profile.verified_at.strftime("%Y-%m-%d %H:%M") if profile and profile.verified_at else None
        } if profile else None
    }

@router.post("/users/{user_id}/kyc-verify")
def set_user_kyc_status(
    user_id: int,
    payload: UserKycUpdateRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")

    profile = db.query(UserKycProfile).filter(UserKycProfile.user_id == u.id).first()
    now = datetime.now(timezone.utc)
    status_upper = payload.kyc_status.upper()
    if status_upper in ["APPROVED", "VERIFIED"]:
        u.kyc_status = KycStatus.VERIFIED
        u.is_verified = True
        u.kyc_verified_at = now
        if profile:
            profile.kyc_status = KycStatus.VERIFIED
            profile.verified_at = now
            if payload.admin_notes:
                profile.admin_review_notes = payload.admin_notes
        if u.role == UserRole.FLEET_PARTNER:
            for d in db.query(Driver).filter(Driver.fleet_partner_id == u.id).all():
                d.kyc_status = KycStatus.VERIFIED
            for v in db.query(Vehicle).filter(Vehicle.fleet_partner_id == u.id).all():
                v.is_verified = True
    elif status_upper == "REJECTED":
        u.kyc_status = KycStatus.REJECTED
        u.is_verified = False
        if profile:
            profile.kyc_status = KycStatus.REJECTED
            if payload.admin_notes:
                profile.admin_review_notes = payload.admin_notes
        if u.role == UserRole.FLEET_PARTNER:
            for d in db.query(Driver).filter(Driver.fleet_partner_id == u.id).all():
                d.kyc_status = KycStatus.REJECTED
            for v in db.query(Vehicle).filter(Vehicle.fleet_partner_id == u.id).all():
                v.is_verified = False
    else:
        u.kyc_status = KycStatus.UNDER_REVIEW
        if profile:
            profile.kyc_status = KycStatus.UNDER_REVIEW

    db.commit()
    return {"message": f"KYC status for '{u.full_name}' updated to {u.kyc_status.value}.", "kyc_status": u.kyc_status.value}

@router.get("/system-status")
def get_system_status(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Returns database backend status and high-level platform health metrics."""
    db_info = get_db_info()
    user_count = db.query(User).count()
    unverified_count = db.query(User).filter(User.is_verified == False).count()
    pending_kyc_count = db.query(User).filter(User.kyc_status == KycStatus.UNDER_REVIEW).count()
    wh_count = db.query(Warehouse).count()
    return {
        "database": db_info["label"],
        "database_engine": db_info["engine"],
        "is_sqlite_fallback": db_info["is_sqlite"],
        "user_count": user_count,
        "unverified_email_count": unverified_count,
        "pending_kyc_count": pending_kyc_count,
        "warehouse_count": wh_count,
        "active_admin": current_user.email
    }

@router.post("/users/{user_id}/verify-email")
def admin_verify_user_email(
    user_id: int,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Allows SuperAdmin to manually verify an account's email if OTP email delivery is delayed."""
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")
    u.is_verified = True
    u.otp_code = None
    db.commit()
    return {"message": f"Email verified and activated for '{u.full_name}' ({u.email}).", "is_verified": True}

@router.post("/users/{user_id}/resend-otp")
def admin_resend_user_otp(
    user_id: int,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Regenerates OTP and re-dispatches to user's email, returning OTP code to SuperAdmin for emergency onboarding."""
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")
    otp_code = f"{random.randint(100000, 999999)}"
    now = datetime.now(timezone.utc)
    u.otp_code = otp_code
    u.otp_expires_at = now + timedelta(minutes=15)
    db.commit()
    email_sent = send_otp_email(to_email=u.email, to_name=u.full_name, otp_code=otp_code)
    return {
        "message": f"New OTP generated for {u.email}.",
        "otp_code": otp_code,
        "email_dispatched": email_sent
    }

@router.get("/invoices")
def get_admin_invoices(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Retrieves all IRD Schedule 13 electronic tax invoices for platform accounting."""
    invoices = db.query(TaxInvoice).order_by(TaxInvoice.issued_at.desc()).all()
    results = []
    for inv in invoices:
        results.append({
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "buyer_name": inv.buyer_name,
            "buyer_pan_vat": inv.buyer_pan_vat or "N/A",
            "seller_name": inv.seller_name,
            "seller_pan_vat": inv.seller_pan_vat,
            "taxable_base_amount": inv.taxable_base_amount,
            "kwdc_admin_margin": inv.kwdc_admin_margin,
            "vat_13_percent": inv.vat_13_percent,
            "gross_total_npr": inv.gross_total_npr,
            "qr_payload": inv.qr_payload,
            "payment_status": inv.payment_status.value if hasattr(inv.payment_status, "value") else str(inv.payment_status),
            "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
            "storage_booking_id": inv.storage_booking_id,
            "freight_order_id": inv.freight_order_id
        })
    return results


# ---------------------------------------------------------------------------
# 11. SUPERADMIN FREIGHT TARIFF & PLATFORM MARGIN CONTROLLER (OPTION A)
# ---------------------------------------------------------------------------
@router.get("/fare-config")
def get_fare_tariff_config(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    Returns current platform margin % and base formula tariff parameters.
    Includes simulated 15 KM corridor benchmark calculations across vehicle types.
    """
    cfg = get_platform_config(db)

    # Simulate 15km benchmark samples for admin instant preview
    sample_categories = [
        ("PICKUP_VAN", "Pickup / Tata Ace / Bolero (< 1.5T)", 1000.0),
        ("MINI_TRUCK", "Mini Truck / Canter (1.5T - 3.5T)", 2500.0),
        ("HEAVY_TRUCK", "Heavy Truck (3.5T - 10T)", 6000.0),
        ("CONTAINER_TRAILER", "Container / Trailer (> 10T)", 12000.0)
    ]
    simulations = []
    for cat_code, cat_label, weight_kg in sample_categories:
        calc = calculate_freight_benchmark(
            db=db,
            vehicle_category=cat_code,
            distance_km=15.0,
            cargo_weight_kg=weight_kg
        )
        simulations.append({
            "category_code": cat_code,
            "category_label": cat_label,
            "distance_km": 15.0,
            "weight_kg": weight_kg,
            "benchmark_fare_npr": calc["benchmark_fare_npr"],
            "platform_revenue_npr": calc["platform_revenue_npr"],
            "driver_payout_npr": calc["driver_payout_npr"],
            "formula_breakdown": calc["formula_description"]
        })

    return {
        "config_key": cfg.config_key,
        "platform_margin_percent": cfg.platform_margin_percent,
        "flag_drops": {
            "van_pickup": cfg.flag_drop_van_pickup,
            "mini_truck": cfg.flag_drop_mini_truck,
            "heavy_truck": cfg.flag_drop_heavy_truck,
            "container_trailer": cfg.flag_drop_container_trailer
        },
        "rates_per_km": {
            "van_pickup": cfg.rate_per_km_van_pickup,
            "mini_truck": cfg.rate_per_km_mini_truck,
            "heavy_truck": cfg.rate_per_km_heavy_truck,
            "container_trailer": cfg.rate_per_km_container_trailer
        },
        "weight_rate_per_tonne": cfg.weight_rate_per_tonne,
        "fuel_multiplier": cfg.fuel_multiplier,
        "vat_rate_percent": cfg.vat_rate_percent,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
        "simulations_15km": simulations
    }


@router.post("/fare-config")
def update_fare_tariff_config(
    payload: FareConfigUpdateRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    SuperAdmin updates the platform margin % and freight tariff base formula parameters.
    Changes apply dynamically to all subsequent benchmark calculations.
    """
    cfg = get_platform_config(db)

    if payload.platform_margin_percent is not None:
        cfg.platform_margin_percent = max(0.0, min(100.0, float(payload.platform_margin_percent)))
    if payload.flag_drop_van_pickup is not None:
        cfg.flag_drop_van_pickup = max(0.0, float(payload.flag_drop_van_pickup))
    if payload.flag_drop_mini_truck is not None:
        cfg.flag_drop_mini_truck = max(0.0, float(payload.flag_drop_mini_truck))
    if payload.flag_drop_heavy_truck is not None:
        cfg.flag_drop_heavy_truck = max(0.0, float(payload.flag_drop_heavy_truck))
    if payload.flag_drop_container_trailer is not None:
        cfg.flag_drop_container_trailer = max(0.0, float(payload.flag_drop_container_trailer))

    if payload.rate_per_km_van_pickup is not None:
        cfg.rate_per_km_van_pickup = max(0.0, float(payload.rate_per_km_van_pickup))
    if payload.rate_per_km_mini_truck is not None:
        cfg.rate_per_km_mini_truck = max(0.0, float(payload.rate_per_km_mini_truck))
    if payload.rate_per_km_heavy_truck is not None:
        cfg.rate_per_km_heavy_truck = max(0.0, float(payload.rate_per_km_heavy_truck))
    if payload.rate_per_km_container_trailer is not None:
        cfg.rate_per_km_container_trailer = max(0.0, float(payload.rate_per_km_container_trailer))

    if payload.weight_rate_per_tonne is not None:
        cfg.weight_rate_per_tonne = max(0.0, float(payload.weight_rate_per_tonne))
    if payload.fuel_multiplier is not None:
        cfg.fuel_multiplier = max(0.1, float(payload.fuel_multiplier))
    if payload.vat_rate_percent is not None:
        cfg.vat_rate_percent = max(0.0, float(payload.vat_rate_percent))

    db.commit()
    db.refresh(cfg)

    return {
        "message": f"Freight tariff & platform margin updated successfully! Platform margin set to {cfg.platform_margin_percent}%.",
        "platform_margin_percent": cfg.platform_margin_percent,
        "fuel_multiplier": cfg.fuel_multiplier,
        "weight_rate_per_tonne": cfg.weight_rate_per_tonne
    }


# ---------------------------------------------------------------------------
# 12. WAREHOUSEMAN'S LIEN (60-DAY RULE), REMINDER PUSH & AUCTION LEDGER
# ---------------------------------------------------------------------------
class LienReminderRequest(BaseModel):
    stage: str # OVERDUE_MONTH_1, NOTICE_15_DAYS, NOTICE_7_DAYS, GATE_FROZEN_5_DAYS, FINAL_NOTICE_48_HOURS, FORFEITED_AUCTION
    custom_message: Optional[str] = None

class AuctionUpdateRequest(BaseModel):
    auction_status: str # CATALOGUED, AUCTION_ACTIVE, SOLD, REDEEMED
    reserve_price_npr: Optional[float] = None
    winning_bid_npr: Optional[float] = None
    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None
    admin_notes: Optional[str] = None


@router.get("/lien-overdue-leases")
def get_lien_and_overdue_leases(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Lists all leases with their advance payment status, overdue countdowns, and notification logs."""
    bookings = db.query(WarehouseRequest).order_by(WarehouseRequest.created_at.desc()).all()
    now = datetime.now(timezone.utc)
    results = []
    for b in bookings:
        days_left = None
        if b.default_countdown_deadline:
            dl = b.default_countdown_deadline
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=timezone.utc)
            days_left = max(0, (dl - now).days)

        results.append({
            "id": b.id,
            "lease_ref": f"KWDC-LEASE-{b.id:04d}",
            "client_name": b.client.full_name if b.client else "Client",
            "client_email": b.client.email if b.client else "-",
            "warehouse_title": b.warehouse.title if b.warehouse else "Warehouse",
            "allocated_billed_sqft": b.allocated_billed_sqft,
            "booking_duration_type": getattr(b, "booking_duration_type", "MONTHLY"),
            "duration_days": getattr(b, "duration_days", 90),
            "total_monthly_bill": b.total_monthly_bill,
            "status": b.status.value,
            "advance_payment_status": getattr(b, "advance_payment_status", "PAYMENT_DUE"),
            "is_gate_frozen": bool(getattr(b, "is_gate_frozen", False)),
            "is_forfeited": bool(getattr(b, "is_forfeited", False)),
            "days_to_forfeiture": days_left,
            "last_reminder_stage": getattr(b, "last_reminder_stage", None),
            "last_reminder_sent_at": b.last_reminder_sent_at.strftime("%Y-%m-%d %H:%M") if getattr(b, "last_reminder_sent_at", None) else None,
            "notifications_count": len(b.lien_notifications) if getattr(b, "lien_notifications", None) else 0
        })
    return results


@router.post("/bookings/{booking_id}/push-lien-reminder")
def admin_push_lien_reminder(
    booking_id: int,
    payload: LienReminderRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    Admin dispatches an escalating overdue notice (Month 1, 15 Days, 7 Days, 5 Days Freeze,
    48 Hours Final Notice, or Day 60 Stock Forfeiture & Auction).
    """
    booking = db.query(WarehouseRequest).filter(WarehouseRequest.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")

    valid_stages = [
        "OVERDUE_MONTH_1", "NOTICE_15_DAYS", "NOTICE_7_DAYS",
        "GATE_FROZEN_5_DAYS", "FINAL_NOTICE_48_HOURS", "FORFEITED_AUCTION"
    ]
    if payload.stage not in valid_stages:
        raise HTTPException(status_code=400, detail=f"Invalid stage. Choose one of {valid_stages}")

    return push_lien_notification(db, booking, payload.stage, payload.custom_message)


@router.post("/lien-sweep")
def admin_trigger_lien_sweep(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Executes automated 60-day overdue escalation check across all unpaid leases."""
    actions = run_overdue_sweep(db)
    return {
        "message": f"Overdue sweep completed. {len(actions)} lease alert(s) / action(s) triggered.",
        "actions": actions
    }


@router.get("/auctions")
def get_admin_auction_lots(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Lists all forfeited stock lots transferred to KTM-WDC for liquidation auction."""
    lots = db.query(StockAuctionItem).order_by(StockAuctionItem.forfeited_at.desc()).all()
    return [
        {
            "id": l.id,
            "lot_number": l.lot_number,
            "booking_id": l.booking_id,
            "warehouse_title": l.warehouse.title if l.warehouse else f"Warehouse #{l.warehouse_id}",
            "former_client_name": l.client.full_name if l.client else "Defaulted Tenant",
            "item_summary": l.item_summary,
            "estimated_valuation_npr": l.estimated_valuation_npr,
            "arrears_owed_npr": l.arrears_owed_npr,
            "reserve_price_npr": l.reserve_price_npr,
            "winning_bid_npr": l.winning_bid_npr,
            "auction_status": l.auction_status,
            "buyer_name": l.buyer_name,
            "forfeited_at": l.forfeited_at.strftime("%Y-%m-%d") if l.forfeited_at else "",
            "auction_scheduled_at": l.auction_scheduled_at.strftime("%Y-%m-%d") if l.auction_scheduled_at else "",
            "admin_notes": l.admin_notes
        }
        for l in lots
    ]


@router.post("/auctions/{auction_id}/update")
def update_auction_lot(
    auction_id: int,
    payload: AuctionUpdateRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    lot = db.query(StockAuctionItem).filter(StockAuctionItem.id == auction_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Auction lot not found.")

    lot.auction_status = payload.auction_status.upper()
    if payload.reserve_price_npr is not None:
        lot.reserve_price_npr = float(payload.reserve_price_npr)
    if payload.winning_bid_npr is not None:
        lot.winning_bid_npr = float(payload.winning_bid_npr)
    if payload.buyer_name is not None:
        lot.buyer_name = payload.buyer_name
    if payload.buyer_phone is not None:
        lot.buyer_phone = payload.buyer_phone
    if payload.admin_notes is not None:
        lot.admin_notes = payload.admin_notes
    if lot.auction_status == "SOLD":
        lot.sold_at = datetime.now(timezone.utc)

    db.commit()
    return {
        "message": f"Auction Lot {lot.lot_number} updated to {lot.auction_status}.",
        "auction_status": lot.auction_status
    }


# ---------------------------------------------------------------------------
# 13. OWNER CHANGE REQUESTS (15-DAY DELISTING & RATE REVISIONS)
# ---------------------------------------------------------------------------
class AdminChangeProcessRequest(BaseModel):
    status: str # APPROVED or REJECTED
    admin_notes: Optional[str] = None

@router.get("/change-requests")
def get_owner_change_requests(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    reqs = db.query(WarehouseChangeRequest).order_by(WarehouseChangeRequest.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "warehouse_id": r.warehouse_id,
            "warehouse_title": r.warehouse.title if r.warehouse else f"Warehouse #{r.warehouse_id}",
            "owner_name": r.owner.full_name if r.owner else "Owner",
            "request_type": r.request_type,
            "requested_rate_per_sqft": r.requested_rate_per_sqft,
            "reason_note": r.reason_note,
            "status": r.status,
            "admin_notes": r.admin_notes,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else ""
        }
        for r in reqs
    ]

@router.post("/change-requests/{req_id}/process")
def process_owner_change_request(
    req_id: int,
    payload: AdminChangeProcessRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    req = db.query(WarehouseChangeRequest).filter(WarehouseChangeRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Change request not found.")

    decision = payload.status.upper()
    if decision not in ("APPROVED", "REJECTED"):
        raise HTTPException(status_code=400, detail="Status must be APPROVED or REJECTED.")

    req.status = decision
    req.admin_notes = payload.admin_notes
    req.processed_at = datetime.now(timezone.utc)

    wh = req.warehouse
    if decision == "APPROVED" and wh:
        if req.request_type == "DELISTING_15_DAYS":
            wh.is_available = False
            wh.hold_reason_note = f"Owner Delisting Approved: {req.reason_note}"
        elif req.request_type == "RATE_REVISION" and req.requested_rate_per_sqft and req.requested_rate_per_sqft > 0:
            wh.monthly_rate_per_sqft = float(req.requested_rate_per_sqft)

    db.commit()
    return {
        "message": f"Owner change request #{req.id} ({req.request_type}) marked {decision}.",
        "status": decision
    }


@router.get("/sms-outbox")
def get_admin_sms_outbox(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Returns recent OTP & system SMS dispatches (ideal for zero-cost Sandbox/QA OTP inspection)."""
    logs = db.query(SmsOutboxLog).order_by(SmsOutboxLog.created_at.desc()).limit(50).all()
    return {
        "provider_mode": get_sms_provider_mode(),
        "logs": [
            {
                "id": l.id,
                "phone_number": l.phone_number,
                "message": l.message,
                "purpose": l.purpose,
                "provider": l.provider,
                "status": l.status,
                "external_ref": l.external_ref,
                "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else "",
            }
            for l in logs
        ],
    }


@router.get("/holdover-leases")
def get_holdover_leases(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Lists expired leases whose clients still hold un-cleared inventory in storage."""
    now_naive = datetime.utcnow()
    expired = db.query(WarehouseRequest).filter(
        WarehouseRequest.is_forfeited == False,
        WarehouseRequest.lease_end_date != None,
        WarehouseRequest.lease_end_date < now_naive,
    ).all()
    alerts = []
    for lease in expired:
        items = db.query(StockItem).filter(
            StockItem.client_id == lease.client_id,
            StockItem.warehouse_id == lease.warehouse_id,
        ).all()
        rem_units = sum(int(i.total_quantity or 0) + int(getattr(i, "reserved_quantity", 0) or 0) for i in items)
        if rem_units > 0:
            alerts.append({
                "booking_id": lease.id,
                "warehouse_title": lease.warehouse.title if lease.warehouse else f"Warehouse #{lease.warehouse_id}",
                "client_name": lease.client.full_name if lease.client else "Client",
                "client_phone": lease.client.phone_number if lease.client else "-",
                "lease_end_date": lease.lease_end_date.strftime("%Y-%m-%d"),
                "remaining_units": rem_units,
            })
    return alerts


@router.get("/security-agencies")
def get_admin_security_agencies(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Lists registered security agencies awaiting or holding Home Ministry license verification."""
    agencies = db.query(SecurityAgency).order_by(SecurityAgency.created_at.desc()).all()
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "owner_name": a.user.full_name if a.user else "Agency Admin",
            "agency_name": a.agency_name,
            "home_ministry_license_no": a.home_ministry_license_no,
            "emergency_contact_phone": a.emergency_contact_phone,
            "is_verified": bool(a.is_verified),
            "guard_count": len(a.guards or []),
            "created_at": a.created_at.strftime("%Y-%m-%d") if a.created_at else "",
        }
        for a in agencies
    ]


@router.post("/security-agencies/{agency_id}/verify")
def verify_security_agency(
    agency_id: int,
    payload: dict,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    agency = db.query(SecurityAgency).filter(SecurityAgency.id == agency_id).first()
    if not agency:
        raise HTTPException(status_code=404, detail="Security agency not found.")

    approve = bool(payload.get("approve", True))
    agency.is_verified = approve
    if agency.user:
        agency.user.is_verified = approve
        agency.user.kyc_status = KycStatus.VERIFIED if approve else KycStatus.REJECTED
    db.commit()
    return {
        "message": f"Security agency '{agency.agency_name}' is now {'VERIFIED' if approve else 'UNVERIFIED'}.",
        "is_verified": agency.is_verified,
    }
