"""
Kathmandu Warehousing & Distribution Center (KTM-WDC)
Comprehensive Relational Database Models (SQLAlchemy ORM)

Includes:
- 7-Role RBAC:
  1. Property Owner
  2. Commercial Client
  3. Fleet Partner (Multi-Vehicle & Multi-Driver, from 2-Wheelers to Heavy Trailers)
  4. Warehouse Incharge (Assigned to one/multiple facilities, reporting directly to Admin)
  5. Equipment Owner
  6. Security Agency
  7. SuperAdmin
- Multi-Unit Real Estate Engine (sqft, sqm, aana, ropani, bigha, kattha, cuft)
- 10% Floor Space Partitioning constraints & Hold Notes
- Multi-Unit Inventory (Carton, Pallet, Container) with ISO/IEC 18004 QR
- Commercial Freight with 2-Wheelers to Heavy Haulers & Live Telemetry
- IRD Schedule 13 13% VAT FinTech Invoices
- Granular Incident Reporting (Minor Rat/Pest damage to Major structural breaches)
"""
import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Enum
)
from sqlalchemy.orm import relationship
from backend.database import Base

class UserRole(str, enum.Enum):
    PROPERTY_OWNER = "property_owner"
    COMMERCIAL_CLIENT = "commercial_client"
    FLEET_PARTNER = "fleet_partner"
    WAREHOUSE_INCHARGE = "warehouse_incharge"
    EQUIPMENT_OWNER = "equipment_owner"
    SECURITY_AGENCY = "security_agency"
    SUPERADMIN = "superadmin"

class SpaceType(str, enum.Enum):
    RESIDENTIAL_BASEMENT = "RESIDENTIAL_BASEMENT"
    COMMERCIAL_SHUTTER = "COMMERCIAL_SHUTTER"
    COVERED_GODOWN = "COVERED_GODOWN"
    WALLED_LAND_PLOT = "WALLED_LAND_PLOT"

class AreaUnit(str, enum.Enum):
    SQFT = "SQFT"       # Square Feet (Standard Base)
    SQM = "SQM"         # Square Meters
    AANA = "AANA"       # Nepali Hill Unit (342.25 sq ft)
    ROPANI = "ROPANI"   # Nepali Hill Unit (5476 sq ft)
    BIGHA = "BIGHA"     # Nepali Terai Unit (72900 sq ft)
    KATTHA = "KATTHA"   # Nepali Terai Unit (3645 sq ft)
    CUFT = "CUFT"       # Cubic Feet (Volume for High-Ceiling Godowns)

class InventoryUnitType(str, enum.Enum):
    CARTOON = "CARTOON"         # Individual Carton / Box
    PALLET = "PALLET"           # Wooden / Plastic Pallet
    CONTAINER = "CONTAINER"     # 20ft / 40ft Shipping Container

class VehicleCategory(str, enum.Enum):
    TWO_WHEELER = "TWO_WHEELER"         # Motorcycle / Delivery Scooter / Cargo Bike (< 50kg)
    THREE_WHEELER = "THREE_WHEELER"     # Cargo Auto-Tempo (300-500kg)
    MINI_TRUCK = "MINI_TRUCK"           # Tata Ace / Batta / Dost (750-1200kg)
    MEDIUM_PICKUP = "MEDIUM_PICKUP"     # Mahindra Bolero / 3-Ton Pickup (1.5-3 Ton)
    SIX_WHEELER = "SIX_WHEELER"         # Eicher / Tata 1109 Commercial (5-9 Ton)
    TEN_WHEELER = "TEN_WHEELER"         # Multi-Axle Heavy Hauler (16-25 Ton)
    CONTAINER_TRAILER = "CONTAINER_TRAILER" # 20ft / 40ft Container Bed (30+ Ton)

class BookingStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED_CONTRACT_DISPATCHED = "APPROVED_CONTRACT_DISPATCHED"
    ACTIVE_LEASED = "ACTIVE_LEASED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class FreightStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    ASSIGNED = "ASSIGNED"
    PICKUP_IN_PROGRESS = "PICKUP_IN_PROGRESS"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"

class PaymentStatus(str, enum.Enum):
    UNPAID = "UNPAID"
    PAID = "PAID"
    REFUNDED = "REFUNDED"

class IncidentSeverity(str, enum.Enum):
    MINOR = "MINOR"         # e.g., Minor rat nibbling on outer packaging
    MODERATE = "MODERATE"   # e.g., Moisture ingress, broken stack
    MAJOR = "MAJOR"         # e.g., Water leakage during monsoon, broken lock/seal
    CRITICAL = "CRITICAL"   # e.g., Fire hazard, structural collapse, burglary

