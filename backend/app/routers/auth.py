import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Form, Response, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    verify_password,
    hash_password,
    create_access_token,
    get_current_user_from_request
)
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
    VerifyCodeRequest,
    ResendCodeRequest,
    MessageResponse
)
from app.services.email_service import EmailService

router = APIRouter(tags=["Authentication"])
from app.core.templates import templates

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request=request, name="auth/login.html", context={"user": None})

@router.post("/login")
def login(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    remember: bool = Form(False),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password):
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"user": None, "error": "Invalid email credentials or master password."},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    if not user.is_active:
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"user": None, "error": "This account is inactive. Please contact support."},
            status_code=status.HTTP_403_FORBIDDEN
        )

    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role},
        expires_delta=timedelta(days=30 if remember else 1)
    )

    redirect = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        max_age=86400 * 30 if remember else 86400,
        samesite="lax",
    )
    return redirect

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request=request, name="auth/register.html", context={"user": None})

@router.post("/register")
def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    phone: str = Form(None),
    role: str = Form("client"),
    address: str = Form(None),
    db: Session = Depends(get_db)
):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html",
            context={"user": None, "error": "An account with this email already exists."},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    new_user = User(
        name=name,
        email=email,
        password=hash_password(password),
        phone=phone,
        role=role,
        address=address,
        is_active=True,
        is_admin=(role == "admin"),
        is_driver=(role == "driver"),
        is_property_owner=(role == "property_owner"),
        is_equipment_owner=(role == "equipment_owner"),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token(
        data={"sub": str(new_user.id), "email": new_user.email, "role": new_user.role}
    )

    redirect = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        max_age=86400,
        samesite="lax"
    )
    return redirect

@router.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME)
    return response

# RESTful JSON endpoints for API consumers
@router.post("/api/auth/login", response_model=TokenResponse)
def api_login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Require email verification for non-admin accounts
    if not user.is_admin and user.role != "admin" and user.email_verified_at is None:
        raise HTTPException(
            status_code=403,
            detail="Your email address has not been verified yet. Please check your inbox for the 6-digit verification code or click 'Resend Code'."
        )
    
    token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=86400,
        samesite="lax"
    )
    return {"access_token": token, "token_type": "bearer", "user": user}

@router.post("/api/auth/register", response_model=RegisterResponse)
def api_register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email address already exists.")

    # Generate 6-digit numeric verification OTP code
    verification_code = f"{secrets.randbelow(900000) + 100000}"
    role_normalized = payload.role.strip().lower()
    
    # Restrict public self-registration to customer and partner roles only (Super Admin is seeded via env vars)
    ALLOWED_PUBLIC_ROLES = {"client", "property_owner", "driver", "equipment_owner", "security_agency"}
    if role_normalized not in ALLOWED_PUBLIC_ROLES:
        role_normalized = "client"

    # Generate human-readable user code
    prefix_map = {
        "client": "CLI",
        "driver": "DRV",
        "property_owner": "PRO",
        "equipment_owner": "EQP",
        "security_agency": "SEC"
    }
    prefix = prefix_map.get(role_normalized, "USR")
    user_code = f"{prefix}-{secrets.randbelow(89999) + 10000}"

    new_user = User(
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        password=hash_password(payload.password),
        phone=payload.phone.strip() if payload.phone else None,
        role=role_normalized,
        address=payload.address.strip() if payload.address else None,
        user_code=user_code,
        is_active=True,
        is_admin=False,
        is_driver=(role_normalized == "driver"),
        is_property_owner=(role_normalized == "property_owner"),
        is_equipment_owner=(role_normalized == "equipment_owner"),
        email_verification_token=verification_code,
        email_verified_at=None,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Dispatch verification email with the 6-digit code
    base_url = str(request.base_url).rstrip("/")
    email_res = EmailService.send_verification_code_email(
        to_email=new_user.email,
        name=new_user.name,
        code=verification_code,
        base_url=base_url
    )

    code_preview = None
    if "error" in email_res or email_res.get("status") == "simulated":
        code_preview = verification_code

    return {
        "status": "pending_verification",
        "message": f"Verification code sent to {new_user.email}. Please enter the 6-digit code to activate your account.",
        "email": new_user.email,
        "requires_verification": True,
        "verification_code_preview": code_preview
    }

@router.post("/api/auth/verify-code")
def api_verify_code(payload: VerifyCodeRequest, response: Response, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    code_clean = payload.code.strip()

    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(status_code=400, detail="No registered account found with this email address.")

    if user.email_verified_at:
        token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})
        response.set_cookie(key=settings.SESSION_COOKIE_NAME, value=token, httponly=True, max_age=86400, samesite="lax")
        return {
            "status": "verified",
            "message": "Account already verified. Welcome back!",
            "access_token": token,
            "token_type": "bearer",
            "user": user,
            "role": user.role,
            "dashboard_url": f"/dashboard.html?role={user.role}"
        }

    if not user.email_verification_token or user.email_verification_token.strip() != code_clean:
        raise HTTPException(status_code=400, detail="Invalid verification code. Please check your email or click 'Resend Code'.")

    user.email_verified_at = datetime.utcnow()
    user.email_verification_token = None
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=86400,
        samesite="lax"
    )
    return {
        "status": "verified",
        "message": "Email verified successfully! Welcome to KTM-WDC.",
        "access_token": token,
        "token_type": "bearer",
        "user": user,
        "role": user.role,
        "dashboard_url": f"/dashboard.html?role={user.role}"
    }

