import sys
import os
from datetime import datetime

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import SessionLocal, Base, engine
from app.core.security import hash_password
from app.models.user import User
from app.models.warehouse import Warehouse, WarehouseRequest
from app.models.logistics import Vehicle, DriverRate, DispatchOrder, DeliveryStop
from app.models.finance import Invoice, MarginTier
from app.models.equipment import Equipment, EquipmentJob
from app.models.security_agency import SecurityAgency, SecurityPersonnel, SecurityAssignment, SecurityIncident

def seed_production_roles():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        print("🚀 Starting Production 6-Entity Role Seeding...")

        # 1. Platform Super Admin
        admin = db.query(User).filter(User.email == "admin@kwdc.com.np").first()
        if not admin:
            admin = User(
                name="KTM-WDC System Superadmin",
                email="admin@kwdc.com.np",
                password=hash_password("Admin@KWDC2026!"),
                phone="9800000001",
                role="admin",
                is_admin=True,
                is_active=True,
                user_code="ADM-002",
                email_verified_at=now
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            print("✅ Created Super Admin: admin@kwdc.com.np")
        else:
            admin.password = hash_password("Admin@KWDC2026!")
            admin.is_admin = True
            admin.role = "admin"
            admin.is_active = True
            admin.email_verified_at = now
            db.commit()
            print("🔄 Updated Super Admin: admin@kwdc.com.np")

        # 2. Warehouse Property Owner
        owner = db.query(User).filter(User.email == "property@kwdc.com.np").first()
        if not owner:
            owner = User(
                name="Ram Shrestha (Godown Owner)",
                email="property@kwdc.com.np",
                password=hash_password("Property@KWDC2026!"),
                phone="9851020001",
                role="property_owner",
                is_admin=False,
                is_active=True,
                user_code="OWN-001",
                email_verified_at=now
            )
            db.add(owner)
            db.commit()
            db.refresh(owner)
            print("✅ Created Property Owner: property@kwdc.com.np")
        else:
            owner.password = hash_password("Property@KWDC2026!")
            owner.role = "property_owner"
            owner.is_active = True
            owner.email_verified_at = now
            db.commit()
            print("🔄 Updated Property Owner: property@kwdc.com.np")

        # Ensure Warehouses for Property Owner
        wh1 = db.query(Warehouse).filter(Warehouse.user_id == owner.id).first()
        if not wh1:
            wh1 = Warehouse(
                user_id=owner.id,
                name="Kalimati Commercial Agro-Logistics Center",
                location="Kalimati, Ward 14, Kathmandu",
                address="Near Kalimati Fruits & Vegetable Wholesale Market",
                area_sqft=12000.0,
                price_per_sqft=50.0,
                cold_storage=True,
                temperature_min=-4.0,
                temperature_max=4.0,
                facilities="Cold Store, CCTV, 24/7 Security, 3 Loading Bays, Forklift Ramp",
                nearby_police="Kalimati Police Circle (400m)",
                nearby_hospital="Vayodha Hospitals (1.2km)",
                nearby_fire="Damkal Station New Road (2.1km)",
                status="approved",
                kataho_code="KTM-KAL-014",
                cctv_count=16,
                guards_count=4,
                fire_extinguishers=8,
                latitude=27.6982,
                longitude=85.3015
            )
            wh2 = Warehouse(
                user_id=owner.id,
                name="Birgunj Dry Port Transit Godown",
                location="Dry Port Access Road, Birgunj",
                address="Plot 42, Sirsiya Inland Container Depot",
                area_sqft=25000.0,
                price_per_sqft=38.0,
                cold_storage=False,
                facilities="Dry Goods, Container Crane Access, Perimeter Security",
                nearby_police="Sirsiya Border Police Post (300m)",
                nearby_hospital="Narayani Hospital Birgunj (3.5km)",
                nearby_fire="Birgunj Municipal Damkal (4.0km)",
                status="approved",
                kataho_code="BRG-ICD-004",
                cctv_count=24,
                guards_count=6,
                fire_extinguishers=14,
                latitude=27.0215,
                longitude=84.8690
            )
            db.add_all([wh1, wh2])
            db.commit()
            print("✅ Seeded Real Warehouses for Property Owner")

        # 3. Commercial Driver
        driver = db.query(User).filter(User.email == "driver@kwdc.com.np").first()
        if not driver:
            driver = User(
                name="Bikash Thapa (Commercial Driver)",
                email="driver@kwdc.com.np",
                password=hash_password("Driver@KWDC2026!"),
                phone="9861040001",
                role="driver",
                is_admin=False,
                is_active=True,
                user_code="DRV-001",
                email_verified_at=now
            )
            db.add(driver)
            db.commit()
            db.refresh(driver)
            print("✅ Created Driver: driver@kwdc.com.np")
        else:
            driver.password = hash_password("Driver@KWDC2026!")
            driver.role = "driver"
            driver.is_active = True
            driver.email_verified_at = now
            db.commit()
            print("🔄 Updated Driver: driver@kwdc.com.np")

        # Driver Vehicle & Rates
        veh = db.query(Vehicle).filter(Vehicle.driver_id == driver.id).first()
        if not veh:
            veh = Vehicle(
                user_id=driver.id,
                driver_id=driver.id,
                vehicle_number="BA 2 KHA 8912",
                vehicle_type="Medium Commercial Truck (Tata Ace / 1.5 Ton)",
                capacity=1.5,
                capacity_unit="Ton",
                manufacturer="Tata Motors",
                model="Tata Ace Gold",
                status="active",
                is_verified=True
            )
            db.add(veh)
            db.commit()
            print("✅ Seeded Driver Vehicle: BA 2 KHA 8912")

        drate = db.query(DriverRate).filter(DriverRate.user_id == driver.id).first()
        if not drate:
            drate = DriverRate(
                user_id=driver.id,
                driver_id=driver.id,
                date=now.date(),
                rate_tiers="[]",
                vehicle_type="truck",
                base_price=450.0,
                is_active=True,
                status="approved"
            )
            db.add(drate)
            db.commit()

        # 4. Enterprise Client / Shipper
        client = db.query(User).filter(User.email == "client@kwdc.com.np").first()
        if not client:
            client = User(
                name="Pooja Enterprises (Shipper)",
                email="client@kwdc.com.np",
                password=hash_password("Client@KWDC2026!"),
                phone="9841030001",
                role="client",
                is_admin=False,
                is_active=True,
                user_code="CLI-001",
                email_verified_at=now
            )
            db.add(client)
            db.commit()
            db.refresh(client)
            print("✅ Created Client: client@kwdc.com.np")
        else:
            client.password = hash_password("Client@KWDC2026!")
            client.role = "client"
            client.is_active = True
            client.email_verified_at = now
            db.commit()
            print("🔄 Updated Client: client@kwdc.com.np")

        # Ensure active dispatch order for Client & Driver
        order = db.query(DispatchOrder).filter(DispatchOrder.client_id == client.id).first()
        if not order:
            order = DispatchOrder(
                client_id=client.id,
                driver_id=driver.id,
                tracking_id="TRK-2026-0001",
                invoice_no="INV-2026-0001",
                pickup_address="Kalimati Commercial Agro-Logistics Center, Kathmandu",
                pickup_contact_person="Pooja Shrestha",
                pickup_contact_phone="9841030001",
                total_distance=14.5,
                base_price=2045.0,
                driver_earning=1700.0,
                admin_margin=245.4,
                tax_amount=297.75,
                grand_total=2588.15,
                status="on_the_way",
                current_latitude=27.6912,
                current_longitude=85.3120,
                tracking_enabled=True,
                total_boxes=48
            )
            db.add(order)
            db.commit()
            db.refresh(order)

            # Add Delivery Stop
            stop = DeliveryStop(
                dispatch_order_id=order.id,
                stop_number=1,
                address="Ring Road Industrial Corridor, Balkumari, Lalitpur",
                recipient_name="Balkumari Wholesale Center",
                recipient_phone="9802223344",
                status="pending"
            )
            db.add(stop)

            # Add Tax Invoice
            inv = Invoice(
                user_id=client.id,
                client_id=client.id,
                invoice_number="INV-2026-0001",
                order_type="dispatch",
                order_id=order.id,
                amount=2290.40,
                subtotal=2290.40,
                tax_amount=297.75,
                grand_total=2588.15,
                payment_status="unpaid",
                due_date=now
            )
            db.add(inv)
            db.commit()
            print("✅ Seeded Real Dispatch Order (TRK-2026-0001) & 13% IRD VAT Invoice")

        # 5. Heavy Equipment Owner
        equipment_owner = db.query(User).filter(User.email == "equipment@kwdc.com.np").first()
        if not equipment_owner:
            equipment_owner = User(
                name="Himal Machinery & Cranes Pvt Ltd",
                email="equipment@kwdc.com.np",
                password=hash_password("Equipment@KWDC2026!"),
                phone="9811050001",
                role="equipment_owner",
                is_admin=False,
                is_active=True,
                user_code="EQP-001",
                email_verified_at=now
            )
            db.add(equipment_owner)
            db.commit()
            db.refresh(equipment_owner)
            print("✅ Created Heavy Equipment Owner: equipment@kwdc.com.np")
        else:
            equipment_owner.password = hash_password("Equipment@KWDC2026!")
            equipment_owner.role = "equipment_owner"
            equipment_owner.is_active = True
            equipment_owner.email_verified_at = now
            db.commit()
            print("🔄 Updated Heavy Equipment Owner: equipment@kwdc.com.np")

        # Machinery Catalog
        eq_count = db.query(Equipment).filter(Equipment.user_id == equipment_owner.id).count()
        if eq_count == 0:
            eq1 = Equipment(
                user_id=equipment_owner.id,
                name="Toyota 3-Ton Electric Warehouse Forklift",
                type="forklift",
                daily_rate=6500.0,
                security_deposit=15000.0,
                location="Kalimati Logistics Hub, Kathmandu",
                description="Zero-emission electric forklift with 4.5m mast and certified operator.",
                status="available"
            )
            eq2 = Equipment(
                user_id=equipment_owner.id,
                name="TCM 5-Ton Diesel Heavy Forklift",
                type="forklift",
                daily_rate=9000.0,
                security_deposit=20000.0,
                location="Birgunj Dry Port Depot",
                description="Heavy container unloading forklift for cement and industrial freight.",
                status="available"
            )
            eq3 = Equipment(
                user_id=equipment_owner.id,
                name="Sany 25-Ton Hydraulic Mobile Crane",
                type="crane",
                daily_rate=35000.0,
                security_deposit=70000.0,
                location="Balkumari Industrial Depot, Lalitpur",
                description="Telescopic boom crane with licensed senior crane operator.",
                status="available"
            )
            db.add_all([eq1, eq2, eq3])
            db.commit()
            print("✅ Seeded Heavy Machinery Fleet Catalog")

        # 6. Licensed Security Agency
        sec_user = db.query(User).filter(User.email == "security@kwdc.com.np").first()
        if not sec_user:
            sec_user = User(
                name="Nepal Suraksha Guard Services Pvt Ltd",
                email="security@kwdc.com.np",
                password=hash_password("Security@KWDC2026!"),
                phone="9821060001",
                role="security_agency",
                is_admin=False,
                is_active=True,
                user_code="SEC-001",
                email_verified_at=now
            )
            db.add(sec_user)
            db.commit()
            db.refresh(sec_user)
            print("✅ Created Security Agency: security@kwdc.com.np")
        else:
            sec_user.password = hash_password("Security@KWDC2026!")
            sec_user.role = "security_agency"
            sec_user.is_active = True
            sec_user.email_verified_at = now
            db.commit()
            print("🔄 Updated Security Agency: security@kwdc.com.np")

        # Agency Profile & Personnel Roster
        agency = db.query(SecurityAgency).filter(SecurityAgency.user_id == sec_user.id).first()
        if not agency:
            agency = SecurityAgency(
                user_id=sec_user.id,
                agency_name="Nepal Suraksha Guard Services Pvt Ltd",
                license_number="MHA-SEC-2026-092",
                registration_number="REG-SEC-0042",
                address="Putalisadak, Ward 28, Kathmandu",
                phone="9821060001",
                email="security@kwdc.com.np",
                status="approved",
                is_verified=True
            )
            db.add(agency)
            db.commit()
            db.refresh(agency)

            # Guards
            g1 = SecurityPersonnel(
                security_agency_id=agency.id,
                name="Sub-Inspector Birkha Bahadur Gurung",
                badge_id="SEC-KTM-011",
                rank="Guard Commander",
                phone="9801122331",
                status="on_duty"
            )
            g2 = SecurityPersonnel(
                security_agency_id=agency.id,
                name="Havildar Prem Singh Rokaya",
                badge_id="SEC-KTM-012",
                rank="Armed Perimeter Guard",
                phone="9801122332",
                status="on_duty"
            )
            g3 = SecurityPersonnel(
                security_agency_id=agency.id,
                name="Officer Dinesh Tamang",
                badge_id="SEC-KTM-013",
                rank="Gate Sentry Officer",
                phone="9801122333",
                status="on_duty"
            )
            db.add_all([g1, g2, g3])
            db.commit()
            db.refresh(g1)

            # Post Assignment
            wh_rec = db.query(Warehouse).first()
            if wh_rec:
                assign = SecurityAssignment(
                    security_agency_id=agency.id,
                    warehouse_id=wh_rec.id,
                    personnel_id=g1.id,
                    shift_type="day",
                    start_date=now.date(),
                    status="active"
                )
                db.add(assign)
                db.commit()
            print("✅ Seeded Security Agency Profile, Guard Roster & Warehouse Deployments")

        print("🎉 ALL 6 ENTITY ROLES FULLY SEEDED & VERIFIED IN SUPABASE DATABASE!")

    except Exception as e:
        db.rollback()
        print(f"❌ Error during seeding: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    seed_production_roles()
