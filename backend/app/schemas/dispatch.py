from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class StopCreate(BaseModel):
    address: str
    recipient_name: str
    recipient_phone: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_from_previous: float = 0.0
    notes: Optional[str] = None

class DispatchCreate(BaseModel):
    pickup_address: str
    pickup_latitude: Optional[float] = None
    pickup_longitude: Optional[float] = None
    pickup_contact_person: Optional[str] = None
    pickup_contact_phone: Optional[str] = None
    vehicle_type: str = "truck"
    stops: List[StopCreate]
    total_distance: float = 0.0
    bill_type: str = "regular"
    pan_number: Optional[str] = None

class PriceCalculateRequest(BaseModel):
    distance: float
    vehicle_type: str = "truck"
    stops_count: int = 1
    service_type: str = "dispatch"

class PriceCalculateResponse(BaseModel):
    distance: float
    vehicle_type: str
    base_price: float
    admin_margin_percentage: float
    admin_margin_amount: float
    subtotal: float
    vat_13_percent: float
    grand_total: float
    explanation: str

class DispatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tracking_id: Optional[str] = None
    invoice_no: Optional[str] = None
    pickup_address: str
    total_distance: float
    base_price: float
    grand_total: float
    status: str
    created_at: Optional[datetime] = None
