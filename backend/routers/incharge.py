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
    IncidentReport, IncidentSeverity, GatePass, User, UserRole, StockItem, StockMovementLog,
    InventoryUnit, WarehouseRequest, WarehousePhoto
)
from backend.schemas import (
    InchargeReportCreate, IncidentReportCreate, GatePassCreate,
    InchargeStockVerifyRequest, WarehouseMediaDetailsUpdate
)
from backend.auth_utils import require_user, require_roles

router = APIRouter(prefix="/api/incharge", tags=["Warehouse Incharge"])

@router.get("/assigned-warehouses")
def get_assigned_warehouses(
    current_user: User = Depends(require_roles([UserRole.WAREHOUSE_INCHARGE, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Lists warehouses assigned to this incharge along with inspection details, photos, and walkthrough videos."""
    assignments = db.query(WarehouseInchargeAssignment).filter(
        WarehouseInchargeAssignment.incharge_id == current_user.id,
        WarehouseInchargeAssignment.is_active == True
    ).all()
    audited_whs = db.query(Warehouse).filter(
        Warehouse.audited_by_incharge_id == current_user.id
    ).all()

    wh_by_id = {}
    for a in assignments:
        if a.warehouse:
            wh_by_id[a.warehouse.id] = a.warehouse
    for w in audited_whs:
        wh_by_id[w.id] = w

    results = []
    for w in wh_by_id.values():
        results.append({
            "id": w.id,
            "warehouse_id": w.id,
            "title": w.title,
            "space_type": w.space_type.value if hasattr(w.space_type, "value") else str(w.space_type),
            "total_sqft": w.total_sqft,
            "available_sqft": w.available_sqft,
            "municipality": w.municipality,
            "district": w.district,
            "is_on_maintenance_hold": bool(w.is_on_maintenance_hold),
            "hold_reason_note": w.hold_reason_note,
            "physical_audit_status": w.physical_audit_status.value if hasattr(w.physical_audit_status, "value") else str(w.physical_audit_status or "PENDING_INSPECTION"),
            "physical_audit_notes": w.physical_audit_notes,
            "clear_ceiling_height_ft": float(w.clear_ceiling_height_ft or 0.0),
            "road_access_ft": float(w.road_access_ft or 0.0),
            "has_three_phase_power": bool(w.has_three_phase_power),
            "has_forklift_ramp": bool(w.has_forklift_ramp),
            "has_cctv": bool(w.has_cctv),
            "has_cold_storage": bool(w.has_cold_storage),
            "photos": [p.photo_url for p in (w.photos or []) if p.photo_url],
            "video_urls": [v.strip() for v in (getattr(w, "video_urls", None) or "").split(",") if v.strip()],
        })
    return results


@router.post("/warehouses/{warehouse_id}/media-details")
def add_incharge_warehouse_media_and_details(
    warehouse_id: int,
    payload: WarehouseMediaDetailsUpdate,
    current_user: User = Depends(require_roles([UserRole.WAREHOUSE_INCHARGE, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """
    Allows an assigned Warehouse Incharge to upload on-site inspection photos, walkthrough videos,
    and update verified physical inspection details for their assigned warehouse.
    """
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found.")

    if current_user.role != UserRole.SUPERADMIN:
        has_assignment = db.query(WarehouseInchargeAssignment).filter(
            WarehouseInchargeAssignment.incharge_id == current_user.id,
            WarehouseInchargeAssignment.warehouse_id == warehouse_id,
            WarehouseInchargeAssignment.is_active == True
        ).first() is not None
        is_inspector = (warehouse.audited_by_incharge_id == current_user.id)
        if not has_assignment and not is_inspector:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not assigned to this warehouse facility."
            )

    existing_photos = {p.photo_url for p in (warehouse.photos or []) if p.photo_url}
    photos_added = 0
    for p_url in (payload.photo_urls or []):
        clean = (p_url or "").strip()
        if clean and clean not in existing_photos:
            db.add(WarehousePhoto(
                warehouse_id=warehouse.id,
                photo_url=clean,
                caption=(payload.caption or f"Incharge On-Site Inspection ({current_user.full_name})").strip()[:250]
            ))
            existing_photos.add(clean)
            photos_added += 1

    existing_videos = [v.strip() for v in (getattr(warehouse, "video_urls", None) or "").split(",") if v.strip()]
    videos_added = 0
    for v_url in (payload.video_urls or []):
        clean = (v_url or "").strip()
        if clean and clean not in existing_videos:
            existing_videos.append(clean)
            videos_added += 1
    warehouse.video_urls = ",".join(existing_videos) if existing_videos else None

    if payload.audit_notes is not None and payload.audit_notes.strip():
        warehouse.physical_audit_notes = payload.audit_notes.strip()
    if payload.physical_audit_status is not None:
        warehouse.physical_audit_status = payload.physical_audit_status
    if payload.clear_ceiling_height_ft is not None:
        warehouse.clear_ceiling_height_ft = float(payload.clear_ceiling_height_ft)
    if payload.road_access_ft is not None:
        warehouse.road_access_ft = float(payload.road_access_ft)
    if payload.has_three_phase_power is not None:
        warehouse.has_three_phase_power = bool(payload.has_three_phase_power)
    if payload.has_forklift_ramp is not None:
        warehouse.has_forklift_ramp = bool(payload.has_forklift_ramp)
    if payload.has_cctv is not None:
        warehouse.has_cctv = bool(payload.has_cctv)
    if payload.has_cold_storage is not None:
        warehouse.has_cold_storage = bool(payload.has_cold_storage)

    warehouse.audited_by_incharge_id = warehouse.audited_by_incharge_id or current_user.id
    warehouse.audited_at = datetime.now(timezone.utc)

    db.add(WarehouseActivityLog(
        warehouse_id=warehouse.id,
        incharge_id=current_user.id,
        log_type="PHYSICAL_MEDIA_UPDATE",
        summary=f"Incharge added {photos_added} photo(s), {videos_added} video(s) & updated specs",
        detailed_notes=payload.audit_notes or payload.caption or "On-site physical inspection media and specifications uploaded."
    ))

    db.commit()
    db.refresh(warehouse)
    all_photos = [p.photo_url for p in (warehouse.photos or []) if p.photo_url]
    return {
        "message": f"Updated inspection media & details for '{warehouse.title}' ({photos_added} photo(s), {videos_added} video(s)).",
        "warehouse_id": warehouse.id,
        "photos_added": photos_added,
        "videos_added": videos_added,
        "photos": all_photos,
        "video_urls": existing_videos,
        "physical_audit_status": warehouse.physical_audit_status.value if hasattr(warehouse.physical_audit_status, "value") else str(warehouse.physical_audit_status),
        "physical_audit_notes": warehouse.physical_audit_notes,
        "clear_ceiling_height_ft": warehouse.clear_ceiling_height_ft,
        "road_access_ft": warehouse.road_access_ft,
    }

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
        stock_item_id=payload.stock_item_id,
        booking_id=payload.booking_id,
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

    # Sync StockItem & StockMovementLog when linked to a specific SKU batch
    if payload.stock_item_id:
        stock = db.query(StockItem).filter(StockItem.id == payload.stock_item_id).first()
        if stock:
            if p_type in ("INWARD", "INBOUND"):
                stock.total_quantity = int(stock.total_quantity or 0) + units
                stock.verification_status = "VERIFIED_IN_STORAGE"
                db.add(StockMovementLog(
                    stock_item_id=stock.id,
                    booking_id=stock.booking_id,
                    warehouse_id=stock.warehouse_id,
                    client_id=stock.client_id,
                    actor_user_id=current_user.id,
                    movement_type="INWARD_VERIFIED",
                    quantity_delta=units,
                    balance_after=stock.total_quantity,
                    gate_pass_id=gate_pass.id,
                    remarks=f"Inward Gate Pass GP-2083-{gate_pass.id:04d} cleared ({payload.vehicle_plate})."
                ))
            elif p_type in ("OUTWARD", "OUTBOUND"):
                reserved = int(getattr(stock, "reserved_quantity", 0) or 0)
                if reserved >= units:
                    stock.reserved_quantity = reserved - units
                else:
                    remainder = units - reserved
                    stock.reserved_quantity = 0
                    stock.total_quantity = max(0, int(stock.total_quantity or 0) - remainder)
                stock.dispatched_quantity = int(getattr(stock, "dispatched_quantity", 0) or 0) + units
                db.add(StockMovementLog(
                    stock_item_id=stock.id,
                    booking_id=stock.booking_id,
                    warehouse_id=stock.warehouse_id,
                    client_id=stock.client_id,
                    actor_user_id=current_user.id,
                    movement_type="OUTWARD_DISPATCHED",
                    quantity_delta=-units,
                    balance_after=int(stock.total_quantity or 0),
                    gate_pass_id=gate_pass.id,
                    remarks=f"Outward Gate Pass GP-2083-{gate_pass.id:04d} dispatched via {payload.vehicle_plate}."
                ))
            db.commit()

    return {
        "message": f"Gate pass {p_type} clearance stamped.",
        "gate_pass_id": gate_pass.id,
        "pass_token": f"GP-2083-{gate_pass.id:04d}",
        "scanned_units": gate_pass.scanned_units_count,
        "status": "CLEARED"
    }


@router.get("/my-logs")
def get_incharge_own_logs(
    current_user: User = Depends(require_roles([UserRole.WAREHOUSE_INCHARGE, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Returns shift activity logs visible to the Warehouse Incharge without requiring SuperAdmin role."""
    q = db.query(WarehouseActivityLog).order_by(WarehouseActivityLog.created_at.desc())
    if current_user.role != UserRole.SUPERADMIN:
        assigned_wh_ids = [
            a.warehouse_id
            for a in db.query(WarehouseInchargeAssignment).filter(
                WarehouseInchargeAssignment.incharge_id == current_user.id,
                WarehouseInchargeAssignment.is_active == True
            ).all()
        ]
        if assigned_wh_ids:
            q = q.filter(
                (WarehouseActivityLog.incharge_id == current_user.id) |
                (WarehouseActivityLog.warehouse_id.in_(assigned_wh_ids))
            )
        else:
            q = q.filter(WarehouseActivityLog.incharge_id == current_user.id)
    logs = q.limit(50).all()
    return [
        {
            "id": l.id,
            "warehouse_id": l.warehouse_id,
            "log_type": l.log_type,
            "summary": l.summary,
            "detailed_notes": l.detailed_notes,
            "admin_reviewed": bool(l.admin_reviewed),
            "timestamp": l.created_at.strftime("%Y-%m-%d %H:%M") if l.created_at else "",
            "created_at": l.created_at.strftime("%Y-%m-%d %H:%M") if l.created_at else ""
        }
        for l in logs
    ]


@router.get("/stock-queue")
def get_incharge_stock_queue(
    current_user: User = Depends(require_roles([UserRole.WAREHOUSE_INCHARGE, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Lists client stock batches across assigned warehouses for Incharge physical dock verification & outward confirmation."""
    q = db.query(StockItem).order_by(StockItem.updated_at.desc())
    if current_user.role != UserRole.SUPERADMIN:
        assigned_wh_ids = [
            a.warehouse_id
            for a in db.query(WarehouseInchargeAssignment).filter(
                WarehouseInchargeAssignment.incharge_id == current_user.id,
                WarehouseInchargeAssignment.is_active == True
            ).all()
        ]
        if assigned_wh_ids:
            q = q.filter(StockItem.warehouse_id.in_(assigned_wh_ids))
        else:
            return []
    items = q.limit(100).all()
    return [
        {
            "id": s.id,
            "sku_code": s.sku_code,
            "item_name": s.item_name,
            "warehouse_id": s.warehouse_id,
            "warehouse_title": s.warehouse.title if s.warehouse else f"Warehouse #{s.warehouse_id}",
            "client_id": s.client_id,
            "unit_type": s.unit_type.value if hasattr(s.unit_type, "value") else str(s.unit_type),
            "total_quantity": int(s.total_quantity or 0),
            "reserved_quantity": int(getattr(s, "reserved_quantity", 0) or 0),
            "dispatched_quantity": int(getattr(s, "dispatched_quantity", 0) or 0),
            "verification_status": getattr(s, "verification_status", "PENDING_DOCK_VERIFICATION"),
            "bay_rack_location": getattr(s, "bay_rack_location", "Zone A / Bay-1"),
        }
        for s in items
    ]


@router.post("/stock/{stock_item_id}/verify")
def incharge_verify_stock_batch(
    stock_item_id: int,
    payload: InchargeStockVerifyRequest,
    current_user: User = Depends(require_roles([UserRole.WAREHOUSE_INCHARGE, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Incharge physically verifies an inward SKU batch, assigns Bay/Rack zone, or clears reserved outward dispatch."""
    s = db.query(StockItem).filter(StockItem.id == stock_item_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Stock item not found.")

    if payload.bay_rack_location:
        s.bay_rack_location = payload.bay_rack_location.strip()
        for u in s.units:
            u.bay_rack_location = s.bay_rack_location

    if payload.verified_quantity is not None and payload.verified_quantity >= 0:
        s.total_quantity = int(payload.verified_quantity)

    reserved = int(getattr(s, "reserved_quantity", 0) or 0)
    if reserved > 0:
        s.dispatched_quantity = int(getattr(s, "dispatched_quantity", 0) or 0) + reserved
        s.reserved_quantity = 0
        mv_type = "OUTWARD_DISPATCHED"
        delta = -reserved
        msg = f"Cleared {reserved} reserved units outward for {s.sku_code}."
    else:
        s.verification_status = "VERIFIED_IN_STORAGE"
        mv_type = "INWARD_VERIFIED"
        delta = 0
        msg = f"Physically verified {s.sku_code} at {s.bay_rack_location}."

    db.add(StockMovementLog(
        stock_item_id=s.id,
        booking_id=s.booking_id,
        warehouse_id=s.warehouse_id,
        client_id=s.client_id,
        actor_user_id=current_user.id,
        movement_type=mv_type,
        quantity_delta=delta,
        balance_after=int(s.total_quantity or 0),
        remarks=payload.notes or msg
    ))
    db.commit()
    return {"message": msg, "verification_status": s.verification_status, "bay_rack_location": s.bay_rack_location}

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