class KycStatus(str, enum.Enum):
    PENDING_SUBMISSION = "PENDING_SUBMISSION"
    UNDER_REVIEW = "UNDER_REVIEW"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"

class PhysicalAuditStatus(str, enum.Enum):
    PENDING_INSPECTION = "PENDING_INSPECTION"
    AUDIT_SCHEDULED = "AUDIT_SCHEDULED"
    VERIFIED_PASSED = "VERIFIED_PASSED"
    REPAIRS_REQUIRED = "REPAIRS_REQUIRED"


# ---------------------------------------------------------------------------
# Module 1: Identity & RBAC
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    phone_number = Column(String(50), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    operating_location = Column(String(100), default="Kathmandu Valley")
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.COMMERCIAL_CLIENT, nullable=False)
    fleet_operator_type = Column(String(50), nullable=True, default=None) # "INDEPENDENT_OWNER", "COMMERCIAL_3PL", or None (unconfigured)
    
    # Verification & Security
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    otp_code = Column(String(6), nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)

    # KYC Verification
    kyc_status = Column(Enum(KycStatus), default=KycStatus.PENDING_SUBMISSION, nullable=False)
    kyc_pan_vat = Column(String(50), nullable=True)
    kyc_document_url = Column(String(500), nullable=True)
    kyc_verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    kyc_profile = relationship("UserKycProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    warehouses = relationship("Warehouse", foreign_keys="Warehouse.owner_id", back_populates="owner", cascade="all, delete-orphan")
    incharge_assignments = relationship("WarehouseInchargeAssignment", back_populates="incharge")
    incharge_reports = relationship("WarehouseActivityLog", back_populates="incharge")
    client_bookings = relationship("WarehouseRequest", back_populates="client")
    fleet_vehicles = relationship("Vehicle", back_populates="fleet_partner")
    fleet_drivers = relationship("Driver", back_populates="fleet_partner")
    dispatch_orders_as_client = relationship("DispatchOrder", foreign_keys="DispatchOrder.client_id", back_populates="client")
    equipment_items = relationship("HeavyEquipment", back_populates="owner")
    security_agency_profile = relationship("SecurityAgency", back_populates="user", uselist=False)


class UserKycProfile(Base):
    """
    Dedicated KYC verification dossier:
    - Property Owner: Strictly Nepalese Citizenship & Bank Account Proof (for 90% direct payouts).
    - Commercial Client: Company Registration, PAN/VAT certificate, Authorized Signatory.
    - Fleet Partner: Transport operator registration & PAN/VAT certificate.
    """
    __tablename__ = "user_kyc_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    role = Column(String(50), nullable=False)
    kyc_status = Column(Enum(KycStatus), default=KycStatus.PENDING_SUBMISSION, nullable=False)

    # 1. PROPERTY OWNER (Strictly Citizenship and Bank Account Proof per user directive)
    citizenship_number = Column(String(100), nullable=True)
    citizenship_front_url = Column(String(500), nullable=True)
    citizenship_back_url = Column(String(500), nullable=True)
    bank_name = Column(String(150), nullable=True)
    bank_account_number = Column(String(100), nullable=True)
    bank_account_name = Column(String(255), nullable=True)
    bank_branch = Column(String(150), nullable=True)
    bank_proof_doc_url = Column(String(500), nullable=True) # Cheque leaf or bank statement proof

    # 2. COMMERCIAL CLIENT
    company_name = Column(String(255), nullable=True)
    company_reg_number = Column(String(100), nullable=True)
    company_pan_vat = Column(String(50), nullable=True)
    company_reg_doc_url = Column(String(500), nullable=True)
    company_pan_doc_url = Column(String(500), nullable=True)
    authorized_signatory_name = Column(String(255), nullable=True)
    authorized_signatory_doc_url = Column(String(500), nullable=True)

    # 3. FLEET PARTNER
    fleet_operator_pan_vat = Column(String(50), nullable=True)
    fleet_operator_reg_no = Column(String(100), nullable=True)
    fleet_operator_doc_url = Column(String(500), nullable=True)

    # Compliance & Review
    admin_review_notes = Column(Text, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="kyc_profile")


# ---------------------------------------------------------------------------
# Module 2: Real Estate & 10% Floor Space Partitioning
# ---------------------------------------------------------------------------
class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    title = Column(String(255), nullable=False)
    space_type = Column(Enum(SpaceType), default=SpaceType.RESIDENTIAL_BASEMENT, nullable=False)
    
    # Space & Units (Normalized internally to sqft, while retaining original entry unit)
    total_sqft = Column(Float, nullable=False)
    available_sqft = Column(Float, nullable=False)
    clear_ceiling_height_ft = Column(Float, default=10.0) # For volume calculation
    original_input_unit = Column(Enum(AreaUnit), default=AreaUnit.SQFT)
    original_input_value = Column(Float, nullable=True)

    monthly_rate_per_sqft = Column(Float, nullable=False)
    client_rate_per_sqft = Column(Float, nullable=True)  # Admin-set client base tariff (falls back to monthly_rate_per_sqft if None)
    min_lease_months = Column(Integer, default=1)
    
    # Location
    province = Column(String(100), default="Bagmati")
    district = Column(String(100), default="Kathmandu")
    municipality = Column(String(100), nullable=False)
    ward_no = Column(Integer, default=1)
    neighborhood_landmark = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    
    # Physical Specs & Amenities
    road_access_ft = Column(Float, default=16.0)
    has_three_phase_power = Column(Boolean, default=False)
    has_forklift_ramp = Column(Boolean, default=False)
    has_cctv = Column(Boolean, default=False)
    has_cold_storage = Column(Boolean, default=False)
    temp_min_c = Column(Float, nullable=True)
    temp_max_c = Column(Float, nullable=True)

    # Physical Audit & Verification (On-Site inspection after registration)
    physical_audit_status = Column(Enum(PhysicalAuditStatus), default=PhysicalAuditStatus.PENDING_INSPECTION, nullable=False)
    physical_audit_notes = Column(Text, nullable=True)
    audited_by_incharge_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    audited_at = Column(DateTime, nullable=True)

    # Lifecycle & Audit
    is_approved = Column(Boolean, default=False)
    is_available = Column(Boolean, default=False)
    is_on_maintenance_hold = Column(Boolean, default=False)
    hold_reason_note = Column(Text, nullable=True)
    lease_contract_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id], back_populates="warehouses")
    incharge_auditor = relationship("User", foreign_keys=[audited_by_incharge_id])
    photos = relationship("WarehousePhoto", back_populates="warehouse", cascade="all, delete-orphan")
    requests = relationship("WarehouseRequest", back_populates="warehouse")
    stock_items = relationship("StockItem", back_populates="warehouse")
    incharge_assignments = relationship("WarehouseInchargeAssignment", back_populates="warehouse")
    activity_logs = relationship("WarehouseActivityLog", back_populates="warehouse")
    change_requests = relationship("WarehouseChangeRequest", back_populates="warehouse", cascade="all, delete-orphan")


