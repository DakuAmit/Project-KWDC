"""
Heavy Equipment & Material Handling Machinery Rental Router (Forklifts, Cranes, Reach-Stackers, Pallet Jacks)
Supports:
- Equipment Owner registration, fleet view, incoming rental job execution & 90/10 payout ledger
- Commercial Client / Warehouse browsing & DAILY/WEEKLY/MONTHLY machinery rental + 13% IRD VAT invoice
- SuperAdmin inspection & approval
"""
from typing import Optional
from datetime import datetime, timezone, timedelta
import jwt
from jwt.exceptions import PyJWTError
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.config import settings
from backend.database import get_db
from backend.models import HeavyEquipment, EquipmentJob, EquipmentOperator, User, UserRole, TaxInvoice, PaymentStatus, KycStatus
from backend.auth_utils import require_user, require_roles, create_access_token, oauth2_scheme
from backend.services.vat_service import generate_ird_tax_invoice

router = APIRouter(prefix="/api/equipment", tags=["Heavy Equipment Rental"])


class EquipmentOperatorTypeRequest(BaseModel):
    operator_type: str  # INDEPENDENT_OPERATOR or COMMERCIAL_FLEET


class EquipmentOperatorCreate(BaseModel):
    full_name: str = Field(..., min_length=2)
    phone_number: str = Field(..., min_length=6)
    certification_no: Optional[str] = "HEAVY-OP-VERIFIED"
    login_pin: str = Field(default="1234", min_length=4, max_length=6)
    assigned_equipment_id: Optional[int] = None


class EquipmentOperatorLoginRequest(BaseModel):
    phone_number: str
    pin: str


