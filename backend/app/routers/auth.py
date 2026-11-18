import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Form, Response, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
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
    TokenResponse,
    UserResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
    MessageResponse
)
from app.services.email_service import EmailService

router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")

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
def api_login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})
    return {"access_token": token, "token_type": "bearer", "user": user}

@router.post("/api/auth/register", response_model=TokenResponse)
def api_register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email address already exists.")

    verification_token = secrets.token_urlsafe(32)
    role_normalized = payload.role.strip().lower()
    
    # Generate human-readable user code
    prefix_map = {
        "admin": "ADM",
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
        is_admin=(role_normalized == "admin"),
        is_driver=(role_normalized == "driver"),
        is_property_owner=(role_normalized == "property_owner"),
        is_equipment_owner=(role_normalized == "equipment_owner"),
        email_verification_token=verification_token,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Dispatch welcome & email verification via Resend
    base_url = str(request.base_url).rstrip("/")
    EmailService.send_verification_email(
        to_email=new_user.email,
        name=new_user.name,
        token=verification_token,
        base_url=base_url
    )

    token = create_access_token({"sub": str(new_user.id), "email": new_user.email, "role": new_user.role})
    return {"access_token": token, "token_type": "bearer", "user": new_user}

@router.get("/api/auth/verify-email")
def api_verify_email(token: str = Query(...), db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=400, detail="Missing verification token.")
    user = db.query(User).filter(User.email_verification_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token.")

    user.email_verified_at = datetime.utcnow()
    user.email_verification_token = None
    db.commit()
    return {"message": "Email verified successfully! You may now access all features.", "status": "success"}

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