class WarehousePhoto(Base):
    __tablename__ = "warehouse_photos"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    photo_url = Column(String(500), nullable=False)
    caption = Column(String(255), nullable=True)

    warehouse = relationship("Warehouse", back_populates="photos")


class WarehouseInchargeAssignment(Base):
    """
    Maps a Warehouse Incharge to one or multiple warehouses.
    """
    __tablename__ = "warehouse_incharge_assignments"

    id = Column(Integer, primary_key=True, index=True)
    incharge_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    assigned_date = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    incharge = relationship("User", back_populates="incharge_assignments")
    warehouse = relationship("Warehouse", back_populates="incharge_assignments")


class WarehouseActivityLog(Base):
    """
    Direct reports from the Warehouse Incharge to Admin regarding all activities:
    inspections, daily shift summaries, stock discrepancies, and maintenance notes.
    """
    __tablename__ = "warehouse_activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    incharge_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    log_type = Column(String(100), nullable=False) # "DAILY_SUMMARY", "STOCK_INSPECTION", "MAINTENANCE_ALERT", "CLIENT_VISIT"
    summary = Column(String(255), nullable=False)
    detailed_notes = Column(Text, nullable=False)
    photos_url = Column(String(500), nullable=True)
    admin_reviewed = Column(Boolean, default=False)
    admin_feedback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    warehouse = relationship("Warehouse", back_populates="activity_logs")
    incharge = relationship("User", back_populates="incharge_reports")


