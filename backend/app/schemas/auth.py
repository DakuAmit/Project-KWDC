from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class LoginRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    email: str
    password: str
    remember: bool = False

class RegisterRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    email: str
    password: str
    phone: Optional[str] = None
    role: str = "client"
    address: Optional[str] = None

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_code: Optional[str] = None
    name: str
    email: str
    phone: Optional[str] = None
    role: str
    is_active: bool
    is_admin: bool
    is_driver: bool
    is_equipment_owner: bool
    is_property_owner: bool
    address: Optional[str] = None
    created_at: Optional[datetime] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class VerifyEmailRequest(BaseModel):
    token: str

class VerifyCodeRequest(BaseModel):
    email: str
    code: str

class ResendCodeRequest(BaseModel):
    email: str

class RegisterResponse(BaseModel):
    status: str
    message: str
    email: str
    requires_verification: bool = True
    verification_code_preview: Optional[str] = None

class MessageResponse(BaseModel):
    message: str
    status: str = "success"
