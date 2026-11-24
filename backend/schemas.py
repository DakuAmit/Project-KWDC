"""
Pydantic Request & Response Validation Schemas for KTM-WDC
"""
from typing import Optional, List, Any, Union
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
    operating_location: Optional[str] = Field(default="Kathmandu Valley", description="Primary operating city/district")
    password: str = Field(..., min_length=6)
    confirm_password: Optional[str] = None

    @model_validator(mode="after")
    def check_passwords_match(self):
        if self.confirm_password and self.password != self.confirm_password:
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
    space_type: Any = SpaceType.COVERED_GODOWN
    input_unit: Any = AreaUnit.SQFT
    input_value: Optional[float] = None
    total_sqft: Optional[float] = None
    ceiling_height_ft: float = 12.0
    monthly_rate_per_sqft: Optional[float] = None
    base_rate_per_sqft: Optional[float] = None
    min_lease_months: int = 1
    
    # Location
    province: str = "Bagmati"
    district: str = "Kathmandu"
    municipality: Optional[str] = "Kathmandu"
    ward_no: int = 1
    neighborhood_landmark: Optional[str] = "Kathmandu Valley Hub"
    latitude: Optional[float] = 27.7172
    longitude: Optional[float] = 85.3240
    
    # Specs
    road_access_ft: Optional[float] = 20.0
    road_access_width_ft: Optional[float] = None
    has_three_phase_power: bool = False
    has_forklift_ramp: bool = False
    has_cctv: bool = False
    has_cold_storage: bool = False
    has_security_guard: bool = False
    has_raised_dock: bool = False
    has_forklift_access: bool = False
    has_fire_safety: bool = False
    temp_min_c: Optional[float] = None
    temp_max_c: Optional[float] = None

class MaintenanceHoldRequest(BaseModel):
    warehouse_id: Optional[int] = None
    is_on_hold: Optional[bool] = None
    is_on_maintenance_hold: Optional[bool] = None
    hold_reason_note: str

class BookingRequestCreate(BaseModel):
    warehouse_id: int
    requested_sqft: float = Field(..., gt=0)
    duration_months: int = Field(default=3, ge=1)
    client_intended_use: Optional[str] = "Commercial Freight"
    client_pan_vat: Optional[str] = None
    buyer_pan: Optional[str] = None

class InchargeReportCreate(BaseModel):
    warehouse_id: int
    log_type: str = "security_check"
    summary: str
    detailed_notes: str

class IncidentReportCreate(BaseModel):
    warehouse_id: int
    severity: Optional[str] = "low"
    title: Optional[str] = None
    observation_notes: Optional[str] = None
    incident_category: Optional[str] = "general"
    description: Optional[str] = None
    action_taken: Optional[str] = None
    police_alert_dispatched: bool = False

class GatePassCreate(BaseModel):
    warehouse_id: int
    client_id: Optional[int] = None
    movement_type: Optional[str] = "inbound"
    pass_type: Optional[str] = "inbound"
    vehicle_plate: str
    driver_name: str
    cargo_manifest: Optional[str] = None
    pallet_count: Optional[int] = 1
    unit_type: InventoryUnitType = InventoryUnitType.CARTOON
    scanned_units_count: Optional[int] = 1
    remarks: Optional[str] = None

class VehicleCreate(BaseModel):
    category: Any = VehicleCategory.SIX_WHEELER
    model_name: str
    license_plate: str
    bluebook_number: str
    payload_capacity_kg: float
    volume_capacity_cft: float = 0.0

class DriverCreate(BaseModel):
    full_name: str
    phone_number: str
    license_number: str
    citizenship_no: Optional[str] = "CTZ-VERIFIED"
    assigned_vehicle_id: Optional[int] = None

class InsuranceRequestCreate(BaseModel):
    warehouse_id: int
    booking_id: Optional[int] = None
    commodity_type: str
    declared_valuation_npr: float = Field(..., gt=0)
    coverage_scope: Optional[str] = "Fire, Lightning, Earthquake, Monsoon Flood, Burglary"
    stock_manifest_summary: Optional[str] = None
    manifest_summary: Optional[str] = None
    invoice_document_ref: Optional[str] = None

    @model_validator(mode="after")
    def resolve_manifest_summary(self):
        if not self.stock_manifest_summary and not self.manifest_summary:
            raise ValueError("Stock manifest summary is required.")
        if not self.stock_manifest_summary:
            self.stock_manifest_summary = self.manifest_summary
        return self

class InsuranceProcessRequest(BaseModel):
    underwriter_name: str = "Shikhar Insurance Co. Ltd."
    policy_number: Optional[str] = None
    premium_rate_percent: float = Field(default=0.25, ge=0.01)
    status: str = "ACTIVE_INSURED"
    admin_notes: Optional[str] = None
    duration_months: int = 12
