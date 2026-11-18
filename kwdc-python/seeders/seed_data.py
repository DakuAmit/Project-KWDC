import os
import json
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, Base, engine
from app.core.security import hash_password
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.logistics import Vehicle, DriverRate, DispatchOrder, DeliveryStop
from app.models.equipment import Equipment
from app.models.security_agency import SecurityAgency, SecurityPersonnel, SecurityAssignment
from app.models.finance import MarginTier, Invoice
from app.services.qr_service import QRService

def seed_database():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    print("🚀 Initializing KTM-WDC Database & Demo Dataset...")
    master_password = hash_password(settings.KWDC_DEMO_PASSWORD)

    # 1. CREATE ALL 6 DEMO ACCOUNTS
    users_data = [
        {
            "email": "admin.access@kwdc.test",
            "name": "Super Admin User",
            "role": "admin",
            "phone": "9800000000",
            "is_admin": True,
            "user_code": "ADM-DEMO"
        },
        {
            "email": "client.access@kwdc.test",
            "name": "Sita Enterprises Demo",
            "role": "client",
            "phone": "9801112233",
            "user_code": "CLI-DEMO"
        },
        {
            "email": "driver.access@kwdc.test",
            "name": "Ram Bahadur Driver",
            "role": "driver",
            "phone": "9802223344",
            "is_driver": True,
            "user_code": "DRV-DEMO"
        },
        {
            "email": "property.access@kwdc.test",
            "name": "Maya Warehouse Owner",
            "role": "property_owner",
            "phone": "9803334455",
            "is_property_owner": True,
            "user_code": "PRO-DEMO"
        },
        {
            "email": "equipment.access@kwdc.test",
            "name": "Krishna Equipment Owner",
            "role": "equipment_owner",
            "phone": "9804445566",
            "is_equipment_owner": True,
            "user_code": "EQP-DEMO"
        },
        {
            "email": "security.access@kwdc.test",
            "name": "Nepal Suraksha Agency",
            "role": "security_agency",
            "phone": "9805556677",
            "user_code": "SEC-DEMO"
        }
    ]

    user_map = {}
    for u in users_data:
        existing = db.query(User).filter(User.email == u["email"]).first()
        if not existing:
            new_u = User(
                name=u["name"],
                email=u["email"],
                password=master_password,
                phone=u["phone"],
                role=u["role"],
                is_active=True,
                is_admin=u.get("is_admin", False),
                is_driver=u.get("is_driver", False),
                is_property_owner=u.get("is_property_owner", False),
                is_equipment_owner=u.get("is_equipment_owner", False),
                user_code=u["user_code"],
                email_verified_at=datetime.utcnow()
            )
            db.add(new_u)
            db.commit()
            db.refresh(new_u)
            user_map[u["role"]] = new_u
            print(f"✅ Created User: {u['email']} [{u['role']}]")
        else:
            user_map[u["role"]] = existing

    # 2. SEED MARGIN TIERS
    if db.query(MarginTier).count() == 0:
        tiers = [
            MarginTier(name="Short Distance (0-10km)", min_distance=0, max_distance=10, service_type="dispatch", margin_type="percentage", margin_value=10.0, is_active=True),
            MarginTier(name="Medium Distance (11-50km)", min_distance=10, max_distance=50, service_type="dispatch", margin_type="percentage", margin_value=12.0, is_active=True),
            MarginTier(name="Long Distance (51km+)", min_distance=50, max_distance=None, service_type="dispatch", margin_type="percentage", margin_value=15.0, is_active=True),
        ]
        db.add_all(tiers)
        db.commit()
        print("✅ Seeded Margin Tiers (10%, 12%, 15%)")

    # 3. SEED WAREHOUSES
    prop_owner = user_map.get("property_owner")
    if prop_owner and db.query(Warehouse).count() == 0:
        wh1 = Warehouse(
            user_id=prop_owner.id,
            name="Kalimati Cold Store Demo",
            location="Kalimati, Kathmandu",
            address="Kalimati Tarkari Bazaar gate pachadi, Kathmandu",
            latitude=27.6823,
            longitude=85.3038,
            contact_number=prop_owner.phone,
            email="kalimati.cold@kwdc.test",
            area_sqft=6200,
            area_sqm=576.0,
            price_per_sqft=52.0,
            description="Cold storage for vegetable, dairy, and pharmaceutical cargo with 24/7 guard service.",
            cold_storage=True,
            temperature_min=-4.0,
            temperature_max=6.0,
            cctv_count=18,
            guards_count=4,
            status="approved",
            kataho_code="KTM-KLM-01"
        )
        wh2 = Warehouse(
            user_id=prop_owner.id,
            name="Birgunj Transit Godown Demo",
            location="Birgunj, Parsa",
            address="Dry Port road, Birgunj",
            latitude=27.0125,
            longitude=84.8765,
            contact_number=prop_owner.phone,
            email="birgunj.transit@kwdc.test",
            area_sqft=14000,
            area_sqm=1300.0,
            price_per_sqft=38.0,
            description="Large border transit warehouse for FMCG, cement, and container imports.",
            cold_storage=False,
            cctv_count=24,
            guards_count=6,
            status="approved",
            kataho_code="BRG-DRY-01"
        )
        wh3 = Warehouse(
            user_id=prop_owner.id,
            name="Balkumari Warehouse Lalitpur",
            location="Balkumari, Lalitpur",
            address="Ring Road corridor, Balkumari",
            latitude=27.6753,
            longitude=85.3230,
            contact_number=prop_owner.phone,
            email="balkumari.storage@kwdc.test",
            area_sqft=8000,
            area_sqm=743.0,
            price_per_sqft=45.0,
            description="Spacious warehouse with direct highway transit docks.",
            cold_storage=False,
            cctv_count=12,
            guards_count=3,
            status="approved",
            kataho_code="KTM-BKM-02"
        )
        db.add_all([wh1, wh2, wh3])
        db.commit()
        print("✅ Seeded Warehouses (Kalimati, Birgunj, Balkumari)")

    # 4. SEED VEHICLES & DRIVER RATES
    driver_u = user_map.get("driver")
    if driver_u and db.query(Vehicle).count() == 0:
        v1 = Vehicle(
            user_id=driver_u.id,
            driver_id=driver_u.id,
            driver_code="DRV-001",
            vehicle_number="BA 1 KA 1234",
            vehicle_type="truck",
            capacity=1.5,
            capacity_unit="tons",
            manufacturer="Tata",
            model="Ace",
            year=2021,
            color="White",
            fuel_type="diesel",
            status="active",
            is_verified=True
        )
        db.add(v1)

        rate = DriverRate(
            user_id=driver_u.id,
            driver_id=driver_u.id,
            date=date.today(),
            base_price=650.0,
            vehicle_type="truck",
            status="active",
            is_active=True
        )
        db.add(rate)
        db.commit()
        print("✅ Seeded Vehicles and Driver Rates")

    # 5. SEED HEAVY EQUIPMENT
    equip_owner = user_map.get("equipment_owner")
    if equip_owner and db.query(Equipment).count() == 0:
        eq1 = Equipment(
            user_id=equip_owner.id,
            owner_id=equip_owner.id,
            name="Toyota 5-Ton Diesel Forklift",
            type="forklift",
            model="8FD50N",
            year=2022,
            daily_rate=8500.0,
            security_deposit=15000.0,
            location="Kalimati, Kathmandu",
            status="available",
            description="Heavy forklift with certified operator for palletized warehouse loading."
        )
        eq2 = Equipment(
            user_id=equip_owner.id,
            owner_id=equip_owner.id,
            name="Hino 20-Ton Mobile Hydraulic Crane",
            type="crane",
            model="Ranger 500",
            year=2020,
            daily_rate=28000.0,
            security_deposit=50000.0,
            location="Birgunj Dry Port",
            status="available",
            description="Telescopic crane for heavy container and industrial plant unloading."
        )
        db.add_all([eq1, eq2])
        db.commit()
        print("✅ Seeded Heavy Machinery Fleet")

    # 6. SEED SECURITY AGENCY
    sec_u = user_map.get("security_agency")
    wh_obj = db.query(Warehouse).first()
    if sec_u and db.query(SecurityAgency).count() == 0:
        sec_agency = SecurityAgency(
            user_id=sec_u.id,
            agency_name="Nepal Suraksha Agency Pvt Ltd",
            registration_number="SEC-2026-NP",
            license_number="MHA-SEC-092",
            address="Baluwatar, Kathmandu, Nepal",
            phone="9805556677",
            status="approved",
            is_verified=True
        )
        db.add(sec_agency)
        db.commit()
        db.refresh(sec_agency)

        guard = SecurityPersonnel(
            security_agency_id=sec_agency.id,
            name="Ram Bahadur Guard",
            phone="9811223344",
            citizenship_no="27-01-72-00123",
            rank="Senior Guard",
            status="assigned"
        )
        db.add(guard)
        db.commit()
        db.refresh(guard)

        if wh_obj:
            asgn = SecurityAssignment(
                security_agency_id=sec_agency.id,
                warehouse_id=wh_obj.id,
                personnel_id=guard.id,
                shift_type="day",
                start_date=date.today(),
                status="active"
            )
            db.add(asgn)
            db.commit()
        print("✅ Seeded Licensed Security Agency & Guard Posts")

    # 7. SEED SAMPLE DISPATCH & INVOICE
    client_u = user_map.get("client")
    if client_u and db.query(DispatchOrder).count() == 0:
        order = DispatchOrder(
            client_id=client_u.id,
            driver_id=driver_u.id if driver_u else None,
            tracking_id="TRK-KWDC-9812",
            invoice_no="INV-2026-0012",
            pickup_address="Kalimati Cold Store, Ward 14, Kathmandu",
            pickup_contact_person="Sita Thapa",
            pickup_contact_phone="9801112233",
            total_distance=18.5,
            base_price=2037.50,
            driver_earning=2037.50,
            admin_margin=244.50,
            tax_amount=296.66,
            grand_total=2578.66,
            bill_type="regular",
            pan_number="601234567",
            status="on_the_way",
            tracking_enabled=True
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        stop = DeliveryStop(
            dispatch_order_id=order.id,
            stop_number=1,
            address="Ring Road Junction, Balkumari, Lalitpur",
            recipient_name="Balkumari Wholesale Depot",
            recipient_phone="9802223344",
            distance_price=2037.50,
            status="pending"
        )
        db.add(stop)
        db.commit()

        # Seed Invoice
        qr_data = QRService.generate_qr_base64("https://kwdc.gov.np/verify/INV-2026-0012")
        inv = Invoice(
            user_id=client_u.id,
            client_id=client_u.id,
            invoice_number="INV-2026-0012",
            order_type="dispatch",
            order_id=order.id,
            amount=2578.66,
            subtotal=2282.00,
            tax_rate=13.00,
            tax_amount=296.66,
            grand_total=2578.66,
            pan_number="601234567",
            status="pending",
            payment_status="unpaid",
            due_date=date.today() + timedelta(days=7),
            qr_code=qr_data
        )
        db.add(inv)
        db.commit()
        print("✅ Seeded Sample Dispatch #TRK-KWDC-9812 & 13% VAT Tax Invoice #INV-2026-0012")

    db.close()
    print("==================================================")
    print("✨ KTM-WDC Database Seeding Complete!")
    print("🔑 Demo Login: admin.access@kwdc.test (Password: KwdcNew2026!)")
    print("==================================================")

if __name__ == "__main__":
    seed_database()
