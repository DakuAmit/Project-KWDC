from datetime import datetime, date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.security_agency import SecurityAgency, SecurityPersonnel, SecurityAssignment, SecurityIncident
from app.models.warehouse import Warehouse
from app.models.finance import Invoice
from app.services.invoice_service import InvoiceService
from app.services.qr_service import QRService

router = APIRouter(tags=["Security Agency"])
from app.core.templates import templates

class GuardCreatePayload(BaseModel):
    name: str
    phone: str
    citizenship_no: str
    badge_id: str
    rank: Optional[str] = "Senior Guard"

class AssignmentCreatePayload(BaseModel):
    warehouse_id: int
    personnel_id: int
    shift_type: str = "day"  # day, night, 24h
    start_date: date
    end_date: Optional[date] = None

class IncidentCreatePayload(BaseModel):
    warehouse_id: int
    incident_type: str  # theft, fire, unauthorized_entry, perimeter_breach, damage
    severity: str = "medium"  # low, medium, high, critical
    description: str
    escalate_to_police: bool = False

class GuardingInvoicePayload(BaseModel):
    warehouse_id: int
    guards_count: int = 4
    monthly_rate_per_guard: float = 24000.0

@router.get("/security/dashboard", response_class=HTMLResponse)
def security_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    assignments = db.query(SecurityAssignment).all()
    incidents = db.query(SecurityIncident).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboards/security.html",
        context={"user": user, "assignments": assignments, "incidents": incidents}
    )

@router.get("/security/incidents", response_class=HTMLResponse)
def security_incidents(request: Request, db: Session = Depends(get_db)):
    return security_dashboard(request, db)

# =========================================================================
# LICENSED SECURITY AGENCY REST API (5 UML Use Cases)
# =========================================================================

@router.get("/api/security/overview")
def get_security_overview(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    agency = db.query(SecurityAgency).filter(SecurityAgency.user_id == user.id).first()
    if not agency and user.is_admin:
        agency = db.query(SecurityAgency).first()

    if not agency:
        # Create an agency profile if user is registered as security_agency
        agency = SecurityAgency(
            user_id=user.id,
            agency_name=f"{user.name} Protection Services Pvt Ltd",
            registration_number=f"REG-SEC-{user.id:04d}",
            license_number=f"MHA-SEC-2026-{user.id:03d}",
            address="Kathmandu Ring Road Security Command, Nepal",
            phone=user.phone or "9805556677",
            status="approved",
            is_verified=True
        )
        db.add(agency)
        db.commit()
        db.refresh(agency)

    personnel = db.query(SecurityPersonnel).filter(SecurityPersonnel.security_agency_id == agency.id).all()
    assignments = db.query(SecurityAssignment).filter(SecurityAssignment.security_agency_id == agency.id).all()
    incidents = db.query(SecurityIncident).filter(SecurityIncident.security_agency_id == agency.id).order_by(SecurityIncident.id.desc()).all()
    invoices = db.query(Invoice).filter(Invoice.order_type == "security_guarding").order_by(Invoice.id.desc()).limit(10).all()

    return {
        "status": "success",
        "agency": {
            "id": agency.id,
            "agency_name": agency.agency_name,
            "license_number": agency.license_number,
            "registration_number": agency.registration_number,
            "address": agency.address,
            "phone": agency.phone,
            "is_verified": agency.is_verified,
            "status": agency.status
        },
        "stats": {
            "total_guards": len(personnel),
            "guards_on_duty": len([p for p in personnel if p.status == "assigned"]),
            "active_posts": len([a for a in assignments if a.status == "active"]),
            "incidents_logged": len(incidents),
            "police_escalations": len([inc for inc in incidents if inc.police_station_notified])
        },
        "roster": [
            {
                "id": p.id,
                "name": p.name,
                "phone": p.phone,
                "citizenship_no": p.citizenship_no,
                "badge_id": p.badge_id,
                "rank": p.rank,
                "status": p.status
            } for p in personnel
        ],
        "assignments": [
            {
                "id": a.id,
                "warehouse_id": a.warehouse_id,
                "warehouse_name": a.warehouse.name if a.warehouse else "Warehouse Depot",
                "personnel_id": a.personnel_id,
                "guard_name": a.agency.personnel[0].name if a.agency and a.agency.personnel else "Security Officer",
                "shift_type": a.shift_type,
                "start_date": a.start_date.isoformat() if a.start_date else None,
                "end_date": a.end_date.isoformat() if a.end_date else None,
                "status": a.status
            } for a in assignments
        ],
        "incidents": [
            {
                "id": inc.id,
                "warehouse_id": inc.warehouse_id,
                "warehouse_name": inc.warehouse.name if inc.warehouse else "Commercial Post",
                "incident_type": inc.incident_type,
                "severity": inc.severity,
                "description": inc.description,
                "police_station_notified": inc.police_station_notified,
                "status": inc.status,
                "created_at": inc.created_at.strftime('%Y-%m-%d %H:%M') if inc.created_at else None
            } for inc in incidents
        ],
        "invoices": [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "subtotal": float(inv.subtotal or 0),
                "tax_amount": float(inv.tax_amount or 0),
                "grand_total": float(inv.grand_total or inv.amount or 0),
                "payment_status": inv.payment_status or "unpaid",
                "created_at": inv.created_at.strftime('%Y-%m-%d') if inv.created_at else None
            } for inv in invoices
        ]
    }