class WarehouseRequest(Base):
    """
    Client Lease Booking enforcing:
    - 10% Floor Block Rule: Ceil(req / (tot * 0.10)) * (tot * 0.10)
    - Zero Holding Liability for KWDC when idle
    - Privacy Shield (Owner and Client never see each other's details)
    """
    __tablename__ = "warehouse_requests"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    
    requested_sqft = Column(Float, nullable=False)
    allocated_billed_sqft = Column(Float, nullable=False)
    
    monthly_base_rent = Column(Float, nullable=False)
    kwdc_margin_amount = Column(Float, nullable=False)
    vat_13_percent = Column(Float, nullable=False)
    total_monthly_bill = Column(Float, nullable=False)
    
    status = Column(Enum(BookingStatus), default=BookingStatus.PENDING_REVIEW, nullable=False)
    lease_start_date = Column(DateTime, nullable=True)
    lease_end_date = Column(DateTime, nullable=True)

    # Flexible 3-Tier Storage Duration (DAILY, WEEKLY, MONTHLY)
    booking_duration_type = Column(String(20), default="MONTHLY")  # DAILY, WEEKLY, MONTHLY
    duration_value = Column(Integer, default=3)                    # e.g. 3 days, 2 weeks, 6 months
    duration_days = Column(Integer, default=90)                    # Total days normalized
    client_intended_use = Column(String(255), default="Commercial Freight")

    # 60-Day Advance Payment, Escalating Lien Alerts & Auction Forfeiture
    advance_payment_status = Column(String(50), default="PAYMENT_DUE") # PAID, PAYMENT_DUE, OVERDUE_MONTH_1, NOTICE_15_DAYS, NOTICE_7_DAYS, GATE_FROZEN_5_DAYS, FINAL_NOTICE_48_HOURS, FORFEITED_AUCTION
    overdue_since = Column(DateTime, nullable=True)
    default_countdown_deadline = Column(DateTime, nullable=True)
    is_gate_frozen = Column(Boolean, default=False)
    is_forfeited = Column(Boolean, default=False)
    last_reminder_sent_at = Column(DateTime, nullable=True)
    last_reminder_stage = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("User", back_populates="client_bookings")
    warehouse = relationship("Warehouse", back_populates="requests")
    invoice = relationship("TaxInvoice", back_populates="storage_booking", uselist=False)
    lien_notifications = relationship("LienNotificationLog", back_populates="booking", cascade="all, delete-orphan")
    auction_items = relationship("StockAuctionItem", back_populates="booking", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Module 3: Logistics & Freight Telemetry (Fleet Partner 2-Wheeler to Hauler)
# ---------------------------------------------------------------------------
class Vehicle(Base):
    """
    Fleet Partner Vehicle. Supports 2-Wheelers up to Heavy Container Trailers.
    """
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    fleet_partner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    category = Column(Enum(VehicleCategory), default=VehicleCategory.MINI_TRUCK, nullable=False)
    model_name = Column(String(100), nullable=False) # e.g. "Honda Dio 110", "Tata Ace HT", "Bolero Camper", "Eicher Pro 3015"
    license_plate = Column(String(50), unique=True, index=True, nullable=False)
    bluebook_number = Column(String(100), nullable=False)
    bluebook_photo_url = Column(String(500), nullable=True)
    
    payload_capacity_kg = Column(Float, nullable=False) # e.g. 30kg for bike, 10000kg for hauler
    volume_capacity_cft = Column(Float, default=0.0)
    is_verified = Column(Boolean, default=False)
    is_available = Column(Boolean, default=True)

    # Telemetry Cache
    current_lat = Column(Float, nullable=True)
    current_lng = Column(Float, nullable=True)
    last_telemetry_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    fleet_partner = relationship("User", back_populates="fleet_vehicles")
    drivers = relationship("Driver", foreign_keys="[Driver.assigned_vehicle_id]", back_populates="assigned_vehicle")
    dispatches = relationship("DispatchOrder", foreign_keys="[DispatchOrder.vehicle_id]", back_populates="vehicle")


class Driver(Base):
    """
    Individual driver employed or rostered by a Fleet Partner.
    """
    __tablename__ = "drivers"

    id = Column(Integer, primary_key=True, index=True)
    fleet_partner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    
    full_name = Column(String(255), nullable=False)
    phone_number = Column(String(50), unique=True, nullable=False)
    license_number = Column(String(100), unique=True, nullable=False)
    license_category = Column(String(255), default="Category B (Van / Pickup / Light 4-Wheeler)")
    id_document_type = Column(String(50), default="CITIZENSHIP") # CITIZENSHIP or NID
    citizenship_no = Column(String(100), nullable=False)
    license_photo_url = Column(String(500), nullable=True)
    license_photo_front_url = Column(String(500), nullable=True)
    license_photo_back_url = Column(String(500), nullable=True)
    citizenship_photo_url = Column(String(500), nullable=True)
    id_doc_front_url = Column(String(500), nullable=True)
    id_doc_back_url = Column(String(500), nullable=True)
    blood_group = Column(String(10), nullable=True)
    emergency_contact_name = Column(String(255), nullable=True)
    emergency_contact_phone = Column(String(50), nullable=True)
    has_clean_traffic_record = Column(Boolean, default=True)
    is_standby = Column(Boolean, default=False)
    login_pin = Column(String(255), default="1234") # 4-digit access PIN for Driver Run Interface
    kyc_status = Column(Enum(KycStatus), default=KycStatus.PENDING_SUBMISSION, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    fleet_partner = relationship("User", back_populates="fleet_drivers")
    assigned_vehicle = relationship("Vehicle", foreign_keys=[assigned_vehicle_id], back_populates="drivers")
    dispatches = relationship("DispatchOrder", foreign_keys="[DispatchOrder.driver_id]", back_populates="driver")


class DispatchOrder(Base):
    """
    Commercial freight order with origin and up to 5 multi-drop delivery stops,
    distance-tiered margins, live GPS telemetry broadcast, and digital signature POD.
    """
    __tablename__ = "dispatch_orders"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    fleet_partner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=True)

    cargo_description = Column(String(255), default="Commercial Freight")
    required_vehicle_category = Column(Enum(VehicleCategory), default=VehicleCategory.MINI_TRUCK)
    pickup_address = Column(String(255), nullable=False)
    pickup_lat = Column(Float, nullable=False)
    pickup_lng = Column(Float, nullable=False)

    total_distance_km = Column(Float, default=0.0)
    base_freight_tariff = Column(Float, nullable=False)
    kwdc_margin_amount = Column(Float, nullable=False)
    vat_13_percent = Column(Float, nullable=False)
    total_fare_npr = Column(Float, nullable=False)

    status = Column(Enum(FreightStatus), default=FreightStatus.REQUESTED, nullable=False)
    live_lat = Column(Float, nullable=True)
    live_lng = Column(Float, nullable=True)
    telemetry_heading = Column(Float, nullable=True)
    last_telemetry_at = Column(DateTime, nullable=True)

    consignee_signature_url = Column(String(500), nullable=True)
    delivery_proof_photo_url = Column(String(500), nullable=True)
    delivery_otp = Column(String(6), nullable=True)
    delivered_at = Column(DateTime, nullable=True)

    # Option A: InDrive-style Pricing & Counter-Offer Negotiations
    benchmark_fare_npr = Column(Float, nullable=True)
    client_offered_fare_npr = Column(Float, nullable=True)
    cargo_weight_kg = Column(Float, default=1000.0)

    # Emergency Breakdown Mid-Trip Reassignment Tracking
    reassigned_from_vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    reassigned_from_driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=True)
    reassignment_reason = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("User", foreign_keys=[client_id], back_populates="dispatch_orders_as_client")
    vehicle = relationship("Vehicle", foreign_keys=[vehicle_id], back_populates="dispatches")
    driver = relationship("Driver", foreign_keys=[driver_id], back_populates="dispatches")
    reassigned_from_vehicle = relationship("Vehicle", foreign_keys=[reassigned_from_vehicle_id])
    reassigned_from_driver = relationship("Driver", foreign_keys=[reassigned_from_driver_id])
    stops = relationship("DeliveryStop", back_populates="dispatch_order", cascade="all, delete-orphan")
    counter_offers = relationship("FreightCounterOffer", back_populates="order", cascade="all, delete-orphan")
    invoice = relationship("TaxInvoice", back_populates="freight_order", uselist=False)


