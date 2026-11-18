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
    assert "access_token" in data
    assert data["user"]["email"] == "contact@himalayancargo.np"
    assert data["user"]["role"] == "client"

def test_real_user_login():
    response = client.post("/api/auth/login", json={
        "email": "contact@himalayancargo.np",
        "password": "SecurePassword2026!"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == "client"

def test_email_verification_flow():
    db = SessionLocal()
    user = db.query(User).filter(User.email == "contact@himalayancargo.np").first()
    token = user.email_verification_token
    db.close()

    assert token is not None

    response = client.get(f"/api/auth/verify-email?token={token}")
    assert response.status_code == 200
    assert "Email verified successfully" in response.json()["message"]

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