@router.post("/api/security/guards")
def add_guard_personnel(payload: GuardCreatePayload, request: Request, db: Session = Depends(get_db)):
    """Use Case 2: Manage Guard Personnel Roster (Badge/Rank)"""
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    agency = db.query(SecurityAgency).filter(SecurityAgency.user_id == user.id).first()
    if not agency and user.is_admin:
        agency = db.query(SecurityAgency).first()
    if not agency:
        raise HTTPException(status_code=404, detail="Security agency registration not found")

    guard = SecurityPersonnel(
        security_agency_id=agency.id,
        name=payload.name,
        phone=payload.phone,
        citizenship_no=payload.citizenship_no,
        badge_id=payload.badge_id,
        rank=payload.rank or "Senior Guard",
        status="available"
    )
    db.add(guard)
    db.commit()
    db.refresh(guard)

    return {
        "status": "success",
        "message": f"Officer '{guard.name}' added to security roster with Badge #{guard.badge_id}",
        "guard": {
            "id": guard.id,
            "name": guard.name,
            "badge_id": guard.badge_id,
            "rank": guard.rank,
            "status": guard.status
        }
    }

@router.post("/api/security/assignments")
def deploy_guards_to_post(payload: AssignmentCreatePayload, request: Request, db: Session = Depends(get_db)):
    """Use Case 3: Deploy Guards to Warehouse Posts <<include>> Configure Day/Night Shift Schedules"""
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    agency = db.query(SecurityAgency).filter(SecurityAgency.user_id == user.id).first()
    if not agency and user.is_admin:
        agency = db.query(SecurityAgency).first()
    if not agency:
        raise HTTPException(status_code=404, detail="Security agency profile not found")

    warehouse = db.query(Warehouse).filter(Warehouse.id == payload.warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse facility not found")

    guard = db.query(SecurityPersonnel).filter(SecurityPersonnel.id == payload.personnel_id).first()
    if not guard:
        raise HTTPException(status_code=404, detail="Guard personnel not found")

    shift_label = "Day Shift (06:00 - 18:00)" if payload.shift_type == "day" else "Night Shift (18:00 - 06:00)"

    assignment = SecurityAssignment(
        security_agency_id=agency.id,
        warehouse_id=warehouse.id,
        personnel_id=guard.id,
        shift_type=payload.shift_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status="active"
    )
    guard.status = "assigned"
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return {
        "status": "success",
        "message": f"Officer {guard.name} deployed to {warehouse.name} under {shift_label}",
        "assignment": {
            "id": assignment.id,
            "warehouse_name": warehouse.name,
            "guard_name": guard.name,
            "shift": payload.shift_type,
            "status": assignment.status
        }
    }

@router.post("/api/security/incidents")
def log_security_incident(payload: IncidentCreatePayload, request: Request, db: Session = Depends(get_db)):
    """Use Case 4: Log Security Incidents <<extend>> Escalate & Notify Local Nepal Police Post"""
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    agency = db.query(SecurityAgency).filter(SecurityAgency.user_id == user.id).first()
    if not agency and user.is_admin:
        agency = db.query(SecurityAgency).first()
    if not agency:
        raise HTTPException(status_code=404, detail="Security agency not found")

    warehouse = db.query(Warehouse).filter(Warehouse.id == payload.warehouse_id).first()
    police_post = None
    if payload.escalate_to_police:
        police_post = getattr(warehouse, "nearby_police_station", None) if warehouse else None
        if not police_post:
            police_post = "Metropolitan Police Post / Nepal Police Command (100)"

    incident = SecurityIncident(
        security_agency_id=agency.id,
        warehouse_id=payload.warehouse_id,
        incident_type=payload.incident_type,
        severity=payload.severity,
        description=payload.description,
        police_station_notified=police_post,
        status="investigating" if payload.escalate_to_police else "reported"
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    esc_msg = f" Escalated & dispatched alert to {police_post}." if police_post else ""

    return {
        "status": "success",
        "message": f"Incident '{payload.incident_type.title()}' logged.{esc_msg}",
        "incident": {
            "id": incident.id,
            "incident_type": incident.incident_type,
            "severity": incident.severity,
            "police_station_notified": incident.police_station_notified,
            "status": incident.status
        }
    }

@router.post("/api/security/invoices/generate")
def generate_station_guarding_invoice(payload: GuardingInvoicePayload, request: Request, db: Session = Depends(get_db)):
    """Use Case 5: Generate Monthly Station Guarding Invoices (13% IRD VAT Compliant)"""
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    warehouse = db.query(Warehouse).filter(Warehouse.id == payload.warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse facility not found")

    subtotal = round(payload.guards_count * payload.monthly_rate_per_guard, 2)
    tax_amount = round(subtotal * 0.13, 2)
    grand_total = round(subtotal + tax_amount, 2)

    inv_num = f"INV-SEC-{datetime.now().year}-{datetime.now().strftime('%m%d%H%M')}"
    qr_data = QRService.generate_qr_base64(f"https://kwdc.gov.np/verify/{inv_num}")

    invoice = Invoice(
        user_id=warehouse.user_id or user.id,
        client_id=warehouse.user_id or user.id,
        invoice_number=inv_num,
        order_type="security_guarding",
        order_id=warehouse.id,
        amount=grand_total,
        subtotal=subtotal,
        tax_rate=13.0,
        tax_amount=tax_amount,
        grand_total=grand_total,
        pan_number="601234567",
        status="pending",
        payment_status="unpaid",
        due_date=date.today() + timedelta(days=15),
        qr_code=qr_data,
        notes=f"Monthly 24/7 Station Guarding Invoice for {warehouse.name} ({payload.guards_count} Guards stationed)"
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    return {
        "status": "success",
        "message": f"Monthly station guarding invoice #{inv_num} generated with 13% IRD VAT",
        "invoice": {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "warehouse_name": warehouse.name,
            "guards_count": payload.guards_count,
            "subtotal": subtotal,
            "vat_13_percent": tax_amount,
            "grand_total": grand_total,
            "payment_status": invoice.payment_status
        }
    }