@router.post("/api/auth/resend-code")
def api_resend_code(payload: ResendCodeRequest, request: Request, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(status_code=400, detail="No registered account found with this email address.")

    if user.email_verified_at:
        return {"status": "already_verified", "message": "This email is already verified. You can sign in directly."}

    new_code = f"{secrets.randbelow(900000) + 100000}"
    user.email_verification_token = new_code
    db.commit()

    base_url = str(request.base_url).rstrip("/")
    email_res = EmailService.send_verification_code_email(
        to_email=user.email,
        name=user.name,
        code=new_code,
        base_url=base_url
    )

    code_preview = None
    if "error" in email_res or email_res.get("status") == "simulated":
        code_preview = new_code

    return {
        "status": "sent",
        "message": f"A new 6-digit verification code has been dispatched to {user.email}.",
        "verification_code_preview": code_preview
    }

@router.get("/api/auth/verify-email")
def api_verify_email(token: Optional[str] = Query(None), code: Optional[str] = Query(None), email: Optional[str] = Query(None), response: Response = None, db: Session = Depends(get_db)):
    search_val = (code or token or "").strip()
    if not search_val:
        raise HTTPException(status_code=400, detail="Missing verification token or code.")
    
    query = db.query(User).filter(User.email_verification_token == search_val)
    if email:
        query = query.filter(User.email == email.strip().lower())
    user = query.first()
    
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")

    user.email_verified_at = datetime.utcnow()
    user.email_verification_token = None
    db.commit()
    db.refresh(user)

    access_token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})
    if response:
        response.set_cookie(key=settings.SESSION_COOKIE_NAME, value=access_token, httponly=True, max_age=86400, samesite="lax")
    return {
        "message": "Email verified successfully! You may now access all features.",
        "status": "success",
        "access_token": access_token,
        "user": user,
        "dashboard_url": f"/dashboard.html?role={user.role}"
    }

@router.post("/api/auth/forgot-password", response_model=MessageResponse)
def api_forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    
    if user:
        reset_token = secrets.token_urlsafe(32)
        user.reset_password_token = reset_token
        user.reset_password_expires_at = datetime.utcnow() + timedelta(hours=1)
        db.commit()

        base_url = str(request.base_url).rstrip("/")
        EmailService.send_password_reset_email(
            to_email=user.email,
            name=user.name,
            token=reset_token,
            base_url=base_url
        )

    # Always return success message to prevent user enumeration
    return {
        "message": "If this email address is registered, a password reset link has been dispatched to your inbox.",
        "status": "success"
    }

@router.post("/api/auth/reset-password", response_model=MessageResponse)
def api_reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    if not payload.token or not payload.new_password:
        raise HTTPException(status_code=400, detail="Token and new password are required.")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")

    user = db.query(User).filter(User.reset_password_token == payload.token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset link.")

    if not user.reset_password_expires_at or user.reset_password_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="This password reset link has expired. Please request a new one.")

    user.password = hash_password(payload.new_password)
    user.reset_password_token = None
    user.reset_password_expires_at = None
    db.commit()

    # Send security notification
    EmailService.send_password_changed_notification(user.email, user.name)

    return {
        "message": "Your password has been reset successfully. You can now sign in.",
        "status": "success"
    }
