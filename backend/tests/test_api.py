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
