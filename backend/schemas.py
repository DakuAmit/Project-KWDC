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
    email: Optional[str] = None
    fleet_operator_type: Optional[str] = None

class SubmitKycRequest(BaseModel):
    # Backward compatibility
    pan_vat_number: Optional[str] = None
    document_url: Optional[str] = None

    # Property Owner KYC (STRICTLY Citizenship & Bank Account Proof per user directive)
    citizenship_number: Optional[str] = None
    citizenship_front_url: Optional[str] = None
    citizenship_back_url: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_account_name: Optional[str] = None
    bank_branch: Optional[str] = None
    bank_proof_doc_url: Optional[str] = None

    # Commercial Client KYC
    company_name: Optional[str] = None
    company_reg_number: Optional[str] = None
    company_pan_vat: Optional[str] = None
    company_reg_doc_url: Optional[str] = None
    company_pan_doc_url: Optional[str] = None
    authorized_signatory_name: Optional[str] = None
    authorized_signatory_doc_url: Optional[str] = None

    # Fleet Partner KYC
    fleet_operator_pan_vat: Optional[str] = None
    fleet_operator_reg_no: Optional[str] = None
    fleet_operator_doc_url: Optional[str] = None

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
    photo_urls: Optional[List[str]] = None

class OwnerChangeRequestCreate(BaseModel):
    request_type: str # DELISTING_15_DAYS, RATE_REVISION
    requested_rate_per_sqft: Optional[float] = None
    reason_note: str = Field(..., min_length=10)

class ClientDispatchOrderCreate(BaseModel):
    movement_type: str = "DIRECT_HAUL" # WAREHOUSE_DISPATCH or DIRECT_HAUL
    warehouse_id: Optional[int] = None
    cargo_description: str
    cargo_description_other: Optional[str] = None
    required_vehicle_category: str = "mini_truck"
    vehicle_category_other: Optional[str] = None
    pickup_address: str
    pickup_contact_name: str
    pickup_contact_phone: str
    pickup_lat: Optional[float] = 27.7172
    pickup_lng: Optional[float] = 85.3240
    destination_address: str
    consignee_name: str
    consignee_phone: str
    dest_lat: Optional[float] = 27.7000
    dest_lng: Optional[float] = 85.3000
    estimated_distance_km: Optional[float] = 8.5
    cargo_weight_kg: Optional[float] = 1000.0
    benchmark_fare_npr: Optional[float] = None
    client_offered_fare_npr: Optional[float] = None
    is_fragile: bool = False
    is_perishable: bool = False

class CounterOfferCreate(BaseModel):
    offered_fare_npr: float = Field(..., gt=0)
    counter_note: Optional[str] = None
    vehicle_id: Optional[int] = None
    driver_id: Optional[int] = None

class CounterOfferAcceptRequest(BaseModel):
    counter_offer_id: int

class MaintenanceHoldRequest(BaseModel):
    warehouse_id: Optional[int] = None
    is_on_hold: Optional[bool] = None
    is_on_maintenance_hold: Optional[bool] = None
    hold_reason_note: str

class BookingRequestCreate(BaseModel):
    warehouse_id: int
    requested_sqft: float = Field(..., gt=0)
    booking_duration_type: Optional[str] = "MONTHLY" # DAILY, WEEKLY, MONTHLY
    duration_value: Optional[int] = None
    duration_months: Optional[int] = Field(default=3, ge=1)
    client_intended_use: Optional[str] = "Commercial Freight"
    client_pan_vat: Optional[str] = None
    buyer_pan: Optional[str] = None

class BookingModifyRequest(BaseModel):
    action: str # EXPAND, DOWNSIZE, RENEW
    delta_sqft: Optional[float] = 0.0
    extra_duration_value: Optional[int] = 1
    duration_type: Optional[str] = "MONTHLY"

class StockItemCreate(BaseModel):
    warehouse_id: int
    booking_id: Optional[int] = None
    sku_code: Optional[str] = None
    item_name: str
    category: Optional[str] = "General Merchandise"
    unit_type: InventoryUnitType = InventoryUnitType.CARTOON
    quantity: int = Field(..., gt=0)
    gross_weight_kg: Optional[float] = 25.0
    bay_rack_location: Optional[str] = "Zone A / Bay-1"

class StockDispatchRequest(BaseModel):
    stock_item_id: Optional[int] = None
    booking_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    dispatch_all: bool = False
    quantity: Optional[int] = None
    dispatch_mode: str = "SELF_PICKUP" # SELF_PICKUP or KTM_FREIGHT
    vehicle_plate: Optional[str] = "SELF-PICKUP"
    driver_name: Optional[str] = "Authorized Carrier"
    destination_address: Optional[str] = None
    consignee_name: Optional[str] = None
    consignee_phone: Optional[str] = None
    required_vehicle_category: Optional[str] = "mini_truck"
    estimated_distance_km: Optional[float] = 10.0
    client_offered_fare_npr: Optional[float] = None
    remarks: Optional[str] = None