class DeliveryStop(Base):
    __tablename__ = "delivery_stops"

    id = Column(Integer, primary_key=True, index=True)
    dispatch_order_id = Column(Integer, ForeignKey("dispatch_orders.id"), nullable=False)
    stop_sequence = Column(Integer, nullable=False)
    consignee_name = Column(String(255), nullable=False)
    consignee_phone = Column(String(50), nullable=False)
    destination_address = Column(String(255), nullable=False)
    dest_lat = Column(Float, nullable=False)
    dest_lng = Column(Float, nullable=False)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)

    dispatch_order = relationship("DispatchOrder", back_populates="stops")


class FreightCounterOffer(Base):
    """
    InDrive-style negotiation counter-offer submitted by Drivers / Fleet Partners.
    """
    __tablename__ = "freight_counter_offers"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("dispatch_orders.id"), nullable=False)
    fleet_partner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)

    offered_fare_npr = Column(Float, nullable=False)
    counter_note = Column(String(255), nullable=True) # e.g. "Includes helper for loading", "Ready in 10 mins"
    status = Column(String(50), default="PENDING") # PENDING, ACCEPTED, REJECTED, WITHDRAWN
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("DispatchOrder", back_populates="counter_offers")
    fleet_partner = relationship("User", foreign_keys=[fleet_partner_id])
    driver = relationship("Driver", foreign_keys=[driver_id])
    vehicle = relationship("Vehicle", foreign_keys=[vehicle_id])


# ---------------------------------------------------------------------------
# Module 4: Inventory & ISO/IEC 18004 QR (Carton, Pallet, Container)
# ---------------------------------------------------------------------------
class StockItem(Base):
    __tablename__ = "stock_items"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    
    sku_code = Column(String(100), unique=True, index=True, nullable=False)
    item_name = Column(String(255), nullable=False)
    category = Column(String(100), default="General Merchandise")
    unit_type = Column(Enum(InventoryUnitType), default=InventoryUnitType.CARTOON, nullable=False)
    total_quantity = Column(Integer, default=0)
    inward_date = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    warehouse = relationship("Warehouse", back_populates="stock_items")
    units = relationship("InventoryUnit", back_populates="stock_item", cascade="all, delete-orphan")


