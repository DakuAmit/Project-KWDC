"""
Stock & Cargo Insurance Router for KTM-WDC
Connects Commercial Clients with Licensed Nepalese Insurance Underwriters:
- Shikhar Insurance Company Ltd.
- Siddhartha Premier Insurance Ltd.
- Himalayan Everest Insurance Ltd.
- Nepal Insurance Company Ltd.
- Neco Insurance Ltd.

Supports:
1. Client stock declaration & valuation submission
2. Standard coverage (Fire, Flood/Monsoon, Earthquake, Burglary, In-Transit)
3. Admin underwriter quotation, binding & digital Cover Note issuance
4. IRD 13% VAT calculation on insurance premiums
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import random

from backend.database import get_db
from backend.models import (
    StockInsurancePolicy, Warehouse, WarehouseRequest, User, UserRole, InsuranceClaim
)
from backend.schemas import (
    InsuranceRequestCreate, InsuranceProcessRequest,
    InsurancePayPremiumRequest, InsuranceClaimCreate, InsuranceClaimProcessRequest
)
from backend.auth_utils import require_user, require_roles

router = APIRouter(prefix="/api/insurance", tags=["Cargo & Stock Insurance"])

@router.post("/request")
def request_stock_insurance(
    payload: InsuranceRequestCreate,
    current_user: User = Depends(require_roles([UserRole.COMMERCIAL_CLIENT, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Commercial Client declares inventory valuation and requests insurance coverage."""
    warehouse = db.query(Warehouse).filter(Warehouse.id == payload.warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse facility not found.")

    # Preliminary estimated premium calculation (standard 0.25% annual tariff)
    base_rate = 0.0025 # 0.25%
    est_premium = round(payload.declared_valuation_npr * base_rate, 2)
    vat_amt = round(est_premium * 0.13, 2)
    total_payable = round(est_premium + vat_amt, 2)

    draft_policy_no = f"KWDC-INS-REQ-{datetime.now(timezone.utc).year}-{random.randint(1000, 9999)}"

    policy = StockInsurancePolicy(
        client_id=current_user.id,
        warehouse_id=warehouse.id,
        booking_id=payload.booking_id,
        policy_number=draft_policy_no,
        commodity_type=payload.commodity_type.strip(),
        declared_valuation_npr=payload.declared_valuation_npr,
        coverage_scope=payload.coverage_scope or "Fire, Lightning, Earthquake, Monsoon Flood, Burglary",
        stock_manifest_summary=payload.stock_manifest_summary.strip(),
        invoice_document_ref=payload.invoice_document_ref,
        underwriter_name="Shikhar Insurance Co. Ltd.",
        premium_rate_percent=0.25,
        premium_amount_npr=est_premium,
        vat_13_percent=vat_amt,
        total_payable_npr=total_payable,
        status="UNDER_REVIEW",
        admin_notes="Pending underwriter risk assessment and Cover Note execution."
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)

    return {
        "message": "Stock insurance application submitted! SuperAdmin is binding with underwriter.",
        "policy_id": policy.id,
        "policy_number": policy.policy_number,
        "declared_valuation_npr": policy.declared_valuation_npr,
        "estimated_annual_premium_npr": policy.premium_amount_npr,
        "estimated_vat_npr": policy.vat_13_percent,
        "total_estimated_payable_npr": policy.total_payable_npr,
        "status": policy.status
    }

@router.get("/my-policies")
def get_my_insurance_policies(
    current_user: User = Depends(require_roles([UserRole.COMMERCIAL_CLIENT, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Retrieves all insurance policies and active cover notes for the logged-in client."""
    policies = db.query(StockInsurancePolicy).filter(
        StockInsurancePolicy.client_id == current_user.id
    ).order_by(StockInsurancePolicy.created_at.desc()).all()

    results = []
    for p in policies:
        results.append({
            "id": p.id,
            "policy_number": p.policy_number or f"PENDING-REV-{p.id}",
            "warehouse_title": p.warehouse.title if p.warehouse else f"Warehouse #{p.warehouse_id}",
            "commodity_type": p.commodity_type,
            "declared_valuation_npr": p.declared_valuation_npr,
            "coverage_scope": p.coverage_scope,
            "stock_manifest_summary": p.stock_manifest_summary,
            "underwriter_name": p.underwriter_name,
            "premium_amount_npr": p.premium_amount_npr,
            "vat_13_percent": p.vat_13_percent,
            "total_payable_npr": p.total_payable_npr,
            "status": p.status,
            "payment_status": getattr(p, "payment_status", None) or "UNPAID",
            "payment_ref": getattr(p, "payment_ref", None),
            "coverage_start_date": p.coverage_start_date.strftime("%Y-%m-%d") if p.coverage_start_date else None,
            "coverage_end_date": p.coverage_end_date.strftime("%Y-%m-%d") if p.coverage_end_date else None,
            "certificate_qr_payload": p.certificate_qr_payload,
            "created_at": p.created_at.strftime("%Y-%m-%d %H:%M")
        })
    return results

@router.get("/admin/requests")
def get_admin_insurance_requests(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """SuperAdmin review queue of all client inventory insurance requests."""
    policies = db.query(StockInsurancePolicy).order_by(StockInsurancePolicy.created_at.desc()).all()
    results = []
    for p in policies:
        results.append({
            "id": p.id,
            "client_name": p.client.full_name if p.client else "Client",
            "client_email": p.client.email if p.client else "-",
            "client_phone": p.client.phone_number if p.client else "-",
            "warehouse_title": p.warehouse.title if p.warehouse else f"Warehouse #{p.warehouse_id}",
            "policy_number": p.policy_number,
            "commodity_type": p.commodity_type,
            "declared_valuation_npr": p.declared_valuation_npr,
            "coverage_scope": p.coverage_scope,
            "stock_manifest_summary": p.stock_manifest_summary,
            "underwriter_name": p.underwriter_name,
            "premium_rate_percent": p.premium_rate_percent,
            "premium_amount_npr": p.premium_amount_npr,
            "vat_13_percent": p.vat_13_percent,
            "total_payable_npr": p.total_payable_npr,
            "status": p.status,
            "payment_status": getattr(p, "payment_status", None) or "UNPAID",
            "payment_ref": getattr(p, "payment_ref", None),
            "coverage_start_date": p.coverage_start_date.strftime("%Y-%m-%d") if p.coverage_start_date else None,
            "coverage_end_date": p.coverage_end_date.strftime("%Y-%m-%d") if p.coverage_end_date else None,
            "admin_notes": p.admin_notes,
            "created_at": p.created_at.strftime("%Y-%m-%d %H:%M")
        })
    return results

@router.post("/admin/{policy_id}/process")
def process_insurance_policy(
    policy_id: int,
    payload: InsuranceProcessRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """SuperAdmin binds policy with underwriter, issues Cover Note, and activates insurance."""
    policy = db.query(StockInsurancePolicy).filter(StockInsurancePolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Insurance policy request not found.")

    if payload.status.upper() == "REJECTED":
        policy.status = "REJECTED"
        policy.admin_notes = payload.admin_notes or "Underwriting declined based on commodity risk."
        db.commit()
        return {"message": "Insurance request declined.", "status": "REJECTED"}

    # Calculate bound premium
    rate_factor = payload.premium_rate_percent / 100.0
    premium = round(policy.declared_valuation_npr * rate_factor, 2)
    vat = round(premium * 0.13, 2)
    total = round(premium + vat, 2)

    now = datetime.now(timezone.utc)
    start_date = now
    end_date = now + timedelta(days=payload.duration_months * 30)

    policy_no = payload.policy_number or f"KWDC-INS-{payload.underwriter_name[:3].upper()}-{now.year}-{policy.id:04d}"

    # Build QR payload for verification
    qr_str = (
        f"KTM-WDC-INSURANCE|POLICY:{policy_no}|UNDERWRITER:{payload.underwriter_name}|"
        f"CLIENT_ID:{policy.client_id}|VALUATION_NPR:{policy.declared_valuation_npr}|"
        f"PREMIUM_NPR:{total}|VALID_UNTIL:{end_date.strftime('%Y-%m-%d')}"
    )

    policy.underwriter_name = payload.underwriter_name
    policy.policy_number = policy_no
    policy.premium_rate_percent = payload.premium_rate_percent
    policy.premium_amount_npr = premium
    policy.vat_13_percent = vat
    policy.total_payable_npr = total
    policy.status = "ACTIVE_INSURED"
    policy.coverage_start_date = start_date
    policy.coverage_end_date = end_date
    policy.admin_notes = payload.admin_notes or f"Cover Note executed under master commercial agreement with {payload.underwriter_name}."
    policy.certificate_qr_payload = qr_str

    db.commit()
    db.refresh(policy)

    return {
        "message": f"Insurance Cover Note issued! Policy {policy_no} is now ACTIVE.",
        "policy_number": policy.policy_number,
        "underwriter": policy.underwriter_name,
        "underwriter_name": policy.underwriter_name,
        "total_payable_npr": policy.total_payable_npr,
        "status": policy.status,
        "valid_until": policy.coverage_end_date.strftime("%Y-%m-%d")
    }


@router.post("/{policy_id}/pay-premium")
def pay_insurance_premium(
    policy_id: int,
    payload: InsurancePayPremiumRequest,
    current_user: User = Depends(require_roles([UserRole.COMMERCIAL_CLIENT, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Records client insurance premium payment proof / transaction reference."""
    policy = db.query(StockInsurancePolicy).filter(StockInsurancePolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Insurance policy not found.")
    if current_user.role == UserRole.COMMERCIAL_CLIENT and policy.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized to update another client's policy.")

    policy.payment_status = "PAID"
    policy.payment_ref = f"{payload.payment_method.upper()}:{payload.payment_ref.strip()}"
    db.commit()
    return {
        "message": f"Premium payment recorded ({policy.payment_ref}).",
        "policy_id": policy.id,
        "payment_status": policy.payment_status,
        "payment_ref": policy.payment_ref,
    }


@router.post("/{policy_id}/claim")
def submit_insurance_claim(
    policy_id: int,
    payload: InsuranceClaimCreate,
    current_user: User = Depends(require_roles([UserRole.COMMERCIAL_CLIENT, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """Files a damage or loss insurance claim against an active bound policy."""
    policy = db.query(StockInsurancePolicy).filter(StockInsurancePolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Insurance policy not found.")
    if current_user.role == UserRole.COMMERCIAL_CLIENT and policy.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized to claim under another client's policy.")
    if policy.status not in ("ACTIVE_INSURED", "APPROVED_ACTIVE"):
        raise HTTPException(status_code=400, detail="Claims can only be filed against ACTIVE_INSURED policies.")
    if payload.claim_amount_npr > float(policy.declared_valuation_npr or 0):
        raise HTTPException(status_code=400, detail="Claim amount exceeds declared policy valuation.")

    claim_no = f"CLM-{datetime.now(timezone.utc).year}-{random.randint(10000, 99999)}"
    claim = InsuranceClaim(
        policy_id=policy.id,
        client_id=policy.client_id,
        warehouse_id=policy.warehouse_id,
        claim_number=claim_no,
        incident_type=payload.incident_type.upper(),
        incident_date=payload.incident_date.strip(),
        claim_amount_npr=float(payload.claim_amount_npr),
        description=payload.description.strip(),
        evidence_photo_url=payload.evidence_photo_url,
        status="SUBMITTED",
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return {
        "message": f"Insurance claim {claim.claim_number} submitted for surveyor inspection.",
        "claim_id": claim.id,
        "claim_number": claim.claim_number,
        "status": claim.status,
    }


@router.get("/my-claims")
def get_my_insurance_claims(
    current_user: User = Depends(require_roles([UserRole.COMMERCIAL_CLIENT, UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    claims = db.query(InsuranceClaim).filter(
        InsuranceClaim.client_id == current_user.id
    ).order_by(InsuranceClaim.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "claim_number": c.claim_number,
            "policy_id": c.policy_id,
            "policy_number": c.policy.policy_number if c.policy else f"POL-{c.policy_id}",
            "warehouse_title": c.warehouse.title if c.warehouse else f"Warehouse #{c.warehouse_id}",
            "incident_type": c.incident_type,
            "incident_date": c.incident_date,
            "claim_amount_npr": c.claim_amount_npr,
            "approved_payout_npr": c.approved_payout_npr,
            "status": c.status,
            "description": c.description,
            "admin_notes": c.admin_notes,
            "created_at": c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "",
        }
        for c in claims
    ]


@router.get("/admin/claims")
def get_admin_insurance_claims(
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    claims = db.query(InsuranceClaim).order_by(InsuranceClaim.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "claim_number": c.claim_number,
            "policy_id": c.policy_id,
            "policy_number": c.policy.policy_number if c.policy else f"POL-{c.policy_id}",
            "client_name": c.client.full_name if c.client else "Client",
            "warehouse_title": c.warehouse.title if c.warehouse else f"Warehouse #{c.warehouse_id}",
            "incident_type": c.incident_type,
            "incident_date": c.incident_date,
            "claim_amount_npr": c.claim_amount_npr,
            "approved_payout_npr": c.approved_payout_npr,
            "status": c.status,
            "description": c.description,
            "evidence_photo_url": c.evidence_photo_url,
            "admin_notes": c.admin_notes,
            "created_at": c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "",
        }
        for c in claims
    ]


@router.post("/admin/claims/{claim_id}/process")
def process_insurance_claim(
    claim_id: int,
    payload: InsuranceClaimProcessRequest,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    claim = db.query(InsuranceClaim).filter(InsuranceClaim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Insurance claim not found.")

    decision = payload.status.upper()
    if decision not in ("SURVEYING", "APPROVED", "REJECTED", "SETTLED"):
        raise HTTPException(status_code=400, detail="Invalid claim status.")

    claim.status = decision
    if payload.approved_payout_npr > 0 or decision == "REJECTED":
        claim.approved_payout_npr = 0.0 if decision == "REJECTED" else float(payload.approved_payout_npr)
    claim.admin_notes = payload.admin_notes
    claim.processed_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "message": f"Claim {claim.claim_number} updated to {decision}.",
        "status": claim.status,
        "approved_payout_npr": claim.approved_payout_npr,
    }
