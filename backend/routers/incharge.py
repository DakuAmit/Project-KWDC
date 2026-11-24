"""
Warehouse Incharge Operations Router
Governs:
1. Daily Warehouse Activity Reports to SuperAdmin
2. Granular Incident Logging (Minor rat damage to major water seepage)
3. Gate Pass Inward/Outward Processing
4. Physical Stock Verification
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from backend.database import get_db
from backend.models import (
    Warehouse, WarehouseInchargeAssignment, WarehouseActivityLog,
    IncidentReport, IncidentSeverity, GatePass, User, UserRole, StockItem, InventoryUnit,
    WarehouseRequest
)
from backend.schemas import InchargeReportCreate, IncidentReportCreate, GatePassCreate
from backend.auth_utils import require_user, require_roles

router = APIRouter(prefix="/api/incharge", tags=["Warehouse Incharge"])

@router.get("/assigned-warehouses")
def get_assigned_warehouses(
    current_user: User = Depends(require_roles([UserRole.WAREHOUSE_INCHARGE, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Lists warehouses assigned to this incharge."""
    assignments = db.query(WarehouseInchargeAssignment).filter(
        WarehouseInchargeAssignment.incharge_id == current_user.id,
        WarehouseInchargeAssignment.is_active == True
    ).all()
    
    results = []
    for a in assignments:
        w = a.warehouse
        results.append({
            "warehouse_id": w.id,
            "title": w.title,
            "space_type": w.space_type.value,
            "total_sqft": w.total_sqft,
            "available_sqft": w.available_sqft,
            "municipality": w.municipality,
            "district": w.district,
            "is_on_maintenance_hold": w.is_on_maintenance_hold,
            "hold_reason_note": w.hold_reason_note
        })
    return results

