from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class WarehouseCreate(BaseModel):
    name: str
    location: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    area_sqft: float
    price_per_sqft: float
    description: Optional[str] = None
    cold_storage: bool = False
    temperature_min: Optional[float] = None
    temperature_max: Optional[float] = None
    cctv_count: int = 0
    guards_count: int = 0
    kataho_code: Optional[str] = None

class WarehouseRequestCreate(BaseModel):
    warehouse_id: int
    start_date: str
    end_date: str
    space_required: float
    purpose: Optional[str] = None

class WarehouseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    location: str
    address: Optional[str] = None
    area_sqft: Optional[float] = None
    price_per_sqft: Optional[float] = None
    cold_storage: bool
    status: str
    created_at: Optional[datetime] = None
