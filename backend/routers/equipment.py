"""
Heavy Equipment & Material Handling Machinery Rental Router (Forklifts, Cranes, Reach-Stackers, Pallet Jacks)
Supports:
- Equipment Owner registration, fleet view, incoming rental job execution & 90/10 payout ledger
- Commercial Client / Warehouse browsing & DAILY/WEEKLY/MONTHLY machinery rental + 13% IRD VAT invoice
- SuperAdmin inspection & approval
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import HeavyEquipment, EquipmentJob, User, UserRole, TaxInvoice, PaymentStatus, KycStatus
from backend.auth_utils import require_user, require_roles
from backend.services.vat_service import generate_ird_tax_invoice

router = APIRouter(prefix="/api/equipment", tags=["Heavy Equipment Rental"])


class EquipmentRegisterRequest(BaseModel):
    equipment_type: str = Field(..., description="Forklift, Reach Stacker, Mobile Crane, Pallet Jack, Excavator")
    model_name: str = Field(..., min_length=2)
    registration_no: Optional[str] = None
    capacity_ton: float = Field(..., gt=0)
    hourly_rate_npr: Optional[float] = 1500.0
    daily_rate_npr: float = Field(..., gt=0)
    monthly_rate_npr: float = Field(..., gt=0)
    operator_included: bool = True
    location_city: str = "Kathmandu"
    photo_url: Optional[str] = None


class EquipmentBookRequest(BaseModel):
    equipment_id: int
    duration_type: str = "DAILY"  # HOURLY, DAILY, MONTHLY
    duration_units: int = Field(default=1, ge=1, le=36)
    site_address: str = Field(..., min_length=3)
    notes: Optional[str] = None


@router.post("/register")
def register_heavy_equipment(
    payload: EquipmentRegisterRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    if current_user.role not in (UserRole.EQUIPMENT_OWNER, UserRole.SUPERADMIN):
        if current_user.role in (UserRole.COMMERCIAL_CLIENT, UserRole.PROPERTY_OWNER):
            raise HTTPException(
                status_code=403,
                detail="Only Heavy Equipment Owners can register machinery."
            )
        current_user.role = UserRole.EQUIPMENT_OWNER

    eq = HeavyEquipment(
        owner_id=current_user.id,
        equipment_type=payload.equipment_type.strip(),
        model_name=payload.model_name.strip(),
        registration_no=(payload.registration_no or "").strip() or None,
        capacity_ton=float(payload.capacity_ton),
        hourly_rate_npr=float(payload.hourly_rate_npr or 1500.0),
        daily_rate_npr=float(payload.daily_rate_npr),
        monthly_rate_npr=float(payload.monthly_rate_npr),
        operator_included=bool(payload.operator_included),
        location_city=payload.location_city.strip() or "Kathmandu",
        photo_url=(payload.photo_url or "").strip() or None,
        is_approved=(current_user.role == UserRole.SUPERADMIN),
        is_available=True
    )
    db.add(eq)
    db.commit()
    db.refresh(eq)

    return {
        "message": f"Machinery '{eq.model_name}' registered and submitted for SuperAdmin safety audit.",
        "equipment_id": eq.id,
        "is_approved": eq.is_approved
    }


@router.get("/my-fleet")
def get_my_equipment_fleet(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    items = db.query(HeavyEquipment).filter(HeavyEquipment.owner_id == current_user.id).order_by(HeavyEquipment.id.desc()).all()
    eq_ids = [e.id for e in items]
    jobs = db.query(EquipmentJob).filter(EquipmentJob.equipment_id.in_(eq_ids)).order_by(EquipmentJob.id.desc()).all() if eq_ids else []

    gross_rev = round(sum(float(j.base_cost_npr or j.total_cost_npr or 0.0) for j in jobs), 2)
    platform_fee = round(sum(float(j.platform_fee_npr or (float(j.total_cost_npr or 0.0) * 0.10)) for j in jobs), 2)
    net_payout = round(max(0.0, gross_rev - platform_fee), 2)

    return {
        "equipment": [
            {
                "id": e.id,
                "equipment_type": e.equipment_type,
                "model_name": e.model_name,
                "registration_no": e.registration_no or f"EQ-{e.id:04d}",
                "capacity_ton": e.capacity_ton,
                "hourly_rate_npr": float(getattr(e, "hourly_rate_npr", 1500.0) or 1500.0),
                "daily_rate_npr": e.daily_rate_npr,
                "monthly_rate_npr": e.monthly_rate_npr,
                "operator_included": bool(getattr(e, "operator_included", True)),
                "location_city": e.location_city,
                "photo_url": getattr(e, "photo_url", None),
                "is_approved": bool(getattr(e, "is_approved", False)),
                "is_available": bool(e.is_available),
                "created_at": e.created_at.strftime("%Y-%m-%d") if e.created_at else "-"
            }
            for e in items
        ],
        "jobs": [
            {
                "id": j.id,
                "job_ref": f"EQJOB-2083-{j.id:04d}",
                "equipment_id": j.equipment_id,
                "equipment_model": j.equipment.model_name if j.equipment else "Machinery",
                "equipment_type": j.equipment.equipment_type if j.equipment else "-",
                "duration_type": j.duration_type,
                "duration_units": j.duration_units,
                "site_address": getattr(j, "site_address", "Kathmandu Valley Facility"),
                "base_cost_npr": float(getattr(j, "base_cost_npr", 0.0) or 0.0),
                "platform_fee_npr": float(getattr(j, "platform_fee_npr", 0.0) or 0.0),
                "total_cost_npr": j.total_cost_npr,
                "status": j.status,
                "start_date": j.start_date.strftime("%Y-%m-%d") if j.start_date else "-"
            }
            for j in jobs
        ],
        "summary": {
            "total_units": len(items),
            "active_jobs": sum(1 for j in jobs if j.status in ("CONFIRMED", "IN_PROGRESS")),
            "gross_revenue_npr": gross_rev,
            "platform_fee_npr": platform_fee,
            "net_payout_npr": net_payout
        }
    }


@router.get("/catalog")
def get_approved_equipment_catalog(db: Session = Depends(get_db)):
    items = db.query(HeavyEquipment).filter(
        HeavyEquipment.is_approved == True,
        HeavyEquipment.is_available == True
    ).order_by(HeavyEquipment.id.desc()).all()

    return [
        {
            "id": e.id,
            "equipment_type": e.equipment_type,
            "model_name": e.model_name,
            "capacity_ton": e.capacity_ton,
            "hourly_rate_npr": float(getattr(e, "hourly_rate_npr", 1500.0) or 1500.0),
            "daily_rate_npr": e.daily_rate_npr,
            "monthly_rate_npr": e.monthly_rate_npr,
            "operator_included": bool(getattr(e, "operator_included", True)),
            "location_city": e.location_city,
            "photo_url": getattr(e, "photo_url", None)
        }
        for e in items
    ]


@router.post("/book")
def book_heavy_equipment(
    payload: EquipmentBookRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    eq = db.query(HeavyEquipment).filter(HeavyEquipment.id == payload.equipment_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Heavy equipment not found.")
    if not getattr(eq, "is_approved", False):
        raise HTTPException(status_code=400, detail="This equipment is pending SuperAdmin safety approval.")
    if not eq.is_available:
        raise HTTPException(status_code=400, detail="This equipment is currently deployed on another job.")

    dtype = payload.duration_type.upper()
    if dtype == "HOURLY":
        unit_rate = float(getattr(eq, "hourly_rate_npr", 1500.0) or 1500.0)
    elif dtype == "MONTHLY":
        unit_rate = float(eq.monthly_rate_npr)
    else:
        dtype = "DAILY"
        unit_rate = float(eq.daily_rate_npr)

    base_cost = round(unit_rate * payload.duration_units, 2)
    platform_fee = round(base_cost * 0.10, 2)
    vat_amt = round(base_cost * 0.13, 2)
    total_cost = round(base_cost + vat_amt, 2)

    job = EquipmentJob(
        equipment_id=eq.id,
        client_id=current_user.id,
        duration_type=dtype,
        duration_units=payload.duration_units,
        site_address=payload.site_address.strip(),
        notes=payload.notes,
        base_cost_npr=base_cost,
        platform_fee_npr=platform_fee,
        vat_13_percent=vat_amt,
        total_cost_npr=total_cost,
        status="CONFIRMED"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    inv_num = f"INV-EQ-{job.id:05d}"
    vat_data = generate_ird_tax_invoice(
        invoice_number=inv_num,
        buyer_name=current_user.company_name or current_user.full_name,
        buyer_pan=current_user.kyc_pan_vat or "UNREGISTERED",
        service_type="EQUIPMENT_RENTAL",
        base_tariff=base_cost,
        margin_percent=0.10
    )
    invoice = TaxInvoice(
        invoice_number=inv_num,
        buyer_name=current_user.company_name or current_user.full_name,
        buyer_pan_vat=current_user.kyc_pan_vat,
        taxable_base_amount=base_cost,
        kwdc_admin_margin=platform_fee,
        vat_13_percent=vat_amt,
        gross_total_npr=total_cost,
        qr_payload=vat_data["qr_payload"],
        payment_status=PaymentStatus.UNPAID
    )
    db.add(invoice)
    db.commit()

    return {
        "message": f"Booked {eq.model_name} ({payload.duration_units} {dtype.lower()} units). Schedule 13 VAT invoice issued.",
        "job_id": job.id,
        "job_ref": f"EQJOB-2083-{job.id:04d}",
        "base_cost_npr": base_cost,
        "vat_13_percent": vat_amt,
        "total_cost_npr": total_cost,
        "invoice_number": invoice.invoice_number
    }


@router.get("/my-rentals")
def get_client_equipment_rentals(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    jobs = db.query(EquipmentJob).filter(EquipmentJob.client_id == current_user.id).order_by(EquipmentJob.id.desc()).all()
    return [
        {
            "id": j.id,
            "job_ref": f"EQJOB-2083-{j.id:04d}",
            "equipment_model": j.equipment.model_name if j.equipment else "Machinery",
            "equipment_type": j.equipment.equipment_type if j.equipment else "-",
            "duration_type": j.duration_type,
            "duration_units": j.duration_units,
            "site_address": getattr(j, "site_address", "Kathmandu"),
            "total_cost_npr": j.total_cost_npr,
            "status": j.status,
            "start_date": j.start_date.strftime("%Y-%m-%d") if j.start_date else "-"
        }
        for j in jobs
    ]


@router.post("/jobs/{job_id}/status")
def update_equipment_job_status(
    job_id: int,
    status_str: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    job = db.query(EquipmentJob).filter(EquipmentJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Equipment rental job not found.")
    eq = job.equipment
    if current_user.role != UserRole.SUPERADMIN and (not eq or eq.owner_id != current_user.id):
        raise HTTPException(status_code=403, detail="Unauthorized.")

    clean_status = status_str.strip().upper()
    if clean_status not in ("CONFIRMED", "IN_PROGRESS", "COMPLETED", "CANCELLED"):
        raise HTTPException(status_code=400, detail="Invalid equipment job status.")

    job.status = clean_status
    if eq:
        eq.is_available = (clean_status in ("COMPLETED", "CANCELLED"))
    db.commit()
    return {"message": f"Equipment job EQJOB-2083-{job.id:04d} updated to {clean_status}.", "status": clean_status}


@router.get("/admin/all")
def admin_list_all_equipment(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    items = db.query(HeavyEquipment).order_by(HeavyEquipment.id.desc()).all()
    return [
        {
            "id": e.id,
            "equipment_type": e.equipment_type,
            "model_name": e.model_name,
            "registration_no": e.registration_no or f"EQ-{e.id:04d}",
            "capacity_ton": e.capacity_ton,
            "daily_rate_npr": e.daily_rate_npr,
            "monthly_rate_npr": e.monthly_rate_npr,
            "location_city": e.location_city,
            "owner_name": e.owner.full_name if e.owner else "Owner",
            "owner_phone": e.owner.phone_number if e.owner else "-",
            "is_approved": bool(getattr(e, "is_approved", False)),
            "is_available": bool(e.is_available),
        }
        for e in items
    ]


@router.post("/admin/{equipment_id}/approve")
def admin_approve_equipment(
    equipment_id: int,
    approved: bool = True,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    eq = db.query(HeavyEquipment).filter(HeavyEquipment.id == equipment_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found.")
    eq.is_approved = approved
    db.commit()
    state = "approved & published to rental catalog" if approved else "rejected/suspended"
    return {"message": f"Machinery '{eq.model_name}' {state}.", "is_approved": eq.is_approved}
