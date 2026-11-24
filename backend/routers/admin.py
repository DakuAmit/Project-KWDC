"""
SuperAdmin Master Operations Router for KTM-WDC
Governs:
1. Auditing & Approving Property Listings
2. Executing & Emailing Master Commercial Contracts via Brevo
3. Post-Approval Governance & Feature Overrides
4. Client Booking Activation (Starting Owner Cashflow)
5. Reviewing Warehouse Incharge Logs
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import Optional
from backend.database import get_db
from backend.models import (
    Warehouse, WarehouseRequest, User, UserRole,
    BookingStatus, TaxInvoice, PaymentStatus, WarehouseActivityLog
)
from backend.auth_utils import require_user, require_roles
from backend.services.contract_service import generate_master_lease_contract
from backend.services.email_service import send_contract_approval_email

router = APIRouter(prefix="/api/admin", tags=["SuperAdmin Governance"])

@router.get("/pending-warehouses")
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
            "owner_name": w.owner.full_name,
            "owner_email": w.owner.email,
            "owner_phone": w.owner.phone_number,
            "title": w.title,
            "space_type": w.space_type.value,
            "total_sqft": w.total_sqft,
            "monthly_rate_per_sqft": w.monthly_rate_per_sqft,
            "neighborhood_landmark": w.neighborhood_landmark,
            "road_access_ft": w.road_access_ft,
            "created_at": w.created_at.strftime("%Y-%m-%d %H:%M")
        })
    return results

@router.post("/warehouses/{warehouse_id}/approve")
def approve_and_dispatch_contract(
    warehouse_id: int,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    Step 7 of Architecture:
    Admin clicks 'Verify & Dispatch Contract':
    - Status becomes APPROVED (is_available = True).
    - Master Commercial Lease Agreement is executed and emailed to owner via Brevo.
    - Property features are locked permanently from owner tampering.
    - Zero Holding Liability continues until client assignment.
    """
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found.")

    owner = warehouse.owner
    contract_data = generate_master_lease_contract(warehouse, owner)

    warehouse.is_approved = True
    warehouse.is_available = True
    warehouse.lease_contract_url = contract_data["contract_number"]
    db.commit()

    # Send official contract to property owner email
    email_dispatched = send_contract_approval_email(
        owner_email=owner.email,
        owner_name=owner.full_name,
        warehouse_title=warehouse.title,
        contract_text=contract_data["contract_text"]
    )

    return {
        "message": f"Facility verified and approved! Contract {contract_data['contract_number']} dispatched to {owner.email}.",
        "contract_number": contract_data["contract_number"],
        "email_dispatched": email_dispatched,
        "holding_liability": "NPR 0.00 (Zero Holding Liability until rented)",
        "features_locked": True
    }

@router.put("/warehouses/{warehouse_id}/admin-override")
def admin_override_warehouse(
    warehouse_id: int,
    title: Optional[str] = None,
    monthly_rate_per_sqft: Optional[float] = None,
    is_available: Optional[bool] = None,
    is_on_maintenance_hold: Optional[bool] = None,
    hold_reason_note: Optional[str] = None,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    Post-approval operations: only Admin can modify warehouse features,
    adjust tariffs, or alter availability states.
    """
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found.")

    if title:
        warehouse.title = title
    if monthly_rate_per_sqft is not None:
        warehouse.monthly_rate_per_sqft = monthly_rate_per_sqft
    if is_available is not None:
        warehouse.is_available = is_available
    if is_on_maintenance_hold is not None:
        warehouse.is_on_maintenance_hold = is_on_maintenance_hold
    if hold_reason_note is not None:
        warehouse.hold_reason_note = hold_reason_note

    db.commit()
    return {"message": "Warehouse updated under SuperAdmin authority."}

@router.get("/bookings")
def get_all_bookings(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    bookings = db.query(WarehouseRequest).all()
    results = []
    for b in bookings:
        results.append({
            "id": b.id,
            "client_name": b.client.full_name,
            "client_email": b.client.email,
            "warehouse_title": b.warehouse.title,
            "owner_name": b.warehouse.owner.full_name,
            "requested_sqft": b.requested_sqft,
            "allocated_billed_sqft": b.allocated_billed_sqft,
            "total_monthly_bill": b.total_monthly_bill,
            "status": b.status.value,
            "invoice_number": b.invoice.invoice_number if b.invoice else "N/A",
            "invoice_paid": b.invoice.payment_status.value == "paid" if b.invoice else False
        })
    return results

@router.post("/bookings/{booking_id}/activate")
def activate_commercial_lease(
    booking_id: int,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    SuperAdmin activates lease:
    - Rental disbursement to owner starts on this exact date.
    - Warehouse available capacity is reduced.
    """
    booking = db.query(WarehouseRequest).filter(WarehouseRequest.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking request not found.")

    warehouse = booking.warehouse
    now = datetime.now(timezone.utc)

    booking.status = BookingStatus.ACTIVE_LEASED
    booking.lease_start_date = now
    booking.lease_end_date = now + timedelta(days=90) # Standard 3 months
    
    # Deduct available capacity
    warehouse.available_sqft = max(0.0, warehouse.available_sqft - booking.allocated_billed_sqft)
    if warehouse.available_sqft <= 0:
        warehouse.is_available = False

    db.commit()
    return {
        "message": f"Commercial lease activated for {booking.allocated_billed_sqft:,.2f} sq ft! Owner rental cashflow commenced today.",
        "lease_start_date": booking.lease_start_date.strftime("%Y-%m-%d"),
        "warehouse_remaining_sqft": warehouse.available_sqft
    }

@router.get("/incharge-logs")
def get_incharge_activity_logs(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    logs = db.query(WarehouseActivityLog).order_by(WarehouseActivityLog.created_at.desc()).all()
    results = []
    for l in logs:
        results.append({
            "id": l.id,
            "warehouse_title": l.warehouse.title,
            "incharge_name": l.incharge.full_name,
            "log_type": l.log_type,
            "summary": l.summary,
            "detailed_notes": l.detailed_notes,
            "admin_reviewed": l.admin_reviewed,
            "admin_feedback": l.admin_feedback,
            "created_at": l.created_at.strftime("%Y-%m-%d %H:%M")
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

@router.get("/users")
def get_all_users(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Lists all registered platform users with verification and KYC status."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    results = []
    for u in users:
        results.append({
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "phone_number": u.phone_number,
            "role": u.role.value,
            "operating_location": u.operating_location,
            "is_verified": u.is_verified,
            "kyc_status": u.kyc_status.value,
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M")
        })
    return results
