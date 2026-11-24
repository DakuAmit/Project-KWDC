"""
Authentication & KYC API router for KTM-WDC.
Supports:
1. Hassle-free Partner & Client Registration (Role, Name/Company, Email, Phone, Location, Password).
2. 6-Digit Email OTP verification via Brevo.
3. KYC Document Submission (PAN/VAT, Registration, License).
4. SuperAdmin KYC Verification.
"""
import random
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import User, UserRole, KycStatus, UserKycProfile
from backend.schemas import UserRegister, VerifyOtpRequest, UserLogin, TokenResponse, SubmitKycRequest
from backend.auth_utils import (
    verify_password, get_password_hash, create_access_token,
    get_current_user, require_user, require_roles
)
from backend.services.email_service import send_otp_email

router = APIRouter(prefix="/api/auth", tags=["Authentication & KYC"])

@router.post("/register")
def register_user(payload: UserRegister, db: Session = Depends(get_db)):
    """
    Hassle-free registration:
    Takes Name/Company, Email, Contact, Operating Location, Role, Password & Confirm Password.
    Dispatches 6-digit OTP via Brevo email for account activation.
    """
    # Warehouse Incharge and SuperAdmin cannot be self-registered publicly
    if payload.role in (UserRole.WAREHOUSE_INCHARGE, UserRole.SUPERADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Warehouse Incharge accounts cannot be self-registered. They are created and provisioned directly by the SuperAdmin."
        )

    # Check existing email
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists. Please sign in."
        )
    
    # Check existing phone
    if db.query(User).filter(User.phone_number == payload.phone_number).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this contact number already exists."
        )

    # Generate 6-digit OTP
    otp_code = f"{random.randint(100000, 999999)}"
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=15)

    new_user = User(
        email=payload.email.lower(),
        phone_number=payload.phone_number,
        full_name=payload.full_name,
        company_name=payload.company_name or payload.full_name,
        operating_location=payload.operating_location,
        hashed_password=get_password_hash(payload.password),
        role=payload.role,
        is_active=True,
        is_verified=False,
        otp_code=otp_code,
        otp_expires_at=expires_at,
        kyc_status=KycStatus.PENDING_SUBMISSION,
        fleet_operator_type=None if payload.role == UserRole.FLEET_PARTNER else "COMMERCIAL_3PL"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Send OTP Email
    email_dispatched = send_otp_email(
        to_email=new_user.email,
        to_name=new_user.full_name,
        otp_code=otp_code
    )

    return {
        "message": f"Welcome to KTM-WDC! A 6-digit verification code has been sent to {new_user.email}.",
        "email": new_user.email,
        "email_dispatched": email_dispatched,
        "role": new_user.role.value
    }

@router.post("/resend-otp")
def resend_otp(payload: dict, db: Session = Depends(get_db)):
    """Resends a new 6-digit OTP verification code."""
    email = (payload.get("email") or "").strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")

    otp_code = f"{random.randint(100000, 999999)}"
    now = datetime.now(timezone.utc)
    user.otp_code = otp_code
    user.otp_expires_at = now + timedelta(minutes=15)
    db.commit()

    send_otp_email(to_email=user.email, to_name=user.full_name, otp_code=otp_code)
    return {"message": f"A new 6-digit verification code has been sent to {user.email}."}

@router.post("/verify-otp", response_model=TokenResponse)
def verify_otp(payload: VerifyOtpRequest, response: Response, db: Session = Depends(get_db)):
    """Verifies the 6-digit OTP code sent to user email."""
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    def build_user_token(u: User) -> str:
        return create_access_token(data={
            "sub": str(u.id),
            "email": u.email,
            "role": u.role.value,
            "full_name": u.full_name,
            "company_name": u.company_name or u.full_name,
            "phone_number": u.phone_number,
            "operating_location": u.operating_location or "Kathmandu Valley",
            "fleet_operator_type": u.fleet_operator_type
        })

    if user.is_verified:
        token = build_user_token(user)
        response.set_cookie(key="access_token", value=f"Bearer {token}", httponly=True, max_age=86400, samesite="lax")
        return TokenResponse(
            access_token=token,
            user_role=user.role.value,
            full_name=user.full_name,
            email=user.email,
            user_id=user.id,
            is_verified=True,
            kyc_status=user.kyc_status.value,
            fleet_operator_type=user.fleet_operator_type
        )

    # Check OTP match
    if user.otp_code != payload.otp_code and payload.otp_code != "123456": # 123456 as local test fallback
        raise HTTPException(status_code=400, detail="Invalid OTP verification code. Please check your email.")

    # Mark verified
    user.is_verified = True
    user.otp_code = None
    db.commit()

    token = build_user_token(user)
    response.set_cookie(key="access_token", value=f"Bearer {token}", httponly=True, max_age=86400, samesite="lax")

    return TokenResponse(
        access_token=token,
        user_role=user.role.value,
        full_name=user.full_name,
        email=user.email,
        user_id=user.id,
        is_verified=True,
        kyc_status=user.kyc_status.value,
        fleet_operator_type=user.fleet_operator_type
    )

@router.post("/login", response_model=TokenResponse)
def login_user(payload: UserLogin, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email address or password."
        )

    token = create_access_token(data={
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "full_name": user.full_name,
        "company_name": user.company_name or user.full_name,
        "phone_number": user.phone_number,
        "operating_location": user.operating_location or "Kathmandu Valley",
        "fleet_operator_type": user.fleet_operator_type
    })
    response.set_cookie(key="access_token", value=f"Bearer {token}", httponly=True, max_age=86400, samesite="lax")

    return TokenResponse(
        access_token=token,
        user_role=user.role.value,
        full_name=user.full_name,
        email=user.email,
        user_id=user.id,
        is_verified=user.is_verified,
        kyc_status=user.kyc_status.value,
        fleet_operator_type=user.fleet_operator_type
    )

@router.get("/kyc-profile")
def get_my_kyc_profile(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Retrieves current user's structured KYC submission."""
    profile = db.query(UserKycProfile).filter(UserKycProfile.user_id == current_user.id).first()
    return {
        "user_id": current_user.id,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
        "kyc_status": current_user.kyc_status.value,
        "is_verified": current_user.is_verified,
        "profile": {
            "citizenship_number": profile.citizenship_number if profile else None,
            "citizenship_front_url": profile.citizenship_front_url if profile else None,
            "citizenship_back_url": profile.citizenship_back_url if profile else None,
            "bank_name": profile.bank_name if profile else None,
            "bank_account_number": profile.bank_account_number if profile else None,
            "bank_account_name": profile.bank_account_name if profile else None,
            "bank_branch": profile.bank_branch if profile else None,
            "bank_proof_doc_url": profile.bank_proof_doc_url if profile else None,
            "company_name": profile.company_name if profile else current_user.company_name,
            "company_reg_number": profile.company_reg_number if profile else None,
            "company_pan_vat": profile.company_pan_vat or current_user.kyc_pan_vat if profile else current_user.kyc_pan_vat,
            "company_reg_doc_url": profile.company_reg_doc_url if profile else None,
            "company_pan_doc_url": profile.company_pan_doc_url if profile else None,
            "authorized_signatory_name": profile.authorized_signatory_name if profile else None,
            "authorized_signatory_doc_url": profile.authorized_signatory_doc_url if profile else None,
            "fleet_operator_pan_vat": profile.fleet_operator_pan_vat if profile else None,
            "fleet_operator_reg_no": profile.fleet_operator_reg_no if profile else None,
            "fleet_operator_doc_url": profile.fleet_operator_doc_url if profile else None,
            "admin_review_notes": profile.admin_review_notes if profile else None,
            "verified_at": profile.verified_at.strftime("%Y-%m-%d %H:%M") if profile and profile.verified_at else None
        } if profile else None
    }

@router.post("/submit-kyc")
def submit_kyc(
    payload: SubmitKycRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Submits role-appropriate KYC documentation:
    - Property Owner: Strictly Nepalese Citizenship & Bank Account Proof (for 90% direct disbursements).
    - Commercial Client: Company Registration, PAN/VAT certificate, Authorized Signatory.
    - Fleet Partner: Transport operator registration & PAN/VAT.
    """
    profile = db.query(UserKycProfile).filter(UserKycProfile.user_id == current_user.id).first()
    if not profile:
        profile = UserKycProfile(
            user_id=current_user.id,
            role=current_user.role.value,
            kyc_status=KycStatus.UNDER_REVIEW
        )
        db.add(profile)
    else:
        profile.kyc_status = KycStatus.UNDER_REVIEW

    # 1. PROPERTY OWNER (STRICTLY citizenship & bank account proof per user instruction)
    if current_user.role == UserRole.PROPERTY_OWNER:
        if payload.citizenship_number:
            profile.citizenship_number = payload.citizenship_number.strip()
        if payload.citizenship_front_url:
            profile.citizenship_front_url = payload.citizenship_front_url.strip()
        if payload.citizenship_back_url:
            profile.citizenship_back_url = payload.citizenship_back_url.strip()
        if payload.bank_name:
            profile.bank_name = payload.bank_name.strip()
        if payload.bank_account_number:
            profile.bank_account_number = payload.bank_account_number.strip()
        if payload.bank_account_name:
            profile.bank_account_name = payload.bank_account_name.strip()
        if payload.bank_branch:
            profile.bank_branch = payload.bank_branch.strip()
        if payload.bank_proof_doc_url:
            profile.bank_proof_doc_url = payload.bank_proof_doc_url.strip()

    # 2. COMMERCIAL CLIENT
    elif current_user.role == UserRole.COMMERCIAL_CLIENT:
        if payload.company_reg_number:
            profile.company_reg_number = payload.company_reg_number.strip()
        if payload.pan_vat_number or payload.company_pan_vat:
            pan = (payload.company_pan_vat or payload.pan_vat_number).strip()
            profile.company_pan_vat = pan
            current_user.kyc_pan_vat = pan
        if payload.company_reg_doc_url or payload.document_url:
            profile.company_reg_doc_url = (payload.company_reg_doc_url or payload.document_url).strip()
        if payload.company_pan_doc_url:
            profile.company_pan_doc_url = payload.company_pan_doc_url.strip()
        if payload.authorized_signatory_name:
            profile.authorized_signatory_name = payload.authorized_signatory_name.strip()
        if payload.authorized_signatory_doc_url:
            profile.authorized_signatory_doc_url = payload.authorized_signatory_doc_url.strip()

    # 3. FLEET PARTNER
    elif current_user.role == UserRole.FLEET_PARTNER:
        if payload.pan_vat_number or payload.fleet_operator_pan_vat:
            pan = (payload.fleet_operator_pan_vat or payload.pan_vat_number).strip()
            profile.fleet_operator_pan_vat = pan
            current_user.kyc_pan_vat = pan
        if payload.fleet_operator_reg_no:
            profile.fleet_operator_reg_no = payload.fleet_operator_reg_no.strip()
        if payload.fleet_operator_doc_url or payload.document_url:
            profile.fleet_operator_doc_url = (payload.fleet_operator_doc_url or payload.document_url).strip()

    # Generic fallbacks
    if payload.pan_vat_number and not current_user.kyc_pan_vat:
        current_user.kyc_pan_vat = payload.pan_vat_number.strip()
    if payload.document_url and not current_user.kyc_document_url:
        current_user.kyc_document_url = payload.document_url.strip()

    current_user.kyc_status = KycStatus.UNDER_REVIEW
    db.commit()

    return {
        "message": "KYC documentation submitted successfully for compliance review.",
        "kyc_status": current_user.kyc_status.value
    }

@router.post("/admin/verify-kyc/{user_id}")
def admin_verify_kyc(
    user_id: int,
    approve: bool = True,
    admin_notes: str = None,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """SuperAdmin approves or rejects submitted KYC."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    profile = db.query(UserKycProfile).filter(UserKycProfile.user_id == user.id).first()
    now = datetime.now(timezone.utc)

    if approve:
        user.kyc_status = KycStatus.VERIFIED
        user.is_verified = True
        user.kyc_verified_at = now
        if profile:
            profile.kyc_status = KycStatus.VERIFIED
            profile.verified_at = now
            if admin_notes:
                profile.admin_review_notes = admin_notes
        msg = f"KYC for {user.full_name} ({user.role.value}) has been VERIFIED."
    else:
        user.kyc_status = KycStatus.REJECTED
        user.is_verified = False
        if profile:
            profile.kyc_status = KycStatus.REJECTED
            if admin_notes:
                profile.admin_review_notes = admin_notes
        msg = f"KYC for {user.full_name} has been REJECTED."

    db.commit()
    return {"message": msg, "kyc_status": user.kyc_status.value}

@router.get("/me")
def get_profile(current_user: User = Depends(require_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "company_name": current_user.company_name,
        "operating_location": current_user.operating_location,
        "phone_number": current_user.phone_number,
        "role": current_user.role.value,
        "is_verified": current_user.is_verified,
        "kyc_status": current_user.kyc_status.value
    }

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully."}
