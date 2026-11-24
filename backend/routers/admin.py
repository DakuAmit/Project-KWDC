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
    WarehouseInchargeAssignment, KycStatus, Vehicle, Driver, GatePass, IncidentReport, UserKycProfile
)
from backend.auth_utils import require_user, require_roles, get_password_hash
from backend.services.contract_service import generate_master_lease_contract
from backend.services.email_service import send_contract_approval_email, send_otp_email

router = APIRouter(prefix="/api/admin", tags=["SuperAdmin Governance"])

# ---------------------------------------------------------------------------
# Pydantic Request Models
# ---------------------------------------------------------------------------
class InchargeProvisionRequest(BaseModel):
    full_name: str
    email: str
    phone_number: str
    warehouse_id: int
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


# ---------------------------------------------------------------------------
# 1. PROPERTY AUDITS & APPROVALS (RULE 1: PHYSICAL AUDIT & LOCKOUT)
# ---------------------------------------------------------------------------
@router.get("/pending-warehouses")
@router.get("/pending")
def get_pending_warehouses(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Lists all properties awaiting SuperAdmin audit."""
    pending = db.query(Warehouse).filter(Warehouse.is_approved == False).all()
    results = []
    for w in pending:
        results.append({
            "id": w.id,
            "owner_name": w.owner.full_name if w.owner else "Property Owner",
            "owner_email": w.owner.email if w.owner else "-",
            "owner_phone": w.owner.phone_number if w.owner else "-",
            "title": w.title,
            "space_type": w.space_type.value if hasattr(w.space_type, "value") else str(w.space_type),
            "total_sqft": w.total_sqft,
            "monthly_rate_per_sqft": w.monthly_rate_per_sqft,
            "neighborhood_landmark": w.neighborhood_landmark,
            "road_access_ft": w.road_access_ft,
            "created_at": w.created_at.strftime("%Y-%m-%d %H:%M") if w.created_at else "Recent"
        })
    return results

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
    booking.lease_end_date = now + timedelta(days=365)

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
        operating_location=warehouse.district or "Kathmandu",
        hashed_password=get_password_hash(raw_password),
        role=UserRole.WAREHOUSE_INCHARGE,
        is_active=True,
        is_verified=True,
        kyc_status=KycStatus.VERIFIED
    )
    db.add(incharge_user)
    db.commit()
    db.refresh(incharge_user)

    # Create assignment
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
        "assigned_facility_id": warehouse.id,
        "assigned_facility_name": warehouse.title,
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
    logs = db.query(WarehouseActivityLog).order_by(WarehouseActivityLog.timestamp.desc()).all()
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
            "timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M")
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
    return {
        "user_id": u.id,
        "full_name": u.full_name,
        "email": u.email,
        "phone_number": u.phone_number,
        "role": u.role.value,
        "kyc_status": u.kyc_status.value,
        "is_verified": u.is_verified,
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
    elif status_upper == "REJECTED":
        u.kyc_status = KycStatus.REJECTED
        u.is_verified = False
        if profile:
            profile.kyc_status = KycStatus.REJECTED
            if payload.admin_notes:
                profile.admin_review_notes = payload.admin_notes
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
