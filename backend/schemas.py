"""
Pydantic Request & Response Validation Schemas for KTM-WDC
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, model_validator
from backend.models import (
    UserRole, SpaceType, AreaUnit, InventoryUnitType,
    VehicleCategory, BookingStatus, FreightStatus, IncidentSeverity,
    KycStatus, PhysicalAuditStatus
)

class UserRegister(BaseModel):
    role: UserRole = UserRole.COMMERCIAL_CLIENT
    full_name: str = Field(..., min_length=2, description="Individual or Company Name")
    company_name: Optional[str] = None
    email: EmailStr
    phone_number: str = Field(..., min_length=7, description="Contact phone")
    operating_location: str = Field(default="Kathmandu Valley", description="Primary operating city/district")
    password: str = Field(..., min_length=6)
    confirm_password: str = Field(..., min_length=6)

    @model_validator(mode="after")
    def check_passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Password and Confirm Password do not match.")
        return self

class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(..., min_length=6, max_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_role: str
    full_name: str
    user_id: int
    is_verified: bool
    kyc_status: str

class SubmitKycRequest(BaseModel):
    pan_vat_number: Optional[str] = None
    document_url: Optional[str] = None

class PhysicalAuditSubmit(BaseModel):
    warehouse_id: int
    status: PhysicalAuditStatus
    audit_notes: str

class WarehouseCreate(BaseModel):
    title: str
    space_type: SpaceType = SpaceType.RESIDENTIAL_BASEMENT
    input_unit: AreaUnit = AreaUnit.SQFT
    input_value: float = Field(..., gt=0)
    ceiling_height_ft: float = 10.0
    monthly_rate_per_sqft: float = Field(..., gt=0)
    min_lease_months: int = 1
    
    # Location
    province: str = "Bagmati"
    district: str = "Kathmandu"
    municipality: str
    ward_no: int = 1
    neighborhood_landmark: str
    latitude: float
    longitude: float
    
    # Specs
    road_access_ft: float = 16.0
    has_three_phase_power: bool = False
    has_forklift_ramp: bool = False
    has_cctv: bool = False
    has_cold_storage: bool = False
    temp_min_c: Optional[float] = None
    temp_max_c: Optional[float] = None

class MaintenanceHoldRequest(BaseModel):
    warehouse_id: int
    is_on_hold: bool
    hold_reason_note: str

class BookingRequestCreate(BaseModel):
    warehouse_id: int
    requested_sqft: float = Field(..., gt=0)
    duration_months: int = Field(default=3, ge=1)
    buyer_pan: Optional[str] = None

class InchargeReportCreate(BaseModel):
    warehouse_id: int
    log_type: str
    summary: str
    detailed_notes: str

class IncidentReportCreate(BaseModel):
    warehouse_id: int
    incident_category: str
    severity: IncidentSeverity = IncidentSeverity.MINOR
    description: str
    action_taken: Optional[str] = None
    police_alert_dispatched: bool = False

class GatePassCreate(BaseModel):
    warehouse_id: int
    client_id: int
    pass_type: str
    vehicle_plate: str
    driver_name: str
    unit_type: InventoryUnitType = InventoryUnitType.CARTOON
    scanned_units_count: int
    remarks: Optional[str] = None

class VehicleCreate(BaseModel):
    category: VehicleCategory
    model_name: str
    license_plate: str
    bluebook_number: str
    payload_capacity_kg: float
    volume_capacity_cft: float = 0.0

class DriverCreate(BaseModel):
    full_name: str
    phone_number: str
    license_number: str
    citizenship_no: str
    assigned_vehicle_id: Optional[int] = None
