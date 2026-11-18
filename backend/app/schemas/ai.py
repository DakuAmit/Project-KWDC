from pydantic import BaseModel
from typing import Optional, Dict, Any

class AIChatRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None

class AIDispatchAdvisorRequest(BaseModel):
    pickup_address: str
    destination_address: str
    estimated_weight_kg: Optional[float] = 100.0
    cargo_type: Optional[str] = "General Cargo"

class VoiceCommandRequest(BaseModel):
    command: str
