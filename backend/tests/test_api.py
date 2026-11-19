import os
import sys
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

# Ensure root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from seeders.seed_data import seed_database
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.finance import Invoice
from app.services.invoice_service import InvoiceService

client = TestClient(app)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    from app.core.database import Base, engine
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed_database()

def test_ping():
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.text == "pong"

def test_welcome_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "Kathmandu Warehousing" in response.text

def test_real_user_registration_and_email_dispatch():
    response = client.post("/api/auth/register", json={
        "name": "Himalayan Cargo Logistics",
        "email": "contact@himalayancargo.np",
        "password": "SecurePassword2026!",
        "phone": "9801122334",
        "role": "client",
        "address": "Birgunj Dry Port, Parsa"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending_verification"
    assert data["email"] == "contact@himalayancargo.np"
    assert data["requires_verification"] is True

def test_login_blocked_before_verification():
    # Attempting to sign in before email verification must return 403
    response = client.post("/api/auth/login", json={
        "email": "contact@himalayancargo.np",
        "password": "SecurePassword2026!"
    })
    assert response.status_code == 403
    assert "not been verified" in response.json()["detail"]

def test_email_verification_flow():
    db = SessionLocal()
    user = db.query(User).filter(User.email == "contact@himalayancargo.np").first()
    code = user.email_verification_token
    db.close()

    assert code is not None
    assert len(code) == 6  # 6-digit numeric OTP

    # Test 6-digit code verification endpoint
    response = client.post("/api/auth/verify-code", json={
        "email": "contact@himalayancargo.np",
        "code": code
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "verified"
    assert "access_token" in data
    assert data["user"]["email"] == "contact@himalayancargo.np"

def test_real_user_login():
    response = client.post("/api/auth/login", json={
        "email": "contact@himalayancargo.np",
        "password": "SecurePassword2026!"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == "client"

def test_forgot_and_reset_password_flow():
    # 1. Request password reset
    forgot_res = client.post("/api/auth/forgot-password", json={
        "email": "contact@himalayancargo.np"
    })
    assert forgot_res.status_code == 200

    db = SessionLocal()
    user = db.query(User).filter(User.email == "contact@himalayancargo.np").first()
    reset_token = user.reset_password_token
    db.close()

    assert reset_token is not None

    # 2. Reset password
    reset_res = client.post("/api/auth/reset-password", json={
        "token": reset_token,
        "new_password": "BrandNewPassword2026!"
    })
    assert reset_res.status_code == 200

    # 3. Verify new password login succeeds
    login_res = client.post("/api/auth/login", json={
        "email": "contact@himalayancargo.np",
        "password": "BrandNewPassword2026!"
    })
    assert login_res.status_code == 200

def test_pricing_calculator_with_13_percent_vat():
    response = client.post("/dispatch/calculate-price", json={
        "distance": 25.0,
        "vehicle_type": "truck",
        "stops_count": 1
    })
    assert response.status_code == 200
    data = response.json()
    assert data["distance"] == 25.0
    assert data["base_price"] > 0
    assert data["admin_margin_percentage"] == 12.0  # Medium distance tier
    assert data["vat_13_percent"] == round(data["subtotal"] * 0.13, 2)
    assert data["grand_total"] == round(data["subtotal"] + data["vat_13_percent"], 2)

def test_warehouses_and_pdf_tax_invoice():
    db = SessionLocal()
    user = db.query(User).first()
    wh = Warehouse(
        user_id=user.id,
        name="Pokhara Valley Cold Store",
        location="Pokhara, Kaski",
        address="Nayabazar, Pokhara",
        area_sqft=5000,
        price_per_sqft=45.0,
        status="approved"
    )
    db.add(wh)
    
    inv = Invoice(
        user_id=user.id,
        invoice_number="INV-TEST-2026",
        amount=1000.0,
        subtotal=1000.0,
        tax_rate=13.0,
        tax_amount=130.0,
        grand_total=1130.0,
        status="pending",
        pan_number="600123456",
        due_date=date.today() + timedelta(days=7)
    )
    db.add(inv)
    db.commit()

    pdf_bytes = InvoiceService.generate_pdf_bytes(inv)
    db.close()

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500

def test_ai_dispatch_advisor():
    response = client.post("/ai/dispatch-advisor", json={
        "pickup_address": "Kalimati Fruit Market",
        "destination_address": "Pokhara Wholesale Hub",
        "estimated_weight_kg": 500.0,
        "cargo_type": "Fresh Apples"
    })
    assert response.status_code == 200
    data = response.json()
    assert "estimated_km" in data
    assert "recommended_vehicle" in data

def test_warehouse_and_invoice_api_production_flow():
    # 1. Login as user to get auth token
    login_resp = client.post("/api/auth/login", json={
        "email": "contact@himalayancargo.np",
        "password": "BrandNewPassword2026!"
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. List a new real commercial warehouse
    wh_resp = client.post("/api/warehouses", json={
        "name": "Bhairahawa Special Economic Zone Cold Hub",
        "location": "Bhairahawa, Rupandehi",
        "address": "SEZ Industrial Area, Plot 4",
        "kataho_code": "BHA-SEZ-04",
        "area_sqft": 15000.0,
        "price_per_sqft": 40.0,
        "cold_storage": True,
        "temperature_min": -2.0,
        "temperature_max": 6.0,
        "description": "Multi-chamber cold facility for pharmaceuticals and perishable agriculture."
    }, headers=headers)
    assert wh_resp.status_code == 200
    wh_data = wh_resp.json()
    assert wh_data["status"] == "success"
    wh_id = wh_data["warehouse"]["id"]

    # 3. Fetch warehouses list via GET /api/warehouses
    list_resp = client.get("/api/warehouses")
    assert list_resp.status_code == 200
    warehouses = list_resp.json()
    assert any(w["id"] == wh_id for w in warehouses)

    # 4. Reserve storage space (500 sqft)
    res_resp = client.post(f"/api/warehouses/{wh_id}/reserve", json={
        "space_required": 500.0,
        "purpose": "Cold fruit transit storage"
    }, headers=headers)
    assert res_resp.status_code == 200
    res_data = res_resp.json()
    assert res_data["status"] == "success"
    inv = res_data["invoice"]
    assert inv["subtotal"] == 20000.0  # 500 sqft * 40 Rs/sqft
    assert inv["vat_amount"] == 2600.0  # 13% VAT
    assert inv["grand_total"] == 22600.0
    inv_id = inv["id"]

    # 5. Fetch real invoices via GET /api/invoices
    inv_list_resp = client.get("/api/invoices", headers=headers)
    assert inv_list_resp.status_code == 200
    invoices = inv_list_resp.json()
    assert any(i["id"] == inv_id for i in invoices)

    # 6. Settle invoice via POST /api/invoices/{id}/pay (eSewa)
    pay_resp = client.post(f"/api/invoices/{inv_id}/pay", json={
        "payment_method": "esewa",
        "reference_id": "ESEWA-TEST-998877"
    }, headers=headers)
    assert pay_resp.status_code == 200
    pay_data = pay_resp.json()
    assert pay_data["status"] == "success"
    assert pay_data["invoice"]["payment_status"] == "paid"

    # 7. Check Dashboard Stats reflects real live figures
    stats_resp = client.get("/api/dashboard/stats", headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert "stats" in stats
    assert stats["stats"]["storage_sqft"] == 500.0
    assert stats["stats"]["unpaid_invoices_amount"] == 0.0
    assert len(stats["stats"]["invoices"]) >= 1

    # 8. Check PDF Tax Invoice download via GET /api/invoices/{inv_id}/download
    pdf_resp = client.get(f"/api/invoices/{inv_id}/download")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF")

def test_admin_console_drawers_api():
    # 1. Non-admin client token should get 403
    client_login = client.post("/api/auth/login", json={
        "email": "contact@himalayancargo.np",
        "password": "BrandNewPassword2026!"
    })
    client_token = client_login.json()["access_token"]
    forbidden_resp = client.get("/api/admin/overview", headers={"Authorization": f"Bearer {client_token}"})
    assert forbidden_resp.status_code == 403

    # 2. SuperAdmin login
    admin_login = client.post("/api/auth/login", json={
        "email": "app.netpack@gmail.com",
        "password": "Admin@2026"
    })
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Drawer 1: Overview
    ov_resp = client.get("/api/admin/overview", headers=admin_headers)
    assert ov_resp.status_code == 200
    ov_data = ov_resp.json()
    assert ov_data["status"] == "healthy"
    assert "counts" in ov_data
    assert "financials" in ov_data

    # Drawer 2: Users & KYC
    users_resp = client.get("/api/admin/users", headers=admin_headers)
    assert users_resp.status_code == 200
    users_list = users_resp.json()
    assert len(users_list) >= 2
    target_user = users_list[0]
    # Toggle status
    status_resp = client.post(f"/api/admin/users/{target_user['id']}/status", json={"is_active": True}, headers=admin_headers)
    assert status_resp.status_code == 200
    # Toggle verification
    verify_resp = client.post(f"/api/admin/users/{target_user['id']}/verify", json={"is_verified": True}, headers=admin_headers)
    assert verify_resp.status_code == 200

    # Drawer 3: Warehouses
    wh_resp = client.get("/api/admin/warehouses", headers=admin_headers)
    assert wh_resp.status_code == 200
    wh_list = wh_resp.json()
    assert len(wh_list) >= 1
    wh_id = wh_list[0]["id"]
    wh_status_resp = client.post(f"/api/admin/warehouses/{wh_id}/status", json={"status": "approved"}, headers=admin_headers)
    assert wh_status_resp.status_code == 200

    # Drawer 4: Dispatches
    disp_resp = client.get("/api/admin/dispatches", headers=admin_headers)
    assert disp_resp.status_code == 200

    # Drawer 5: Telemetry
    tele_resp = client.get("/api/admin/telemetry", headers=admin_headers)
    assert tele_resp.status_code == 200

    # Drawer 6: Inventory
    inv_resp = client.get("/api/admin/inventory", headers=admin_headers)
    assert inv_resp.status_code == 200

    # Drawer 7: Equipment
    eq_resp = client.get("/api/admin/equipment", headers=admin_headers)
    assert eq_resp.status_code == 200

    # Drawer 8: Security
    sec_resp = client.get("/api/admin/security", headers=admin_headers)
    assert sec_resp.status_code == 200

    # Drawer 9: Invoices
    inv_mgmt_resp = client.get("/api/admin/invoices", headers=admin_headers)
    assert inv_mgmt_resp.status_code == 200
    inv_mgmt_data = inv_mgmt_resp.json()
    assert "summary" in inv_mgmt_data
    assert "invoices" in inv_mgmt_data

    # Drawer 10: Settings & Margins
    settings_resp = client.get("/api/admin/settings", headers=admin_headers)
    assert settings_resp.status_code == 200
    # Create new margin tier
    tier_add_resp = client.post("/api/admin/settings/margin-tiers", json={
        "name": "Express Mountain Corridor",
        "min_distance": 100.0,
        "max_distance": 350.0,
        "margin_value": 18.0,
        "service_type": "dispatch",
        "margin_type": "percentage",
        "is_active": True
    }, headers=admin_headers)
    assert tier_add_resp.status_code == 200
    tier_id = tier_add_resp.json()["tier_id"]
    # Deactivate tier
    tier_del_resp = client.delete(f"/api/admin/settings/margin-tiers/{tier_id}", headers=admin_headers)
    assert tier_del_resp.status_code == 200

def test_property_owner_multi_tenant_and_facility_governance():
    # 1. Register Property Owner User
    po_email = "owner@birgunjlogistics.com"
    reg_resp = client.post("/api/auth/register", json={
        "name": "Birgunj Logistics Real Estate",
        "email": po_email,
        "password": "SecurePassword2026!",
        "phone": "9841998877",
        "role": "property_owner",
        "address": "Dry Port Road, Parsa"
    })
    assert reg_resp.status_code == 200

    # Verify Email
    db = SessionLocal()
    po_user = db.query(User).filter(User.email == po_email).first()
    code = po_user.email_verification_token
    db.close()

    verify_resp = client.post("/api/auth/verify-code", json={"email": po_email, "code": code})
    assert verify_resp.status_code == 200
    po_token = verify_resp.json()["access_token"]
    po_headers = {"Authorization": f"Bearer {po_token}"}

    # 2. List New Commercial Warehouse with All Advanced Facilities
    create_wh_resp = client.post("/api/warehouses", json={
        "name": "Birgunj Integrated Cold & Dry Godown",
        "location": "Birgunj Dry Port, Parsa",
        "address": "Corridor 4, Ward 22",
        "kataho_code": "BRG-DRY-99",
        "facilities": "Closed Covered Godown • 40ft Heavy Container Highway Access",
        "area_sqft": 10000.0,
        "price_per_sqft": 45.0,
        "cold_storage": True,
        "temperature_min": -25.0,
        "temperature_max": 4.0,
        "humidity_control": True,
        "cctv_count": 16,
        "guards_count": 4,
        "loading_dock": True,
        "parking_spaces": 10,
        "nearby_police": "Birgunj District Police - 1.2km",
        "nearby_hospital": "Narayani Sub-Regional Hospital - 2km",
        "nearby_fire": "Birgunj Damkal Fire Station - 2.5km",
        "nearby_fuel": "Nepal Oil Corp Depot Pump - 600m",
        "nearby_bank": "Nabil Bank Dry Port Branch - 400m",
        "description": "Multi-temperature certified logistics facility with dedicated multi-tenant docking."
    }, headers=po_headers)
    assert create_wh_resp.status_code == 200
    wh_id = create_wh_resp.json()["warehouse"]["id"]

    # 3. Client 1 (contact@himalayancargo.np) reserves 3,000 sqft
    cl_login = client.post("/api/auth/login", json={"email": "contact@himalayancargo.np", "password": "BrandNewPassword2026!"})
    cl_token = cl_login.json()["access_token"]
    cl_headers = {"Authorization": f"Bearer {cl_token}"}

    res1 = client.post(f"/api/warehouses/{wh_id}/reserve", json={
        "space_required": 3000.0,
        "purpose": "Pharmaceutical cold chain batch staging"
    }, headers=cl_headers)
    assert res1.status_code == 200
    req1_id = res1.json()["reservation_id"]
    inv1 = res1.json()["invoice"]
    assert inv1["subtotal"] == 135000.0  # 3000 * 45
    assert inv1["vat_amount"] == 17550.0  # 13% VAT
    assert inv1["grand_total"] == 152550.0

    # 4. Multi-Tenant Lease 2: Client 1 reserves another 4,000 sqft (1 Warehouse <-> Multiple Leases)
    res2 = client.post(f"/api/warehouses/{wh_id}/reserve", json={
        "space_required": 4000.0,
        "purpose": "Packaged food dry goods storage"
    }, headers=cl_headers)
    assert res2.status_code == 200
    assert res2.json()["invoice"]["subtotal"] == 180000.0

    # 5. Capacity Check: Client attempts to reserve 4,000 sqft (Only 3,000 sqft available) -> Must fail with HTTP 400
    res_overflow = client.post(f"/api/warehouses/{wh_id}/reserve", json={
        "space_required": 4000.0,
        "purpose": "Overflow cargo"
    }, headers=cl_headers)
    assert res_overflow.status_code == 400
    assert "exceeds available capacity" in res_overflow.json()["detail"]

    # 6. Property Owner Overview API
    overview_resp = client.get("/api/property-owner/overview", headers=po_headers)
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()
    assert overview_data["summary"]["total_properties"] >= 1
    assert overview_data["summary"]["total_capacity_sqft"] >= 10000.0
    assert overview_data["summary"]["total_leased_sqft"] >= 7000.0
    assert overview_data["summary"]["total_available_sqft"] <= 3000.0
    assert overview_data["summary"]["active_tenants_count"] >= 2
    assert len(overview_data["warehouses"]) >= 1
    target_wh = next(w for w in overview_data["warehouses"] if w["id"] == wh_id)
    assert target_wh["cctv_count"] == 16
    assert target_wh["guards_count"] == 4
    assert target_wh["nearby_police"] == "Birgunj District Police - 1.2km"
    assert target_wh["cold_storage"] is True
    assert target_wh["temperature_min"] == -25.0

    # 7. Property Owner Space Request Status Management
    patch_resp = client.patch(f"/api/property-owner/requests/{req1_id}", json={
        "status": "approved",
        "admin_notes": "Dock bay 3 allocated. Temperature logging active."
    }, headers=po_headers)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["request"]["status"] == "approved"

def test_client_adaptive_dispatch_and_vat_settlement():
    # 1. Login as Client 1 (who has an approved warehouse lease from previous test)
    cl_login = client.post("/api/auth/login", json={"email": "contact@himalayancargo.np", "password": "BrandNewPassword2026!"})
    cl_token = cl_login.json()["access_token"]
    cl_headers = {"Authorization": f"Bearer {cl_token}"}

    # Verify cockpit stats reflects assigned warehouse
    portal_resp = client.post("/api/portal/cockpit-stats", headers=cl_headers)
    assert portal_resp.status_code == 200
    stats = portal_resp.json()["stats"]
    assert stats["has_assigned_warehouse"] is True
    assert len(stats["assigned_warehouses"]) >= 1
    wh = next(w for w in stats["assigned_warehouses"] if w["cold_storage"])
    assert wh["cold_storage"] is True
    assert any(("-25" in w["temperature_range"] or "-2" in w["temperature_range"]) for w in stats["assigned_warehouses"] if w.get("temperature_range"))

    # 2. Book Dispatch from Leased Warehouse Dock
    disp_dock_resp = client.post("/api/dispatch/orders", json={
        "pickup_address": f"{wh['name']}, Loading Bay 3, Birgunj",
        "warehouse_id": wh["warehouse_id"],
        "vehicle_type": "truck",
        "total_distance": 22.0,
        "delivery_address": "Kalimati Fruit Market Depot, Kathmandu",
        "recipient_name": "Kathmandu Wholesale Dist.",
        "recipient_phone": "9801998877",
        "bill_type": "regular",
        "pan_number": "601234567"
    }, headers=cl_headers)
    assert disp_dock_resp.status_code == 200
    dock_data = disp_dock_resp.json()
    assert dock_data["status"] == "success"
    assert dock_data["dispatch"]["warehouse_id"] == wh["warehouse_id"]
    dock_inv = dock_data["invoice"]
    assert dock_inv["subtotal"] > 0
    assert dock_inv["tax_amount"] == round(dock_inv["subtotal"] * 0.13, 2)
    assert dock_inv["payment_status"] == "unpaid"

    # 3. Register Ad-Hoc Client (No Leased Warehouse)
    adhoc_email = "direct.shipper@nepaltrade.np"
    client.post("/api/auth/register", json={
        "name": "Direct Point-to-Point Shipper",
        "email": adhoc_email,
        "password": "SecurePassword2026!",
        "phone": "9809988112",
        "role": "client",
        "address": "Tripureswor, Kathmandu"
    })

    db = SessionLocal()
    adhoc_u = db.query(User).filter(User.email == adhoc_email).first()
    adhoc_code = adhoc_u.email_verification_token
    db.close()

    v_adhoc = client.post("/api/auth/verify-code", json={"email": adhoc_email, "code": adhoc_code})
    assert v_adhoc.status_code == 200
    adhoc_token = v_adhoc.json()["access_token"]
    adhoc_headers = {"Authorization": f"Bearer {adhoc_token}"}

    # Verify ad-hoc client has NO assigned warehouse
    adhoc_portal = client.post("/api/portal/cockpit-stats", headers=adhoc_headers)
    assert adhoc_portal.status_code == 200
    adhoc_stats = adhoc_portal.json()["stats"]
    assert adhoc_stats["has_assigned_warehouse"] is False
    assert len(adhoc_stats["assigned_warehouses"]) == 0

    # 4. Ad-Hoc Client directly books Point-to-Point Freight Transit (No Warehouse Required)
    disp_p2p_resp = client.post("/api/dispatch/orders", json={
        "pickup_address": "Balaju Industrial Estate Gate 2, Kathmandu",
        "warehouse_id": None,
        "vehicle_type": "pickup",
        "total_distance": 18.5,
        "delivery_address": "Dhulikhel Hospital Medical Store, Kavre",
        "recipient_name": "Store In-charge",
        "recipient_phone": "9841122334",
        "bill_type": "regular",
        "pan_number": "601234567"
    }, headers=adhoc_headers)
    assert disp_p2p_resp.status_code == 200
    p2p_data = disp_p2p_resp.json()
    assert p2p_data["status"] == "success"
    assert p2p_data["dispatch"]["warehouse_id"] is None
    p2p_inv = p2p_data["invoice"]

    # 5. Settle 13% IRD VAT Tax Invoice via eSewa
    pay_resp = client.post(f"/api/invoices/{p2p_inv['id']}/pay", json={
        "payment_method": "esewa",
        "reference_id": "ESEWA-TXN-2026-99"
    }, headers=adhoc_headers)
    assert pay_resp.status_code == 200
    assert pay_resp.json()["status"] == "success"
    assert pay_resp.json()["invoice"]["payment_status"] == "paid"

def test_commercial_driver_workflow():
    # 1. Register and verify Commercial Driver
    driver_email = "driver.pokhara@nepalroad.np"
    reg = client.post("/api/auth/register", json={
        "name": "Hari Sharma",
        "email": driver_email,
        "password": "SecurePassword2026!",
        "phone": "9812334455",
        "role": "driver",
        "address": "Prithvi Chowk, Pokhara"
    })
    assert reg.status_code == 200

    db = SessionLocal()
    driver_u = db.query(User).filter(User.email == driver_email).first()
    code = driver_u.email_verification_token
    db.close()

    v_resp = client.post("/api/auth/verify-code", json={"email": driver_email, "code": code})
    assert v_resp.status_code == 200
    driver_token = v_resp.json()["access_token"]
    driver_headers = {"Authorization": f"Bearer {driver_token}"}

    # 2. Driver overview
    ov_resp = client.get("/api/driver/overview", headers=driver_headers)
    assert ov_resp.status_code == 200
    ov_data = ov_resp.json()
    assert ov_data["status"] == "success"
    assert ov_data["driver"]["name"] == "Hari Sharma"

    # Driver accepts an available dispatch job or claim one
    db = SessionLocal()
    from app.models.logistics import DispatchOrder
    order = db.query(DispatchOrder).first()
    if order:
        order.driver_id = driver_u.id
        order.status = "assigned"
        db.commit()
        job_id = order.id
    db.close()

    # 3. Transmit GPS Telemetry Ping
    tel_resp = client.post("/api/driver/telemetry", json={
        "order_id": job_id if order else None,
        "latitude": 27.7012,
        "longitude": 85.3120,
        "accuracy": 5.0,
        "speed": 35.0
    }, headers=driver_headers)
    assert tel_resp.status_code == 200
    assert tel_resp.json()["status"] == "success"

    if order:
        # 4. Trip Status Transition: picked_up -> on_the_way
        patch1 = client.patch(f"/api/driver/orders/{job_id}/status", json={"status": "picked_up"}, headers=driver_headers)
        assert patch1.status_code == 200
        assert patch1.json()["order"]["status"] == "picked_up"

        patch2 = client.patch(f"/api/driver/orders/{job_id}/status", json={"status": "on_the_way"}, headers=driver_headers)
        assert patch2.status_code == 200
        assert patch2.json()["order"]["status"] == "on_the_way"

        # 5. Digital Proof of Delivery (POD)
        pod_resp = client.post(f"/api/driver/orders/{job_id}/pod", json={
            "recipient_name": "Sita Thapa",
            "delivery_notes": "All pallets received intact with seal intact."
        }, headers=driver_headers)
        assert pod_resp.status_code == 200
        assert pod_resp.json()["status"] == "success"

def test_heavy_equipment_owner_workflow():
    # 1. Register and verify Heavy Equipment Owner
    eq_email = "machinery.crane@himalayanequip.np"
    reg = client.post("/api/auth/register", json={
        "name": "Himalayan Heavy Cranes & Forklifts",
        "email": eq_email,
        "password": "SecurePassword2026!",
        "phone": "9805566778",
        "role": "equipment_owner",
        "address": "Birgunj Inland Port Road"
    })
    assert reg.status_code == 200

    db = SessionLocal()
    eq_u = db.query(User).filter(User.email == eq_email).first()
    code = eq_u.email_verification_token
    db.close()

    v_resp = client.post("/api/auth/verify-code", json={"email": eq_email, "code": code})
    assert v_resp.status_code == 200
    eq_token = v_resp.json()["access_token"]
    eq_headers = {"Authorization": f"Bearer {eq_token}"}

    # 2. Equipment Overview
    ov_resp = client.get("/api/equipment/overview", headers=eq_headers)
    assert ov_resp.status_code == 200
    assert ov_resp.json()["status"] == "success"

    # 3. Register New Machinery
    create_eq = client.post("/api/equipment", json={
        "name": "Komatsu 7-Ton Heavy Duty Forklift",
        "type": "forklift",
        "model": "FD70-10",
        "daily_rate": 9500.0,
        "security_deposit": 20000.0,
        "location": "Birgunj Dry Port Logistics Hub",
        "description": "Heavy container handling forklift with certified operator.",
        "weight": 7000.0
    }, headers=eq_headers)
    assert create_eq.status_code == 200
    new_eq_id = create_eq.json()["equipment"]["id"]

    # 4. Book Equipment
    start = date.today() + timedelta(days=1)
    end = date.today() + timedelta(days=4)
    book_resp = client.post(f"/api/equipment/{new_eq_id}/book", json={
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "location": "Kalimati Cold Store Loading Dock",
        "job_type": "Cold Chain Pallet Unloading"
    }, headers=eq_headers)
    assert book_resp.status_code == 200
    job_id = book_resp.json()["job"]["id"]
    assert book_resp.json()["job"]["days"] == 3
    assert book_resp.json()["job"]["total_amount"] == 28500.0  # 9500 * 3

    # 5. Complete Job
    stat_resp = client.patch(f"/api/equipment/jobs/{job_id}/status", json={"status": "completed"}, headers=eq_headers)
    assert stat_resp.status_code == 200
    assert stat_resp.json()["status"] == "success"

def test_licensed_security_agency_5_use_cases():
    # 1. Register and verify Licensed Security Agency
    sec_email = "suraksha.agency@securitycommand.np"
    reg = client.post("/api/auth/register", json={
        "name": "Nepal Suraksha Agency Pvt Ltd",
        "email": sec_email,
        "password": "SecurePassword2026!",
        "phone": "9809988776",
        "role": "security_agency",
        "address": "Ring Road Security Division, Kathmandu"
    })
    assert reg.status_code == 200

    db = SessionLocal()
    sec_u = db.query(User).filter(User.email == sec_email).first()
    code = sec_u.email_verification_token
    db.close()

    v_resp = client.post("/api/auth/verify-code", json={"email": sec_email, "code": code})
    assert v_resp.status_code == 200
    sec_token = v_resp.json()["access_token"]
    sec_headers = {"Authorization": f"Bearer {sec_token}"}

    # USE CASE 1: Register Agency & Government License Overview
    ov_resp = client.get("/api/security/overview", headers=sec_headers)
    assert ov_resp.status_code == 200
    ov_data = ov_resp.json()
    assert ov_data["status"] == "success"
    assert "agency" in ov_data
    assert ov_data["agency"]["license_number"] is not None

    # USE CASE 2: Manage Guard Personnel Roster (Badge/Rank)
    guard_resp = client.post("/api/security/guards", json={
        "name": "Bhim Bahadur Thapa",
        "phone": "9812998877",
        "citizenship_no": "27-01-70-04918",
        "badge_id": "SEC-G-8821",
        "rank": "Patrol Officer"
    }, headers=sec_headers)
    assert guard_resp.status_code == 200
    guard_id = guard_resp.json()["guard"]["id"]

    # USE CASE 3: Deploy Guards to Warehouse Posts <<include>> Configure Day/Night Shift Schedules
    asgn_resp = client.post("/api/security/assignments", json={
        "warehouse_id": 1,
        "personnel_id": guard_id,
        "shift_type": "night",
        "start_date": date.today().isoformat()
    }, headers=sec_headers)
    assert asgn_resp.status_code == 200
    assert asgn_resp.json()["assignment"]["shift"] == "night"

    # USE CASE 4: Log Security Incidents (Theft/Fire/Intrusion) <<extend>> Escalate & Notify Local Nepal Police Post
    inc_resp = client.post("/api/security/incidents", json={
        "warehouse_id": 1,
        "incident_type": "perimeter_breach",
        "severity": "critical",
        "description": "Unauthorized vehicle detected inspecting rear godown fence at 02:30 AM.",
        "escalate_to_police": True
    }, headers=sec_headers)
    assert inc_resp.status_code == 200
    inc_data = inc_resp.json()
    assert inc_data["incident"]["police_station_notified"] is not None
    assert "Escalated & dispatched alert" in inc_data["message"]

    # USE CASE 5: Generate Monthly Station Guarding Invoices (13% IRD VAT Compliant)
    inv_resp = client.post("/api/security/invoices/generate", json={
        "warehouse_id": 1,
        "guards_count": 4,
        "monthly_rate_per_guard": 25000.0
    }, headers=sec_headers)
    assert inv_resp.status_code == 200
    inv_data = inv_resp.json()["invoice"]
    assert inv_data["subtotal"] == 100000.0  # 4 * 25000
    assert inv_data["vat_13_percent"] == 13000.0  # 13% VAT
    assert inv_data["grand_total"] == 113000.0
    assert inv_data["payment_status"] == "unpaid"
