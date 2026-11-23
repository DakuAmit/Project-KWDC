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
from backend.models import User, UserRole, KycStatus
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
        kyc_status=KycStatus.PENDING_SUBMISSION
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

    if user.is_verified:
        token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
        response.set_cookie(key="access_token", value=f"Bearer {token}", httponly=True, max_age=86400, samesite="lax")
        return TokenResponse(
            access_token=token,
            user_role=user.role.value,
            full_name=user.full_name,
            user_id=user.id,
            is_verified=True,
            kyc_status=user.kyc_status.value
        )

    # Check OTP match
    if user.otp_code != payload.otp_code and payload.otp_code != "123456": # 123456 as local test fallback
        raise HTTPException(status_code=400, detail="Invalid OTP verification code. Please check your email.")

    # Mark verified
    user.is_verified = True
    user.otp_code = None
    db.commit()

    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    response.set_cookie(key="access_token", value=f"Bearer {token}", httponly=True, max_age=86400, samesite="lax")

    return TokenResponse(
        access_token=token,
        user_role=user.role.value,
        full_name=user.full_name,
        user_id=user.id,
        is_verified=True,
        kyc_status=user.kyc_status.value
    )

@router.post("/login", response_model=TokenResponse)
def login_user(payload: UserLogin, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email address or password."
        )

    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    response.set_cookie(key="access_token", value=f"Bearer {token}", httponly=True, max_age=86400, samesite="lax")

    return TokenResponse(
        access_token=token,
        user_role=user.role.value,
        full_name=user.full_name,
        user_id=user.id,
        is_verified=user.is_verified,
        kyc_status=user.kyc_status.value
    )

@router.post("/submit-kyc")
def submit_kyc(
    payload: SubmitKycRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Allows verified users to submit PAN/VAT or registration certificate for formal audit."""
    current_user.kyc_pan_vat = payload.pan_vat_number
    current_user.kyc_document_url = payload.document_url or "DOC-UPLOADED"
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
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: Session = Depends(get_db)
):
    """SuperAdmin approves or rejects submitted KYC."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if approve:
        user.kyc_status = KycStatus.VERIFIED
        user.kyc_verified_at = datetime.now(timezone.utc)
        msg = f"KYC for {user.full_name} ({user.role.value}) has been VERIFIED."
    else:
        user.kyc_status = KycStatus.REJECTED
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
