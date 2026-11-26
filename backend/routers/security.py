"""
Kathmandu Warehousing & Distribution Center (KTM-WDC)
Security Agency & Guard Roster Operations Router
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    User, UserRole, Warehouse, SecurityAgency, GuardPersonnel,
    SecurityPatrolLog, IncidentReport
)
from backend.schemas import (
    SecurityAgencyProfileCreate, SecurityGuardCreate, SecurityPatrolLogCreate
)
from backend.auth_utils import require_roles

router = APIRouter(prefix="/api/security", tags=["Security Agency Operations"])


def _get_or_404_agency(db: Session, user: User):
    return db.query(SecurityAgency).filter(SecurityAgency.user_id == user.id).first()


@router.get("/dashboard")
def get_security_dashboard(
    current_user: User = Depends(require_roles([UserRole.SECURITY_AGENCY, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    agency = _get_or_404_agency(db, current_user)
    warehouses = db.query(Warehouse).filter(Warehouse.is_approved == True).order_by(Warehouse.title.asc()).all()
    if not agency and current_user.role == UserRole.SUPERADMIN:
        guards = db.query(GuardPersonnel).order_by(GuardPersonnel.id.desc()).all()
        patrols = db.query(SecurityPatrolLog).order_by(SecurityPatrolLog.logged_at.desc()).limit(40).all()
    elif agency:
        guards = db.query(GuardPersonnel).filter(GuardPersonnel.agency_id == agency.id).order_by(GuardPersonnel.id.desc()).all()
        patrols = db.query(SecurityPatrolLog).filter(SecurityPatrolLog.agency_id == agency.id).order_by(SecurityPatrolLog.logged_at.desc()).limit(40).all()
    else:
        guards = []
        patrols = []

    guard_ids = [g.id for g in guards]
    incidents = (
        db.query(IncidentReport)
        .order_by(IncidentReport.created_at.desc())
        .limit(25)
        .all()
    )
    if agency and guard_ids:
        assigned_wh_ids = {g.assigned_warehouse_id for g in guards if g.assigned_warehouse_id}
        incidents = [i for i in incidents if (i.guard_id in guard_ids) or (i.warehouse_id in assigned_wh_ids)]

    wh_map = {w.id: w.title for w in db.query(Warehouse).all()}
    guard_map = {g.id: g.guard_name for g in guards}

    return {
        "user": {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "email": current_user.email,
            "phone_number": current_user.phone_number,
        },
        "agency": {
            "id": agency.id,
            "agency_name": agency.agency_name,
            "home_ministry_license_no": agency.home_ministry_license_no,
            "emergency_contact_phone": agency.emergency_contact_phone,
            "is_verified": bool(agency.is_verified),
            "created_at": agency.created_at.strftime("%Y-%m-%d") if agency.created_at else "",
        } if agency else None,
        "guards": [
            {
                "id": g.id,
                "guard_name": g.guard_name,
                "phone_number": g.phone_number,
                "assigned_warehouse_id": g.assigned_warehouse_id,
                "assigned_warehouse_title": wh_map.get(g.assigned_warehouse_id, "Unassigned") if g.assigned_warehouse_id else "Unassigned",
                "shift_type": g.shift_type,
                "is_active": bool(g.is_active),
            }
            for g in guards
        ],
        "patrol_logs": [
            {
                "id": p.id,
                "warehouse_id": p.warehouse_id,
                "warehouse_title": wh_map.get(p.warehouse_id, f"Facility #{p.warehouse_id}"),
                "guard_id": p.guard_id,
                "guard_name": guard_map.get(p.guard_id, "Station Supervisor") if p.guard_id else "Station Supervisor",
                "shift_type": p.shift_type,
                "perimeter_status": p.perimeter_status,
                "notes": p.notes,
                "photo_url": p.photo_url,
                "logged_at": p.logged_at.strftime("%Y-%m-%d %H:%M") if p.logged_at else "",
            }
            for p in patrols
        ],
        "incidents": [
            {
                "id": inc.id,
                "warehouse_id": inc.warehouse_id,
                "warehouse_title": wh_map.get(inc.warehouse_id, f"Facility #{inc.warehouse_id}"),
                "category": inc.incident_category,
                "severity": inc.severity.value if hasattr(inc.severity, "value") else str(inc.severity),
                "description": inc.description,
                "police_alert_dispatched": bool(inc.police_alert_dispatched),
                "created_at": inc.created_at.strftime("%Y-%m-%d %H:%M") if inc.created_at else "",
            }
            for inc in incidents
        ],
        "warehouses": [
            {"id": w.id, "title": w.title, "city": w.municipality or w.district}
            for w in warehouses
        ],
    }


@router.post("/agency-profile")
def upsert_agency_profile(
    payload: SecurityAgencyProfileCreate,
    current_user: User = Depends(require_roles([UserRole.SECURITY_AGENCY, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    lic = payload.home_ministry_license_no.strip()
    existing_lic = db.query(SecurityAgency).filter(
        SecurityAgency.home_ministry_license_no == lic,
        SecurityAgency.user_id != current_user.id
    ).first()
    if existing_lic:
        raise HTTPException(status_code=400, detail="Home Ministry License Number already registered.")

    agency = _get_or_404_agency(db, current_user)
    if not agency:
        agency = SecurityAgency(
            user_id=current_user.id,
            agency_name=payload.agency_name.strip(),
            home_ministry_license_no=lic,
            emergency_contact_phone=payload.emergency_contact_phone.strip(),
            is_verified=False,
        )
        db.add(agency)
    else:
        agency.agency_name = payload.agency_name.strip()
        agency.home_ministry_license_no = lic
        agency.emergency_contact_phone = payload.emergency_contact_phone.strip()

    db.commit()
    db.refresh(agency)
    return {
        "message": "Security Agency profile saved and submitted for SuperAdmin license verification.",
        "agency_id": agency.id,
        "is_verified": agency.is_verified,
    }


@router.get("/guards")
def list_agency_guards(
    current_user: User = Depends(require_roles([UserRole.SECURITY_AGENCY, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    agency = _get_or_404_agency(db, current_user)
    if not agency and current_user.role != UserRole.SUPERADMIN:
        return []
    q = db.query(GuardPersonnel)
    if agency:
        q = q.filter(GuardPersonnel.agency_id == agency.id)
    guards = q.order_by(GuardPersonnel.id.desc()).all()
    wh_map = {w.id: w.title for w in db.query(Warehouse).all()}
    return [
        {
            "id": g.id,
            "guard_name": g.guard_name,
            "phone_number": g.phone_number,
            "assigned_warehouse_id": g.assigned_warehouse_id,
            "assigned_warehouse_title": wh_map.get(g.assigned_warehouse_id, "Unassigned") if g.assigned_warehouse_id else "Unassigned",
            "shift_type": g.shift_type,
            "is_active": bool(g.is_active),
        }
        for g in guards
    ]


@router.post("/guards")
def create_security_guard(
    payload: SecurityGuardCreate,
    current_user: User = Depends(require_roles([UserRole.SECURITY_AGENCY, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    agency = _get_or_404_agency(db, current_user)
    if not agency:
        raise HTTPException(status_code=400, detail="Please register your Security Agency profile & Home Ministry license first.")

    if payload.assigned_warehouse_id:
        wh = db.query(Warehouse).filter(Warehouse.id == payload.assigned_warehouse_id).first()
        if not wh:
            raise HTTPException(status_code=404, detail="Assigned warehouse facility not found.")

    guard = GuardPersonnel(
        agency_id=agency.id,
        guard_name=payload.guard_name.strip(),
        phone_number=payload.phone_number.strip(),
        assigned_warehouse_id=payload.assigned_warehouse_id,
        shift_type=payload.shift_type.upper(),
        is_active=True,
    )
    db.add(guard)
    db.commit()
    db.refresh(guard)
    return {
        "message": f"Guard {guard.guard_name} added to active security roster.",
        "guard_id": guard.id,
        "shift_type": guard.shift_type,
    }


@router.post("/guards/{guard_id}/assign-warehouse")
def assign_guard_warehouse(
    guard_id: int,
    payload: dict,
    current_user: User = Depends(require_roles([UserRole.SECURITY_AGENCY, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    guard = db.query(GuardPersonnel).filter(GuardPersonnel.id == guard_id).first()
    if not guard:
        raise HTTPException(status_code=404, detail="Guard record not found.")

    if current_user.role == UserRole.SECURITY_AGENCY:
        agency = _get_or_404_agency(db, current_user)
        if not agency or guard.agency_id != agency.id:
            raise HTTPException(status_code=403, detail="Unauthorized to reassign guard outside your agency.")

    wh_id = payload.get("warehouse_id")
    if wh_id is not None:
        wh = db.query(Warehouse).filter(Warehouse.id == int(wh_id)).first()
        if not wh:
            raise HTTPException(status_code=404, detail="Target warehouse not found.")
        guard.assigned_warehouse_id = wh.id

    if payload.get("shift_type"):
        guard.shift_type = str(payload["shift_type"]).upper()
    if "is_active" in payload:
        guard.is_active = bool(payload["is_active"])

    db.commit()
    return {
        "message": f"Guard {guard.guard_name} deployment updated.",
        "assigned_warehouse_id": guard.assigned_warehouse_id,
        "shift_type": guard.shift_type,
        "is_active": guard.is_active,
    }


@router.post("/patrol-log")
def create_patrol_log(
    payload: SecurityPatrolLogCreate,
    current_user: User = Depends(require_roles([UserRole.SECURITY_AGENCY, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    agency = _get_or_404_agency(db, current_user)
    if not agency:
        raise HTTPException(status_code=400, detail="Security Agency profile required before logging patrols.")

    wh = db.query(Warehouse).filter(Warehouse.id == payload.warehouse_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Warehouse facility not found.")

    log = SecurityPatrolLog(
        agency_id=agency.id,
        guard_id=payload.guard_id,
        warehouse_id=payload.warehouse_id,
        shift_type=payload.shift_type.upper(),
        perimeter_status=payload.perimeter_status.upper(),
        notes=payload.notes.strip(),
        photo_url=payload.photo_url,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return {
        "message": f"Perimeter patrol logged for {wh.title} ({log.perimeter_status}).",
        "patrol_id": log.id,
        "perimeter_status": log.perimeter_status,
    }
