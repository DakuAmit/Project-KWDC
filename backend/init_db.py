"""
Database initialization and seeding script for KTM-WDC.
Supports Supabase PostgreSQL (with CASCADE schema reset) and SQLite.
"""
from datetime import datetime, timezone, timedelta
import os
from sqlalchemy import text
from passlib.context import CryptContext
from backend.database import engine, Base, SessionLocal
from backend.models import (
    User, UserRole, Warehouse, SpaceType, AreaUnit, WarehousePhoto,
    Vehicle, VehicleCategory, Driver, StockItem, InventoryUnit, InventoryUnitType,
    HeavyEquipment, SecurityAgency, GuardPersonnel, TaxInvoice, PaymentStatus,
    WarehouseRequest, BookingStatus, WarehouseInchargeAssignment,
    WarehouseActivityLog, IncidentReport, IncidentSeverity
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_pw(password: str) -> str:
    return pwd_context.hash(password)

def init_db():
    print("Resetting database schema...")
    with engine.connect() as conn:
        try:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
            conn.commit()
            print("PostgreSQL public schema reset with CASCADE.")
        except Exception as e:
            print("Note on drop schema:", e)
            Base.metadata.drop_all(bind=engine)

    print("Creating all database tables on Supabase PostgreSQL...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    now = datetime.now(timezone.utc)
    print("Seeding full KTM-WDC platform data with all 7 roles...")

    # 1. SuperAdmin
    admin = User(
        email="admin@kwdc.com.np",
        phone_number="+977-9801000001",
        full_name="KTM-WDC Master Admin",
        hashed_password=hash_pw("Admin@123"),
        role=UserRole.SUPERADMIN,
        is_active=True,
        is_verified=True
    )
    db.add(admin)

    # 2. Property Owner
    owner = User(
        email="ram.shrestha@gmail.com",
        phone_number="+977-9851023456",
        full_name="Ram Bahadur Shrestha",
        hashed_password=hash_pw("Owner@123"),
        role=UserRole.PROPERTY_OWNER,
        is_active=True,
        is_verified=True
    )
    db.add(owner)

    # 3. Commercial Client
    client = User(
        email="purchase@himalayanlogistics.com.np",
        phone_number="+977-9841987654",
        full_name="Himalayan Organics & Traders",
        hashed_password=hash_pw("Client@123"),
        role=UserRole.COMMERCIAL_CLIENT,
        is_active=True,
        is_verified=True
    )
    db.add(client)

    # 4. Fleet Partner
    fleet_partner = User(
        email="operations@kathmandufleet.com.np",
        phone_number="+977-9812345678",
        full_name="Kathmandu Fast Express Fleet",
        hashed_password=hash_pw("Fleet@123"),
        role=UserRole.FLEET_PARTNER,
        is_active=True,
        is_verified=True
    )
    db.add(fleet_partner)

    # 5. Warehouse Incharge
    incharge = User(
        email="incharge.koteshwor@kwdc.com.np",
        phone_number="+977-9861234567",
        full_name="Suman Adhikari (Warehouse Incharge)",
        hashed_password=hash_pw("Incharge@123"),
        role=UserRole.WAREHOUSE_INCHARGE,
        is_active=True,
        is_verified=True
    )
    db.add(incharge)

    # 6. Heavy Equipment Owner
    equip_owner = User(
        email="rentals@nepalcranes.com.np",
        phone_number="+977-9803344556",
        full_name="Bagmati Heavy Plant Hire",
        hashed_password=hash_pw("Equip@123"),
        role=UserRole.EQUIPMENT_OWNER,
        is_active=True,
        is_verified=True
    )
    db.add(equip_owner)

    # 7. Licensed Security Agency
    sec_user = User(
        email="contact@garudasecurity.com.np",
        phone_number="+977-9807766554",
        full_name="Garuda Protection Services Pvt. Ltd.",
        hashed_password=hash_pw("Security@123"),
        role=UserRole.SECURITY_AGENCY,
        is_active=True,
        is_verified=True
    )
    db.add(sec_user)
    db.commit()

    # Seed Warehouses
    w1 = Warehouse(
        owner_id=owner.id,
        title="Koteshwor Highway Dry Basement Storage",
        space_type=SpaceType.RESIDENTIAL_BASEMENT,
        total_sqft=10000.0,
        available_sqft=10000.0,
        clear_ceiling_height_ft=11.5,
        original_input_unit=AreaUnit.SQFT,
        original_input_value=10000.0,
        monthly_rate_per_sqft=35.0,
        min_lease_months=3,
        province="Bagmati",
        district="Kathmandu",
        municipality="Kathmandu Metropolitan - 32",
        ward_no=32,
        neighborhood_landmark="Near Koteshwor Chowk overhead bridge, 150m inside Mahadevsthan road",
        latitude=27.6754,
        longitude=85.3458,
        road_access_ft=20.0,
        has_three_phase_power=True,
        has_forklift_ramp=True,
        has_cctv=True,
        has_cold_storage=False,
        is_approved=True,
        is_available=True,
        is_on_maintenance_hold=False
    )
    db.add(w1)

    w2 = Warehouse(
        owner_id=owner.id,
        title="Patan Industrial Shutter (8 Aana Ground Floor)",
        space_type=SpaceType.COMMERCIAL_SHUTTER,
        total_sqft=2738.0,
        available_sqft=2738.0,
        clear_ceiling_height_ft=12.0,
        original_input_unit=AreaUnit.AANA,
        original_input_value=8.0,
        monthly_rate_per_sqft=45.0,
        min_lease_months=1,
        province="Bagmati",
        district="Lalitpur",
        municipality="Lalitpur Metropolitan - 4",
        ward_no=4,
        neighborhood_landmark="Patan Dhoka main road, adjoining Krishna Galli",
        latitude=27.6801,
        longitude=85.3215,
        road_access_ft=24.0,
        has_three_phase_power=True,
        has_forklift_ramp=False,
        has_cctv=True,
        has_cold_storage=False,
        is_approved=True,
        is_available=True,
        is_on_maintenance_hold=False
    )
    db.add(w2)

    w3 = Warehouse(
        owner_id=owner.id,
        title="Birgunj Dry Port High-Capacity Godown (1 Bigha Plot)",
        space_type=SpaceType.COVERED_GODOWN,
        total_sqft=72900.0,
        available_sqft=72900.0,
        clear_ceiling_height_ft=22.0,
        original_input_unit=AreaUnit.BIGHA,
        original_input_value=1.0,
        monthly_rate_per_sqft=25.0,
        min_lease_months=6,
        province="Madhesh",
        district="Parsa",
        municipality="Birgunj Metropolitan - 14",
        ward_no=14,
        neighborhood_landmark="Directly on Dry Port Highway Bypass, ICP Gate 2",
        latitude=27.0125,
        longitude=84.8764,
        road_access_ft=40.0,
        has_three_phase_power=True,
        has_forklift_ramp=True,
        has_cctv=True,
        has_cold_storage=True,
        temp_min_c=2.0,
        temp_max_c=8.0,
        is_approved=True,
        is_available=True,
        is_on_maintenance_hold=False
    )
    db.add(w3)
    db.commit()

    # Incharge Assignments
    assign1 = WarehouseInchargeAssignment(
        incharge_id=incharge.id,
        warehouse_id=w1.id,
        is_active=True
    )
    assign2 = WarehouseInchargeAssignment(
        incharge_id=incharge.id,
        warehouse_id=w2.id,
        is_active=True
    )
    db.add_all([assign1, assign2])
    db.commit()

    # Incharge Activity Log
    act_log = WarehouseActivityLog(
        warehouse_id=w1.id,
        incharge_id=incharge.id,
        log_type="STOCK_INSPECTION",
        summary="Weekly Inward Physical Audit & Perimeter Inspection",
        detailed_notes="All 10,000 sq ft inspected. Forklift ramp clear. Pallet stacking checked in Bay 1 & 2. Inward gate pass log verified.",
        admin_reviewed=True,
        admin_feedback="Great work Suman. Ensure drainage gutter is cleared ahead of monsoon rains."
    )
    db.add(act_log)

    # Vehicles (2-Wheeler to Trailer)
    v0 = Vehicle(
        fleet_partner_id=fleet_partner.id,
        category=VehicleCategory.TWO_WHEELER,
        model_name="TVS NTORQ 125 Cargo Box",
        license_plate="Ba 92 Pa 5521",
        bluebook_number="BB-2W-KTM-2082-101",
        payload_capacity_kg=35.0,
        volume_capacity_cft=6.0,
        is_verified=True,
        is_available=True,
        current_lat=27.6950,
        current_lng=85.3200
    )
    v1 = Vehicle(
        fleet_partner_id=fleet_partner.id,
        category=VehicleCategory.MINI_TRUCK,
        model_name="Tata Ace Gold (0.75 Ton Batta)",
        license_plate="Ba 2 Kha 4491",
        bluebook_number="BB-KTM-2081-9982",
        payload_capacity_kg=750.0,
        volume_capacity_cft=140.0,
        is_verified=True,
        is_available=True,
        current_lat=27.6915,
        current_lng=85.3250
    )
    v2 = Vehicle(
        fleet_partner_id=fleet_partner.id,
        category=VehicleCategory.MEDIUM_PICKUP,
        model_name="Mahindra Bolero Maxi Truck (3 Ton)",
        license_plate="Pradesh 3-01-006 Kha 1205",
        bluebook_number="BB-LAL-2080-4512",
        payload_capacity_kg=3000.0,
        volume_capacity_cft=480.0,
        is_verified=True,
        is_available=True,
        current_lat=27.6850,
        current_lng=85.3400
    )
    v3 = Vehicle(
        fleet_partner_id=fleet_partner.id,
        category=VehicleCategory.SIX_WHEELER,
        model_name="Eicher Pro 3015 Heavy Truck (10 Ton)",
        license_plate="Na 4 Kha 7819",
        bluebook_number="BB-NAR-2079-8810",
        payload_capacity_kg=10000.0,
        volume_capacity_cft=1200.0,
        is_verified=True,
        is_available=True,
        current_lat=27.7000,
        current_lng=85.3100
    )
    v4 = Vehicle(
        fleet_partner_id=fleet_partner.id,
        category=VehicleCategory.CONTAINER_TRAILER,
        model_name="Tata Prima 40-Foot Container Carrier",
        license_plate="Na 6 Kha 9012",
        bluebook_number="BB-TRAILER-2078-009",
        payload_capacity_kg=32000.0,
        volume_capacity_cft=2600.0,
        is_verified=True,
        is_available=True,
        current_lat=27.0200,
        current_lng=84.8800
    )
    db.add_all([v0, v1, v2, v3, v4])
    db.commit()

    # Drivers
    d1 = Driver(
        fleet_partner_id=fleet_partner.id,
        assigned_vehicle_id=v1.id,
        full_name="Bikram Bahadur Gurung",
        phone_number="+977-9801122334",
        license_number="01-06-00445588",
        citizenship_no="27-01-72-01928"
    )
    d2 = Driver(
        fleet_partner_id=fleet_partner.id,
        assigned_vehicle_id=v2.id,
        full_name="Deepak Tamang",
        phone_number="+977-9815566778",
        license_number="01-08-00991122",
        citizenship_no="27-02-74-05512"
    )
    db.add_all([d1, d2])

    # Multi-Tier Inventory
    item1 = StockItem(
        client_id=client.id,
        warehouse_id=w1.id,
        sku_code="SKU-NEP-TEA-001",
        item_name="Ilam Orthodox Organic Black Tea",
        category="Agro Commodities",
        unit_type=InventoryUnitType.CARTOON,
        total_quantity=200
    )
    item2 = StockItem(
        client_id=client.id,
        warehouse_id=w1.id,
        sku_code="SKU-PALLET-SPICE-10",
        item_name="Standard Pallet of Himalayan Cardamom & Ginger",
        category="Export Spices",
        unit_type=InventoryUnitType.PALLET,
        total_quantity=15
    )
    item3 = StockItem(
        client_id=client.id,
        warehouse_id=w3.id,
        sku_code="SKU-CONT-40FT-IMP-88",
        item_name="40ft High-Cube Sealed Transit Container (Electronics & Solar)",
        category="Import Freight",
        unit_type=InventoryUnitType.CONTAINER,
        total_quantity=2
    )
    db.add_all([item1, item2, item3])
    db.commit()

    # Inventory Units
    u1 = InventoryUnit(
        stock_item_id=item1.id,
        unit_type=InventoryUnitType.CARTOON,
        serial_or_container_no="BOX-KTM-2083-0001",
        qr_code_hash="KWDC:CARTON:BOX-KTM-2083-0001:SKU-NEP-TEA-001:WT-20.5KG",
        gross_weight_kg=20.5,
        status="IN_STORAGE",
        bay_rack_location="Bay-1 / Rack-A3"
    )
    u2 = InventoryUnit(
        stock_item_id=item2.id,
        unit_type=InventoryUnitType.PALLET,
        serial_or_container_no="PLT-KTM-2083-0042",
        qr_code_hash="KWDC:PALLET:PLT-KTM-2083-0042:SKU-PALLET-SPICE-10:WT-450KG",
        gross_weight_kg=450.0,
        status="IN_STORAGE",
        bay_rack_location="Bay-2 / Floor-Pallet-08"
    )
    u3 = InventoryUnit(
        stock_item_id=item3.id,
        unit_type=InventoryUnitType.CONTAINER,
        serial_or_container_no="MSKU-9988112-40HC",
        qr_code_hash="KWDC:CONTAINER:MSKU-9988112-40HC:SEAL-902188:WT-22000KG",
        gross_weight_kg=22000.0,
        status="IN_STORAGE",
        bay_rack_location="DryPort-Yard-Sector-D"
    )
    db.add_all([u1, u2, u3])

    # Heavy Machinery
    eq1 = HeavyEquipment(
        owner_id=equip_owner.id,
        equipment_type="Electric Forklift (3 Ton)",
        model_name="Toyota 8FBE20 Counterbalance",
        capacity_ton=3.0,
        daily_rate_npr=8500.0,
        monthly_rate_npr=160000.0,
        location_city="Kathmandu"
    )
    eq2 = HeavyEquipment(
        owner_id=equip_owner.id,
        equipment_type="Mobile Hydraulic Crane (25 Ton)",
        model_name="ACE 25X Heavy Crane",
        capacity_ton=25.0,
        daily_rate_npr=35000.0,
        monthly_rate_npr=650000.0,
        location_city="Birgunj"
    )
    db.add_all([eq1, eq2])

    # Security
    sec_profile = SecurityAgency(
        user_id=sec_user.id,
        agency_name="Garuda Protection Services Pvt. Ltd.",
        home_ministry_license_no="MOHA-SEC-2078-041",
        emergency_contact_phone="+977-01-4433221",
        is_verified=True
    )
    db.add(sec_profile)
    db.commit()

    guard1 = GuardPersonnel(
        agency_id=sec_profile.id,
        guard_name="Prem Thapa Magar (Ex-Army)",
        phone_number="+977-9808899001",
        assigned_warehouse_id=w1.id,
        shift_type="NIGHT"
    )
    db.add(guard1)

    # Incidents
    inc1 = IncidentReport(
        warehouse_id=w1.id,
        guard_id=guard1.id,
        incharge_id=incharge.id,
        incident_category="RODENT_PEST_DAMAGE",
        severity=IncidentSeverity.MINOR,
        description="Minor rat gnawing detected on outer corrugated carton corner (SKU-NEP-TEA-001, Box #41). Internal sealed foil pouch intact.",
        action_taken="Carton moved to elevated metal rack. Ultrasonic pest repeller activated and rodent bait stations inspected.",
        police_alert_dispatched=False,
        admin_notified=True
    )
    inc2 = IncidentReport(
        warehouse_id=w1.id,
        guard_id=guard1.id,
        incharge_id=incharge.id,
        incident_category="WATER_SEEPAGE_MONSOON",
        severity=IncidentSeverity.MAJOR,
        description="Heavy monsoon downpour caused water seepage near North-East basement ventilator wall. Small water pool formed on floor.",
        action_taken="Immediate diversion barriers set. Tarpaulin covers secured over adjacent pallets. Owner notified for waterproofing maintenance hold.",
        police_alert_dispatched=False,
        admin_notified=True
    )
    db.add_all([inc1, inc2])

    # Booking & IRD Invoice
    booking1 = WarehouseRequest(
        client_id=client.id,
        warehouse_id=w1.id,
        requested_sqft=9200.0,
        allocated_billed_sqft=10000.0,
        monthly_base_rent=350000.0,
        kwdc_margin_amount=35000.0,
        vat_13_percent=50050.0,
        total_monthly_bill=435050.0,
        status=BookingStatus.ACTIVE_LEASED,
        lease_start_date=now - timedelta(days=10),
        lease_end_date=now + timedelta(days=80)
    )
    db.add(booking1)
    db.commit()

    inv = TaxInvoice(
        invoice_number="KWDC-2083-0001",
        storage_booking_id=booking1.id,
        buyer_name=client.full_name,
        buyer_pan_vat="605544332",
        taxable_base_amount=385000.0,
        kwdc_admin_margin=35000.0,
        vat_13_percent=50050.0,
        gross_total_npr=435050.0,
        qr_payload="IRD_NEPAL:VAT52:KWDC:INV-2083-0001:BUYER-605544332:TOTAL-435050.00:VAT-50050.00:HASH-8a4f9b2c",
        payment_status=PaymentStatus.PAID
    )
    db.add(inv)
    db.commit()
    print("ALL 30 TABLES CREATED AND SEEDED SUCCESSFULLY ON SUPABASE POSTGRESQL!")

if __name__ == "__main__":
    init_db()
