import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from seeders.seed_data import seed_database
from app.core.database import SessionLocal
from app.models.finance import Invoice
from app.services.invoice_service import InvoiceService

client = TestClient(app)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    seed_database()

def test_ping():
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.text == "pong"

def test_welcome_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "Kathmandu Warehousing" in response.text

def test_admin_login():
    response = client.post("/api/auth/login", json={
        "email": "admin.access@kwdc.test",
        "password": "KwdcNew2026!"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == "admin"

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

def test_warehouses_endpoint():
    response = client.get("/warehouses")
    assert response.status_code == 200
    assert "Kalimati Cold Store" in response.text

def test_pdf_tax_invoice_generation():
    db = SessionLocal()
    inv = db.query(Invoice).first()
    assert inv is not None
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