class InventoryUnit(Base):
    """
    Physical unit tracking: Individual Carton, Pallet, or Shipping Container.
    Each holds its unique cryptographic QR and tracking status.
    """
    __tablename__ = "inventory_units"

    id = Column(Integer, primary_key=True, index=True)
    stock_item_id = Column(Integer, ForeignKey("stock_items.id"), nullable=False)
    unit_type = Column(Enum(InventoryUnitType), default=InventoryUnitType.CARTOON, nullable=False)
    serial_or_container_no = Column(String(100), unique=True, index=True, nullable=False) # e.g. "MSKU-9988112" or "BOX-KTM-001"
    qr_code_hash = Column(String(255), unique=True, nullable=False)
    gross_weight_kg = Column(Float, default=1.0)
    status = Column(String(50), default="IN_STORAGE") # IN_STORAGE, DISPATCHED, DELIVERED
    bay_rack_location = Column(String(100), default="Bay-1 / Rack-A")
    created_at = Column(DateTime, default=datetime.utcnow)

    stock_item = relationship("StockItem", back_populates="units")


class GatePass(Base):
    __tablename__ = "gate_passes"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    incharge_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Inspected/Authorized by Incharge
    pass_type = Column(String(20), nullable=False) # INWARD, OUTWARD
    vehicle_plate = Column(String(50), nullable=False)
    driver_name = Column(String(255), nullable=False)
    unit_type = Column(Enum(InventoryUnitType), default=InventoryUnitType.CARTOON)
    scanned_units_count = Column(Integer, default=0)
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    warehouse = relationship("Warehouse")
    client = relationship("User", foreign_keys=[client_id])
    incharge = relationship("User", foreign_keys=[incharge_id])


# ---------------------------------------------------------------------------
# Module 5: FinTech & Nepal IRD Schedule 13 13% VAT
# ---------------------------------------------------------------------------
class TaxInvoice(Base):
    __tablename__ = "tax_invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(100), unique=True, index=True, nullable=False)
    
    storage_booking_id = Column(Integer, ForeignKey("warehouse_requests.id"), nullable=True)
    freight_order_id = Column(Integer, ForeignKey("dispatch_orders.id"), nullable=True)
    
    buyer_name = Column(String(255), nullable=False)
    buyer_pan_vat = Column(String(50), nullable=True)
    seller_name = Column(String(255), default="Kathmandu Warehousing & Distribution Center Pvt. Ltd.")
    seller_pan_vat = Column(String(50), default="600987654")
    
    taxable_base_amount = Column(Float, nullable=False)
    kwdc_admin_margin = Column(Float, nullable=False)
    vat_13_percent = Column(Float, nullable=False)
    gross_total_npr = Column(Float, nullable=False)
    
    qr_payload = Column(Text, nullable=False)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.UNPAID, nullable=False)
    issued_at = Column(DateTime, default=datetime.utcnow)

    storage_booking = relationship("WarehouseRequest", back_populates="invoice")
    freight_order = relationship("DispatchOrder", back_populates="invoice")


# ---------------------------------------------------------------------------
# Module 5.1: Stock & Cargo Underwriting Insurance
# ---------------------------------------------------------------------------
class StockInsurancePolicy(Base):
    __tablename__ = "stock_insurance_policies"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    booking_id = Column(Integer, ForeignKey("warehouse_requests.id"), nullable=True)

    policy_number = Column(String(100), unique=True, index=True, nullable=True)
    commodity_type = Column(String(150), nullable=False)
    declared_valuation_npr = Column(Float, nullable=False)
    coverage_scope = Column(String(255), default="Fire, Lightning, Earthquake, Monsoon Flood, Burglary")
    stock_manifest_summary = Column(Text, nullable=False)
    invoice_document_ref = Column(String(255), nullable=True)

    underwriter_name = Column(String(255), default="Shikhar Insurance Co. Ltd.")
    premium_rate_percent = Column(Float, default=0.25)
    premium_amount_npr = Column(Float, default=0.0)
    vat_13_percent = Column(Float, default=0.0)
    total_payable_npr = Column(Float, default=0.0)

    status = Column(String(50), default="REQUESTED", nullable=False)
    coverage_start_date = Column(DateTime, nullable=True)
    coverage_end_date = Column(DateTime, nullable=True)
    admin_notes = Column(Text, nullable=True)
    certificate_qr_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("User", foreign_keys=[client_id])
    warehouse = relationship("Warehouse", foreign_keys=[warehouse_id])
    booking = relationship("WarehouseRequest", foreign_keys=[booking_id])


