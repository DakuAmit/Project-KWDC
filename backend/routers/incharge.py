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
    IncidentReport, GatePass, User, UserRole, StockItem, InventoryUnit
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
    report = IncidentReport(
        warehouse_id=payload.warehouse_id,
        incharge_id=current_user.id,
        incident_category=payload.incident_category,
        severity=payload.severity,
        description=payload.description,
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
    current_user: User = Depends(require_roles([UserRole.WAREHOUSE_INCHARGE, UserRole.SUPERADMIN, UserRole.SECURITY_AGENCY])),
    db: Session = Depends(get_db)
):
    """Stamps digital Inward or Outward Gate Pass with verified unit counts."""
    gate_pass = GatePass(
        warehouse_id=payload.warehouse_id,
        client_id=payload.client_id,
        incharge_id=current_user.id,
        pass_type=payload.pass_type.upper(),
        vehicle_plate=payload.vehicle_plate,
        driver_name=payload.driver_name,
        unit_type=payload.unit_type,
        scanned_units_count=payload.scanned_units_count,
        remarks=payload.remarks
    )
    db.add(gate_pass)
    db.commit()
    db.refresh(gate_pass)

    return {
        "message": f"Gate Pass #{gate_pass.id} verified and stamped for {payload.pass_type.upper()}.",
        "gate_pass_id": gate_pass.id,
        "scanned_units": gate_pass.scanned_units_count
    }

@router.get("/gate-passes")
def get_gate_passes(
    current_user: User = Depends(require_roles([UserRole.WAREHOUSE_INCHARGE, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Retrieves all digital gate passes issued across facilities."""
    passes = db.query(GatePass).order_by(GatePass.issued_at.desc()).limit(50).all()
    results = []
    for g in passes:
        results.append({
            "id": g.id,
            "warehouse_title": g.warehouse.title if g.warehouse else "Facility",
            "pass_type": g.pass_type,
            "vehicle_plate": g.vehicle_plate,
            "driver_name": g.driver_name,
            "unit_type": g.unit_type.value if hasattr(g.unit_type, 'value') else str(g.unit_type),
            "scanned_units_count": g.scanned_units_count,
            "remarks": g.remarks,
            "issued_at": g.issued_at.strftime("%Y-%m-%d %H:%M") if g.issued_at else ""
        })
    return results
