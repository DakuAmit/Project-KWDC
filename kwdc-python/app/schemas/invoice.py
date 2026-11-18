from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, date

class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    invoice_number: str
    order_type: Optional[str] = None
    subtotal: float
    tax_rate: float
    tax_amount: float
    grand_total: float
    payment_status: str
    payment_method: Optional[str] = None
    due_date: Optional[date] = None
    paid_at: Optional[datetime] = None
    qr_code: Optional[str] = None
    created_at: Optional[datetime] = None
