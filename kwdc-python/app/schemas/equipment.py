from pydantic import BaseModel
from typing import Optional
from datetime import date

class EquipmentCreate(BaseModel):
    name: str
    type: str
    model: Optional[str] = None
    year: Optional[int] = None
    daily_rate: float
    security_deposit: float = 0.0
    location: str
    description: Optional[str] = None

class EquipmentJobCreate(BaseModel):
    equipment_id: int
    start_date: date
    end_date: date
    location: str
    job_type: Optional[str] = None
    description: Optional[str] = None
    proposed_price: Optional[float] = None
