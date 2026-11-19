from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.equipment import Equipment, EquipmentJob, EquipmentRequest

router = APIRouter(tags=["Heavy Equipment"])
from app.core.templates import templates

class EquipmentCreatePayload(BaseModel):
    name: str
    type: str  # forklift, crane, reach_stacker, telehandler
    model: Optional[str] = None
    year: Optional[int] = None
    daily_rate: float
    security_deposit: Optional[float] = 0.0
    location: str
    description: Optional[str] = None
    weight: Optional[float] = None

class EquipmentBookPayload(BaseModel):
    start_date: date
    end_date: date
    location: str
    job_type: Optional[str] = "Warehouse Loading & Unloading"
    description: Optional[str] = None

class EquipmentJobStatusPayload(BaseModel):
    status: str  # approved, in_progress, completed, cancelled

@router.get("/equipment-owner/dashboard", response_class=HTMLResponse)
def equipment_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    equipment = db.query(Equipment).all()
    jobs = db.query(EquipmentJob).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboards/equipment.html",
        context={"user": user, "equipment": equipment, "jobs": jobs}
    )

@router.get("/equipment", response_class=HTMLResponse)
def equipment_list(request: Request, db: Session = Depends(get_db)):
    return equipment_dashboard(request, db)

# =========================================================================
# HEAVY EQUIPMENT REST API
# =========================================================================

@router.get("/api/equipment/overview")
def get_equipment_overview(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    equipment = db.query(Equipment).filter(
        (Equipment.user_id == user.id) | (Equipment.owner_id == user.id)
    ).all()
    if not equipment and user.is_admin:
        equipment = db.query(Equipment).all()

    eq_ids = [eq.id for eq in equipment]
    jobs = []
    if eq_ids:
        jobs = db.query(EquipmentJob).filter(EquipmentJob.equipment_id.in_(eq_ids)).order_by(EquipmentJob.id.desc()).all()

    monthly_revenue = sum(float(job.amount or job.price or 0) for job in jobs if job.status == "completed")

    return {
        "status": "success",
        "counts": {
            "total_machinery": len(equipment),
            "available_units": len([e for e in equipment if e.status == "available"]),
            "active_leases": len([j for j in jobs if j.status in ("approved", "in_progress", "active")]),
            "completed_jobs": len([j for j in jobs if j.status == "completed"])
        },
        "monthly_revenue": monthly_revenue,
        "equipment": [
            {
                "id": eq.id,
                "name": eq.name,
                "type": eq.type,
                "model": eq.model,
                "daily_rate": float(eq.daily_rate or 0),
                "security_deposit": float(eq.security_deposit or 0),
                "location": eq.location,
                "status": eq.status,
                "description": eq.description
            } for eq in equipment
        ],
        "jobs": [
            {
                "id": j.id,
                "equipment_id": j.equipment_id,
                "equipment_name": j.equipment.name if j.equipment else "Heavy Machinery",
                "client_id": j.client_id,
                "location": j.location,
                "start_date": j.start_date.isoformat() if j.start_date else None,
                "end_date": j.end_date.isoformat() if j.end_date else None,
                "amount": float(j.amount or j.price or 0),
                "status": j.status
            } for j in jobs
        ]
    }

@router.post("/api/equipment")
def create_equipment(payload: EquipmentCreatePayload, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    eq = Equipment(
        user_id=user.id,
        owner_id=user.id,
        name=payload.name,
        type=payload.type,
        model=payload.model,
        year=payload.year or datetime.now().year,
        daily_rate=payload.daily_rate,
        security_deposit=payload.security_deposit or 0.0,
        location=payload.location,
        description=payload.description,
        weight=payload.weight,
        status="available"
    )
    db.add(eq)
    db.commit()
    db.refresh(eq)

    return {
        "status": "success",
        "message": f"Heavy machinery '{eq.name}' registered to fleet catalog",
        "equipment": {
            "id": eq.id,
            "name": eq.name,
            "type": eq.type,
            "daily_rate": float(eq.daily_rate or 0),
            "status": eq.status
        }
    }

@router.post("/api/equipment/{equipment_id}/book")
def book_equipment(equipment_id: int, payload: EquipmentBookPayload, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    eq = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment machinery not found")

    days = max(1, (payload.end_date - payload.start_date).days)
    total_amount = float(eq.daily_rate or 0) * days

    job = EquipmentJob(
        equipment_id=eq.id,
        owner_id=eq.owner_id or eq.user_id,
        client_id=user.id,
        job_type=payload.job_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        location=payload.location,
        description=payload.description,
        price=total_amount,
        amount=total_amount,
        status="approved"
    )
    db.add(job)

    # Also log an equipment request
    eq_req = EquipmentRequest(
        client_id=user.id,
        equipment_id=eq.id,
        equipment_type=eq.type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        location=payload.location,
        description=payload.description,
        quoted_price=total_amount,
        status="approved"
    )
    db.add(eq_req)

    # Update equipment status to rented
    eq.status = "rented"

    db.commit()
    db.refresh(job)

    return {
        "status": "success",
        "message": f"Machinery booking confirmed for {days} days at Rs. {total_amount:,.2f}",
        "job": {
            "id": job.id,
            "equipment_name": eq.name,
            "days": days,
            "total_amount": total_amount,
            "status": job.status
        }
    }

@router.patch("/api/equipment/jobs/{job_id}/status")
def update_equipment_job_status(job_id: int, payload: EquipmentJobStatusPayload, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    job = db.query(EquipmentJob).filter(EquipmentJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Equipment job not found")

    target_status = payload.status.lower()
    job.status = target_status

    if target_status == "completed" and job.equipment:
        job.equipment.status = "available"
        job.completed_at = datetime.utcnow()
    elif target_status in ("approved", "in_progress") and job.equipment:
        job.equipment.status = "rented"

    db.commit()

    return {
        "status": "success",
        "message": f"Equipment job #{job.id} status updated to '{target_status}'",
        "job": {
            "id": job.id,
            "status": job.status
        }
    }