class InchargeStockVerifyRequest(BaseModel):
    bay_rack_location: Optional[str] = None
    verified_quantity: Optional[int] = None
    notes: Optional[str] = None

class SavedAddressCreate(BaseModel):
    label: str
    address: str
    contact_name: str
    contact_phone: str
    lat: Optional[float] = 27.7172
    lng: Optional[float] = 85.3240

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
    stock_item_id: Optional[int] = None
    booking_id: Optional[int] = None
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
    license_number: str = Field(..., min_length=3, description="Mandatory Commercial Driving License Number")
    license_category: Optional[str] = "Category B (Van / Pickup / Light 4-Wheeler)"
    license_categories: Optional[List[str]] = None
    id_document_type: Optional[str] = "CITIZENSHIP"  # CITIZENSHIP or NID
    citizenship_no: Optional[str] = None
    id_document_number: Optional[str] = None
    blood_group: Optional[str] = "O+"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    license_photo_url: Optional[str] = None
    license_photo_front_url: Optional[str] = None
    license_photo_back_url: Optional[str] = None
    citizenship_photo_url: Optional[str] = None
    id_doc_front_url: Optional[str] = None
    id_doc_back_url: Optional[str] = None
    has_clean_traffic_record: Optional[bool] = True
    is_standby: Optional[bool] = False
    is_self_driver: Optional[bool] = False
    assigned_vehicle_id: Optional[int] = None
    login_pin: Optional[str] = "1234"

    @model_validator(mode="after")
    def normalize_driver_fields(self):
        if self.license_categories and len(self.license_categories) > 0:
            cleaned = [c.strip() for c in self.license_categories if c and c.strip()]
            if cleaned:
                self.license_category = ", ".join(cleaned)
        if not self.citizenship_no and self.id_document_number:
            self.citizenship_no = self.id_document_number.strip()
        if not self.id_doc_front_url and self.citizenship_photo_url:
            self.id_doc_front_url = self.citizenship_photo_url
        return self

class DriverLoginRequest(BaseModel):
    phone_number: str
    pin: str

class DriverResetPinRequest(BaseModel):
    new_pin: str = Field(..., min_length=4, max_length=6)

class EmergencyReassignRequest(BaseModel):
    new_vehicle_id: int
    new_driver_id: int
    breakdown_reason: str = Field(..., min_length=5)

class OperatorTypeUpdateRequest(BaseModel):
    operator_type: str = Field(..., description="'INDEPENDENT_OWNER' or 'COMMERCIAL_3PL'")

class DeliveryCompleteRequest(BaseModel):
    delivery_otp: Optional[str] = None
    proof_photo_url: Optional[str] = None
    consignee_remarks: Optional[str] = None

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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=6)
    confirm_password: Optional[str] = None


class InsurancePayPremiumRequest(BaseModel):
    payment_method: str = "BANK_TRANSFER" # ESEWA, KHALTI, BANK_TRANSFER, IPS_CONNECT
    payment_ref: str = Field(..., min_length=3)


class InsuranceClaimCreate(BaseModel):
    incident_type: str = "WATER_DAMAGE"
    incident_date: str
    claim_amount_npr: float = Field(..., gt=0)
    description: str = Field(..., min_length=5)
    evidence_photo_url: Optional[str] = None


class InsuranceClaimProcessRequest(BaseModel):
    status: str = "APPROVED" # SURVEYING, APPROVED, REJECTED, SETTLED
    approved_payout_npr: float = Field(default=0.0, ge=0.0)
    admin_notes: Optional[str] = None


class SecurityAgencyProfileCreate(BaseModel):
    agency_name: str = Field(..., min_length=2)
    home_ministry_license_no: str = Field(..., min_length=3)
    emergency_contact_phone: str = Field(..., min_length=7)


class SecurityGuardCreate(BaseModel):
    guard_name: str = Field(..., min_length=2)
    phone_number: str = Field(..., min_length=7)
    assigned_warehouse_id: Optional[int] = None
    shift_type: str = "DAY"


class SecurityPatrolLogCreate(BaseModel):
    warehouse_id: int
    guard_id: Optional[int] = None
    shift_type: str = "NIGHT"
    perimeter_status: str = "ALL_CLEAR"
    notes: str = Field(..., min_length=3)
    photo_url: Optional[str] = None
