from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse, TokenResponse
from app.schemas.warehouse import WarehouseCreate, WarehouseRequestCreate, WarehouseResponse
from app.schemas.dispatch import StopCreate, DispatchCreate, DispatchResponse, PriceCalculateRequest, PriceCalculateResponse
from app.schemas.equipment import EquipmentCreate, EquipmentJobCreate
from app.schemas.invoice import InvoiceResponse
from app.schemas.ai import AIChatRequest, AIDispatchAdvisorRequest, VoiceCommandRequest

__all__ = [
    "LoginRequest",
    "RegisterRequest",
    "UserResponse",
    "TokenResponse",
    "WarehouseCreate",
    "WarehouseRequestCreate",
    "WarehouseResponse",
    "StopCreate",
    "DispatchCreate",
    "DispatchResponse",
    "PriceCalculateRequest",
    "PriceCalculateResponse",
    "EquipmentCreate",
    "EquipmentJobCreate",
    "InvoiceResponse",
    "AIChatRequest",
    "AIDispatchAdvisorRequest",
    "VoiceCommandRequest",
]