# ---------------------------------------------------------------------------
# Module 6: Heavy Machinery Fleet
# ---------------------------------------------------------------------------
class HeavyEquipment(Base):
    __tablename__ = "heavy_equipments"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    equipment_type = Column(String(100), nullable=False)
    model_name = Column(String(255), nullable=False)
    registration_no = Column(String(100), nullable=True)
    capacity_ton = Column(Float, nullable=False)
    hourly_rate_npr = Column(Float, default=1500.0)
    daily_rate_npr = Column(Float, nullable=False)
    monthly_rate_npr = Column(Float, nullable=False)
    operator_included = Column(Boolean, default=True)
    location_city = Column(String(100), default="Kathmandu")
    photo_url = Column(String(500), nullable=True)
    is_approved = Column(Boolean, default=False)
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="equipment_items")
    jobs = relationship("EquipmentJob", back_populates="equipment")


class EquipmentJob(Base):
    __tablename__ = "equipment_jobs"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("heavy_equipments.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    duration_type = Column(String(50), default="DAILY")
    duration_units = Column(Integer, default=1)
    site_address = Column(String(255), default="Kathmandu Valley Facility")
    notes = Column(String(500), nullable=True)
    base_cost_npr = Column(Float, default=0.0)
    platform_fee_npr = Column(Float, default=0.0)
    vat_13_percent = Column(Float, default=0.0)
    total_cost_npr = Column(Float, nullable=False)
    status = Column(String(50), default="CONFIRMED")
    start_date = Column(DateTime, default=datetime.utcnow)

    equipment = relationship("HeavyEquipment", back_populates="jobs")


# ---------------------------------------------------------------------------
# Module 8: Persistent Media Uploads (Works across Vercel & Mobile Apps)
# ---------------------------------------------------------------------------
class MediaAsset(Base):
    __tablename__ = "media_assets"

    id = Column(Integer, primary_key=True, index=True)
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), default="image/jpeg")
    data_base64 = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Module 7: Security Agency & Granular Incident Escalation
# ---------------------------------------------------------------------------
class SecurityAgency(Base):
    __tablename__ = "security_agencies"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    agency_name = Column(String(255), nullable=False)
    home_ministry_license_no = Column(String(100), unique=True, nullable=False)
    emergency_contact_phone = Column(String(50), nullable=False)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="security_agency_profile")
    guards = relationship("GuardPersonnel", back_populates="agency")


class GuardPersonnel(Base):
    __tablename__ = "guard_personnel"

    id = Column(Integer, primary_key=True, index=True)
    agency_id = Column(Integer, ForeignKey("security_agencies.id"), nullable=False)
    guard_name = Column(String(255), nullable=False)
    phone_number = Column(String(50), nullable=False)
    assigned_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    shift_type = Column(String(50), default="DAY")
    is_active = Column(Boolean, default=True)

    agency = relationship("SecurityAgency", back_populates="guards")
    incidents = relationship("IncidentReport", back_populates="guard")


class IncidentReport(Base):
    """
    Granular incident reporting:
    - Minor rat/rodent damage on packaging
    - Monsoon water seepage
    - Seal tampering
    - Structural cracks
    - Fire hazard or burglary
    With 1-click Admin and Nepal Police notification.
    """
    __tablename__ = "incident_reports"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    guard_id = Column(Integer, ForeignKey("guard_personnel.id"), nullable=True)
    incharge_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    incident_category = Column(String(100), nullable=False) # e.g. "RODENT_PEST_DAMAGE", "WATER_SEEPAGE", "SEAL_TAMPERING", "FIRE_ALERT"
    severity = Column(Enum(IncidentSeverity), default=IncidentSeverity.MINOR, nullable=False)
    description = Column(Text, nullable=False)
    evidence_photo_url = Column(String(500), nullable=True)
    
    action_taken = Column(Text, nullable=True) # e.g., "Pest trap set", "Goods moved to dry rack", "Police alerted"
    police_alert_dispatched = Column(Boolean, default=False)
    admin_notified = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    guard = relationship("GuardPersonnel", back_populates="incidents")