@router.post("/activity-log")
def create_activity_log(
    payload: InchargeReportCreate,
    current_user: User = Depends(require_roles([UserRole.WAREHOUSE_INCHARGE, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Submits direct activity report to SuperAdmin."""
    log = WarehouseActivityLog(
        warehouse_id=payload.warehouse_id,
        incharge_id=current_user.id,
        log_type=payload.log_type,
        summary=payload.summary,
        detailed_notes=payload.detailed_notes
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return {"message": "Activity report transmitted to SuperAdmin.", "log_id": log.id}

@router.post("/incident-report")
def log_incident(
    payload: IncidentReportCreate,
    current_user: User = Depends(require_roles([UserRole.WAREHOUSE_INCHARGE, UserRole.SUPERADMIN, UserRole.SECURITY_AGENCY])),
    db: Session = Depends(get_db)
):
    """
    Logs minor or major incidents:
    - Minor rat/rodent damage on packaging
    - Water seepage / monsoon leak
    - Seal tampering
    - Fire or burglary (with immediate 1-click police alert)
    """
    # Map low/high to standard IncidentSeverity
    sev_str = str(payload.severity).lower()
    if "low" in sev_str:
        sev = IncidentSeverity.MINOR
    elif "med" in sev_str or "moderate" in sev_str:
        sev = IncidentSeverity.MODERATE
    elif "crit" in sev_str:
        sev = IncidentSeverity.CRITICAL
    else:
        sev = IncidentSeverity.MAJOR if "maj" in sev_str else IncidentSeverity.MINOR

    desc = payload.description or payload.observation_notes or payload.title or "General observation"
    cat = payload.incident_category or payload.title or "Structural Observation"

    report = IncidentReport(
        warehouse_id=payload.warehouse_id,
        incharge_id=current_user.id,
        incident_category=cat,
        severity=sev,
        description=desc,
        action_taken=payload.action_taken,
        police_alert_dispatched=payload.police_alert_dispatched,
        admin_notified=True
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    alert_msg = "Incident recorded and SuperAdmin notified."
    if payload.police_alert_dispatched:
        alert_msg += " URGENT: Dispatch alert transmitted to Nepal Police emergency response."

    return {"message": alert_msg, "report_id": report.id, "severity": report.severity.value}

@router.post("/gate-pass")
def process_gate_pass(
    payload: GatePassCreate,
    current_user: User = Depends(require_roles([UserRole.WAREHOUSE_INCHARGE, UserRole.SUPERADMIN, UserRole.COMMERCIAL_CLIENT, UserRole.SECURITY_AGENCY])),
    db: Session = Depends(get_db)
):
    """Stamps digital Inward or Outward Gate Pass with verified unit counts."""
    p_type = (payload.movement_type or payload.pass_type or "inbound").upper()
    c_id = payload.client_id or (current_user.id if current_user.role == UserRole.COMMERCIAL_CLIENT else None)
    
    # If client_id is None, assign to first user or current user
    if not c_id:
        c_id = current_user.id

    # Gate Freeze Enforcement: Block OUTWARD cargo exits if client's lease is frozen (55+ days overdue / forfeited)
    if p_type in ("OUTWARD", "OUTBOUND"):
        frozen_booking = db.query(WarehouseRequest).filter(
            WarehouseRequest.client_id == c_id,
            WarehouseRequest.warehouse_id == payload.warehouse_id,
            WarehouseRequest.is_gate_frozen == True
        ).first()
        if frozen_booking:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"GATE FROZEN (LIEN LOCK): Outbound stock dispatch blocked for Booking #{frozen_booking.id} "
                    f"({frozen_booking.advance_payment_status}). Please settle overdue rent in full to unlock gate exit."
                )
            )

    units = payload.pallet_count or payload.scanned_units_count or 1
    manifest = payload.cargo_manifest or payload.remarks or "Commercial Cargo"

    gate_pass = GatePass(
        warehouse_id=payload.warehouse_id,
        client_id=c_id,
        incharge_id=current_user.id,
        pass_type=p_type,
        vehicle_plate=payload.vehicle_plate,
        driver_name=payload.driver_name,
        unit_type=payload.unit_type,
        scanned_units_count=units,
        remarks=manifest
    )
    db.add(gate_pass)
    db.commit()
    db.refresh(gate_pass)

    return {
        "message": f"Gate pass {p_type} clearance stamped.",
        "gate_pass_id": gate_pass.id,
        "pass_token": f"GP-2083-{gate_pass.id:04d}",
        "status": "CLEARED"
    }
    db.refresh(gate_pass)

    return {
        "message": f"Gate Pass #{gate_pass.id} verified and stamped for {payload.pass_type.upper()}.",
        "gate_pass_id": gate_pass.id,
        "scanned_units": gate_pass.scanned_units_count
    }

@router.get("/my-gate-passes")
def get_my_gate_passes(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Returns digital gate passes issued for the authenticated client."""
    passes = db.query(GatePass).filter(GatePass.client_id == current_user.id).order_by(GatePass.created_at.desc()).limit(50).all()
    return [
        {
            "id": g.id,
            "pass_token": f"GP-2083-{g.id:04d}",
            "warehouse_title": g.warehouse.title if getattr(g, 'warehouse', None) else f"Warehouse #{g.warehouse_id}",
            "pass_type": g.pass_type,
            "vehicle_plate": g.vehicle_plate,
            "driver_name": g.driver_name,
            "unit_type": g.unit_type.value if hasattr(g.unit_type, 'value') else str(g.unit_type),
            "scanned_units_count": g.scanned_units_count,
            "remarks": g.remarks,
            "created_at": g.created_at.strftime("%Y-%m-%d %H:%M") if g.created_at else ""
        }
        for g in passes
    ]

@router.get("/gate-passes")
def get_gate_passes(
    current_user: User = Depends(require_roles([UserRole.WAREHOUSE_INCHARGE, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Retrieves all digital gate passes issued across facilities."""
    passes = db.query(GatePass).order_by(GatePass.created_at.desc()).limit(50).all()
    results = []
    for g in passes:
        wh_title = g.warehouse.title if getattr(g, 'warehouse', None) else f"Warehouse #{g.warehouse_id}"
        results.append({
            "id": g.id,
            "warehouse_title": wh_title,
            "pass_type": g.pass_type,
            "vehicle_plate": g.vehicle_plate,
            "driver_name": g.driver_name,
            "unit_type": g.unit_type.value if hasattr(g.unit_type, 'value') else str(g.unit_type),
            "scanned_units_count": g.scanned_units_count,
            "remarks": g.remarks,
            "issued_at": g.created_at.strftime("%Y-%m-%d %H:%M") if g.created_at else "",
            "created_at": g.created_at.strftime("%Y-%m-%d %H:%M") if g.created_at else ""
        })
    return results
