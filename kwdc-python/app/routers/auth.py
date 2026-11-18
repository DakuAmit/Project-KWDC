from datetime import timedelta
from fastapi import APIRouter, Depends, Request, Form, Response, HTTPException, status
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
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse

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