# ---------------------------------------------------------------------------
# Module 8: SuperAdmin Platform Configuration & Fare Tariff Engine
# ---------------------------------------------------------------------------
class PlatformConfig(Base):
    """
    Central Admin control for platform margins, vehicle base flag drops,
    per-KM tariffs, and weight tiers.
    """
    __tablename__ = "platform_configs"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String(100), unique=True, default="DEFAULT_CONFIG", nullable=False)

    # 1. Platform Commission / Margin (Admin configurable, e.g. 10.0 for 10%)
    platform_margin_percent = Column(Float, default=10.0)

    # 2. Base Flag Drop by Vehicle Category (NPR)
    flag_drop_van_pickup = Column(Float, default=1200.0)        # Pickup / Tata Ace / Bolero (< 1.5T)
    flag_drop_mini_truck = Column(Float, default=1800.0)        # Mini Truck (1.5T - 3.5T)
    flag_drop_heavy_truck = Column(Float, default=3200.0)       # Heavy Truck (3.5T - 10T)
    flag_drop_container_trailer = Column(Float, default=5000.0) # Container / Trailer (> 10T)

    # 3. Distance Rate (NPR per KM)
    rate_per_km_van_pickup = Column(Float, default=65.0)
    rate_per_km_mini_truck = Column(Float, default=85.0)
    rate_per_km_heavy_truck = Column(Float, default=125.0)
    rate_per_km_container_trailer = Column(Float, default=175.0)

    # 4. Cargo Weight Surcharge (NPR per Metric Tonne)
    weight_rate_per_tonne = Column(Float, default=150.0)

    # 5. Tax & Adjustments
    vat_rate_percent = Column(Float, default=13.0)
    fuel_multiplier = Column(Float, default=1.0)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Module 9: Warehouseman's Lien, Escalating Notifications & Stock Auction
# ---------------------------------------------------------------------------
class LienNotificationLog(Base):
    """
    Audit log of escalating overdue payment reminders dispatched to clients:
    - MONTH_1 (Day 30): Grace period notice
    - NOTICE_15_DAYS (Day 45): 15 days left before forfeiture
    - NOTICE_7_DAYS (Day 53): 1 week urgent legal notice
    - GATE_FROZEN_5_DAYS (Day 55): 5 days left, outbound gate passes blocked
    - FINAL_NOTICE_48_HOURS (Day 58): 2 days (48 hrs) final warning
    - FORFEITED (Day 60): Stock ownership transferred to KTM-WDC for auction
    """
    __tablename__ = "lien_notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("warehouse_requests.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    stage = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    email_dispatched = Column(Boolean, default=False)
    sent_at = Column(DateTime, default=datetime.utcnow)

    booking = relationship("WarehouseRequest", back_populates="lien_notifications")
    client = relationship("User")


class StockAuctionItem(Base):
    """
    Inventory forfeited to KTM-WDC after 60 days of lease non-payment
    (or short-term overstay forfeiture), catalogued for liquidation auction.
    """
    __tablename__ = "stock_auction_items"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("warehouse_requests.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    lot_number = Column(String(100), unique=True, nullable=False)
    item_summary = Column(Text, nullable=False)
    estimated_valuation_npr = Column(Float, default=0.0)
    arrears_owed_npr = Column(Float, default=0.0)
    reserve_price_npr = Column(Float, default=0.0)
    winning_bid_npr = Column(Float, nullable=True)

    auction_status = Column(String(50), default="CATALOGUED") # CATALOGUED, AUCTION_ACTIVE, SOLD, REDEEMED
    buyer_name = Column(String(255), nullable=True)
    buyer_phone = Column(String(50), nullable=True)
    admin_notes = Column(Text, nullable=True)

    forfeited_at = Column(DateTime, default=datetime.utcnow)
    auction_scheduled_at = Column(DateTime, nullable=True)
    sold_at = Column(DateTime, nullable=True)

    booking = relationship("WarehouseRequest", back_populates="auction_items")
    warehouse = relationship("Warehouse")
    client = relationship("User")


class ClientSavedAddress(Base):
    """
    Saved pickup / consignee delivery hubs for rapid 1-click dispatch scheduling.
    """
    __tablename__ = "client_saved_addresses"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    label = Column(String(100), nullable=False)        # e.g. "Kalanki Wholesale Depot"
    address = Column(String(255), nullable=False)
    contact_name = Column(String(150), nullable=False)
    contact_phone = Column(String(50), nullable=False)
    lat = Column(Float, default=27.7172)
    lng = Column(Float, default=85.3240)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("User")


class WarehouseChangeRequest(Base):
    """
    Sanctioned change workflow for Property Owners after Admin lockout:
    - 15-Day Notice Unleased Delisting Request
    - Annual Tariff / Rate Revision Request
    """
    __tablename__ = "warehouse_change_requests"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    request_type = Column(String(50), nullable=False) # DELISTING_15_DAYS, RATE_REVISION
    requested_rate_per_sqft = Column(Float, nullable=True)
    reason_note = Column(Text, nullable=False)
    status = Column(String(50), default="PENDING_REVIEW") # PENDING_REVIEW, APPROVED, REJECTED
    admin_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    warehouse = relationship("Warehouse", back_populates="change_requests")
    owner = relationship("User")