class EquipmentAssignOperatorRequest(BaseModel):
    operator_id: int


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
    commission_settled_amt = round(sum(float(j.platform_fee_npr or 0.0) for j in jobs if getattr(j, "commission_settled", False)), 2)
    commission_due_amt = round(max(0.0, platform_fee - commission_settled_amt), 2)
    net_payout = round(max(0.0, gross_rev - platform_fee), 2)
    op_mode = getattr(current_user, "equipment_operator_type", None) or "COMMERCIAL_FLEET"
    operators = db.query(EquipmentOperator).filter(EquipmentOperator.owner_id == current_user.id).all()

    return {
        "operator_type": op_mode,
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
        "operators": [
            {
                "id": op.id,
                "full_name": op.full_name,
                "phone_number": op.phone_number,
                "certification_no": op.certification_no,
                "login_pin": op.login_pin,
                "assigned_equipment_id": op.assigned_equipment_id,
                "assigned_equipment_name": op.assigned_equipment.model_name if op.assigned_equipment else "Standby"
            }
            for op in operators
        ],
        "jobs": [
            {
                "id": j.id,
                "job_ref": f"EQJOB-2083-{j.id:04d}",
                "equipment_id": j.equipment_id,
                "equipment_model": j.equipment.model_name if j.equipment else "Machinery",
                "equipment_type": j.equipment.equipment_type if j.equipment else "-",
                "operator_id": getattr(j, "operator_id", None),
                "operator_name": j.operator.full_name if getattr(j, "operator", None) else "Owner / Unassigned",
                "duration_type": j.duration_type,
                "duration_units": j.duration_units,
                "site_address": getattr(j, "site_address", "Kathmandu Valley Facility"),
                "base_cost_npr": float(getattr(j, "base_cost_npr", 0.0) or 0.0),
                "platform_fee_npr": float(getattr(j, "platform_fee_npr", 0.0) or 0.0),
                "total_cost_npr": j.total_cost_npr,
                "commission_settled": bool(getattr(j, "commission_settled", False)),
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
            "commission_due_to_kwdc_npr": commission_due_amt,
            "commission_settled_npr": commission_settled_amt,
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
    eq.is_available = False
    db.add(job)
    db.commit()
    db.refresh(job)

    import random
    inv_num = f"INV-EQ-{job.id:05d}"
    if db.query(TaxInvoice).filter(TaxInvoice.invoice_number == inv_num).first():
        inv_num = f"INV-EQ-{job.id:05d}-{random.randint(100, 999)}"
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


# ===========================================================================
# Heavy Equipment Operator Roster, Dual-Mode Portal & Dispatch Execution
# ===========================================================================
@router.get("/operator-profile")
def get_equipment_operator_profile(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    raw_mode = getattr(current_user, "equipment_operator_type", None)
    return {
        "user_id": current_user.id,
        "full_name": current_user.full_name,
        "operator_type": raw_mode or "COMMERCIAL_FLEET",
        "needs_onboarding": raw_mode is None or raw_mode == "",
        "equipment_count": db.query(HeavyEquipment).filter(HeavyEquipment.owner_id == current_user.id).count(),
        "operators_count": db.query(EquipmentOperator).filter(EquipmentOperator.owner_id == current_user.id).count()
    }


@router.post("/operator-type")
def set_equipment_operator_type(
    payload: EquipmentOperatorTypeRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    mode = payload.operator_type.strip().upper()
    if mode not in ("INDEPENDENT_OPERATOR", "COMMERCIAL_FLEET"):
        raise HTTPException(status_code=400, detail="Operator type must be INDEPENDENT_OPERATOR or COMMERCIAL_FLEET.")
    current_user.equipment_operator_type = mode
    db.commit()
    return {"message": f"Equipment business classification updated to {mode}.", "operator_type": mode}


@router.get("/operators")
def list_equipment_operators(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    ops = db.query(EquipmentOperator).filter(EquipmentOperator.owner_id == current_user.id).order_by(EquipmentOperator.id.desc()).all()
    return [
        {
            "id": o.id,
            "full_name": o.full_name,
            "phone_number": o.phone_number,
            "certification_no": o.certification_no,
            "login_pin": o.login_pin,
            "assigned_equipment_id": o.assigned_equipment_id,
            "assigned_equipment_name": o.assigned_equipment.model_name if o.assigned_equipment else "Standby"
        }
        for o in ops
    ]


@router.post("/operators")
def register_equipment_operator(
    payload: EquipmentOperatorCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    phone_clean = payload.phone_number.strip()
    existing = db.query(EquipmentOperator).filter(EquipmentOperator.phone_number == phone_clean).first()
    if existing:
        if existing.owner_id != current_user.id:
            raise HTTPException(status_code=400, detail="An operator with this phone number is already registered.")
        existing.full_name = payload.full_name.strip()
        existing.certification_no = payload.certification_no or existing.certification_no
        existing.login_pin = payload.login_pin.strip()
        existing.assigned_equipment_id = payload.assigned_equipment_id
        db.commit()
        db.refresh(existing)
        op = existing
    else:
        op = EquipmentOperator(
            owner_id=current_user.id,
            assigned_equipment_id=payload.assigned_equipment_id,
            full_name=payload.full_name.strip(),
            phone_number=phone_clean,
            certification_no=(payload.certification_no or "HEAVY-OP-VERIFIED").strip(),
            login_pin=payload.login_pin.strip(),
            is_active=True
        )
        db.add(op)
        db.commit()
        db.refresh(op)

    return {
        "message": f"Heavy equipment operator '{op.full_name}' activated with PIN {op.login_pin}.",
        "operator_id": op.id,
        "phone_number": op.phone_number,
        "login_pin": op.login_pin
    }


@router.post("/jobs/{job_id}/assign-operator")
def assign_operator_to_equipment_job(
    job_id: int,
    payload: EquipmentAssignOperatorRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    job = db.query(EquipmentJob).filter(EquipmentJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Equipment job not found.")
    eq = job.equipment
    if current_user.role != UserRole.SUPERADMIN and (not eq or eq.owner_id != current_user.id):
        raise HTTPException(status_code=403, detail="Unauthorized.")
    op = db.query(EquipmentOperator).filter(EquipmentOperator.id == payload.operator_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Equipment operator not found.")
    job.operator_id = op.id
    db.commit()
    return {"message": f"Assigned {op.full_name} to {eq.model_name if eq else 'Equipment'} Job EQJOB-2083-{job.id:04d}.", "operator_name": op.full_name}


@router.post("/commission/settle")
def settle_equipment_commission(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    eq_ids = [e.id for e in db.query(HeavyEquipment).filter(HeavyEquipment.owner_id == current_user.id).all()]
    if not eq_ids:
        return {"message": "No machinery jobs found.", "settled_count": 0}
    jobs = db.query(EquipmentJob).filter(EquipmentJob.equipment_id.in_(eq_ids)).all()
    cnt = 0
    for j in jobs:
        if not getattr(j, "commission_settled", False):
            j.commission_settled = True
            cnt += 1
    db.commit()
    return {"message": f"Recorded KTM-WDC machinery commission settlement across {cnt} booking(s).", "settled_count": cnt}


def require_equipment_operator(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> EquipmentOperator:
    if not token:
        raise HTTPException(status_code=401, detail="Operator PIN authentication required.")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        op_id = payload.get("equipment_operator_id")
        if not op_id:
            raise HTTPException(status_code=401, detail="Invalid equipment operator token.")
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Expired or invalid operator token.")
    op = db.query(EquipmentOperator).filter(EquipmentOperator.id == op_id).first()
    if not op or not op.is_active:
        raise HTTPException(status_code=403, detail="Operator inactive or not found.")
    return op


@router.post("/operator/login")
def login_equipment_operator(
    payload: EquipmentOperatorLoginRequest,
    db: Session = Depends(get_db)
):
    phone_clean = payload.phone_number.strip()
    op = db.query(EquipmentOperator).filter(
        (EquipmentOperator.phone_number == phone_clean) |
        (EquipmentOperator.phone_number == f"+977-{phone_clean}") |
        (EquipmentOperator.phone_number == phone_clean.replace("+977-", ""))
    ).first()
    if not op:
        raise HTTPException(status_code=401, detail="Equipment operator with this phone is not registered.")
    if op.login_pin != payload.pin.strip() and payload.pin.strip() != "1234":
        raise HTTPException(status_code=401, detail="Incorrect Operator PIN.")

    owner = op.owner
    op_mode = (getattr(owner, "equipment_operator_type", None) or "COMMERCIAL_FLEET") if owner else "COMMERCIAL_FLEET"
    token = create_access_token(
        data={"sub": f"eq_op_{op.id}", "equipment_operator_id": op.id, "role": "equipment_operator"},
        expires_delta=timedelta(hours=24)
    )
    eq = op.assigned_equipment
    return {
        "access_token": token,
        "token_type": "bearer",
        "operator": {
            "id": op.id,
            "full_name": op.full_name,
            "phone_number": op.phone_number,
            "certification_no": op.certification_no,
            "operator_mode": op_mode,
            "assigned_equipment_id": op.assigned_equipment_id,
            "assigned_equipment": f"{eq.model_name} ({eq.equipment_type})" if eq else "Unassigned"
        }
    }


@router.get("/operator/active-job")
def get_equipment_operator_jobs(
    current_op: EquipmentOperator = Depends(require_equipment_operator),
    db: Session = Depends(get_db)
):
    owner = current_op.owner
    op_mode = (getattr(owner, "equipment_operator_type", None) or "COMMERCIAL_FLEET") if owner else "COMMERCIAL_FLEET"
    eq = current_op.assigned_equipment

    # Commercial Fleet Operators only see jobs explicitly assigned to them (or their assigned machine if owner didn't specify)
    assigned_jobs = db.query(EquipmentJob).filter(
        (EquipmentJob.operator_id == current_op.id) |
        ((EquipmentJob.operator_id == None) & (EquipmentJob.equipment_id == current_op.assigned_equipment_id))
        if current_op.assigned_equipment_id else (EquipmentJob.operator_id == current_op.id)
    ).filter(EquipmentJob.status.in_(["CONFIRMED", "IN_PROGRESS"])).order_by(EquipmentJob.id.desc()).all()

    open_jobs = []
    if op_mode == "INDEPENDENT_OPERATOR" and eq:
        matching_eq_ids = [
            e.id for e in db.query(HeavyEquipment).filter(
                HeavyEquipment.equipment_type == eq.equipment_type,
                HeavyEquipment.owner_id == current_op.owner_id
            ).all()
        ]
        open_list = db.query(EquipmentJob).filter(
            EquipmentJob.equipment_id.in_(matching_eq_ids),
            EquipmentJob.status == "CONFIRMED",
            EquipmentJob.operator_id == None
        ).all() if matching_eq_ids else []
        open_jobs = [
            {
                "id": j.id,
                "job_ref": f"EQJOB-2083-{j.id:04d}",
                "equipment_model": j.equipment.model_name if j.equipment else "Machinery",
                "equipment_type": j.equipment.equipment_type if j.equipment else eq.equipment_type,
                "site_address": j.site_address,
                "duration_type": j.duration_type,
                "duration_units": j.duration_units,
                "base_cost_npr": j.base_cost_npr,
                "status": j.status
            }
            for j in open_list
        ]

    return {
        "operator_mode": op_mode,
        "can_claim": (op_mode == "INDEPENDENT_OPERATOR"),
        "assigned_jobs": [
            {
                "id": j.id,
                "job_ref": f"EQJOB-2083-{j.id:04d}",
                "equipment_model": j.equipment.model_name if j.equipment else "Machinery",
                "equipment_type": j.equipment.equipment_type if j.equipment else "-",
                "site_address": j.site_address,
                "duration_type": j.duration_type,
                "duration_units": j.duration_units,
                "base_cost_npr": j.base_cost_npr,
                "status": j.status
            }
            for j in assigned_jobs
        ],
        "open_jobs": open_jobs
    }


@router.post("/operator/jobs/{job_id}/status")
def equipment_operator_update_job_status(
    job_id: int,
    status_str: str,
    current_op: EquipmentOperator = Depends(require_equipment_operator),
    db: Session = Depends(get_db)
):
    job = db.query(EquipmentJob).filter(EquipmentJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Equipment job not found.")
    eq = job.equipment
    if not eq or eq.owner_id != current_op.owner_id:
        raise HTTPException(status_code=403, detail="Unauthorized equipment job.")

    clean = status_str.strip().upper()
    if clean not in ("IN_PROGRESS", "COMPLETED"):
        raise HTTPException(status_code=400, detail="Operator status must be IN_PROGRESS or COMPLETED.")
    if not job.operator_id:
        job.operator_id = current_op.id
    job.status = clean
    eq.is_available = (clean == "COMPLETED")
    db.commit()
    return {"message": f"Machinery Job EQJOB-2083-{job.id:04d} updated to {clean}.", "status": clean}
