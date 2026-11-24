"""
Test Suite for Option A: Freight Pricing Engine & InDrive-style Counter-Offer Negotiation
Verifies:
1. Benchmark Base Formula calculation: Flag Drop + (KM * Rate * Multiplier) + Weight Surcharge
2. SuperAdmin Platform Margin & Tariff controller endpoints (GET & POST /api/admin/fare-config)
3. Client custom offer vs benchmark fare
4. Fleet Partner counter-offer submission (POST /api/fleet/dispatch-orders/{id}/counter-offer)
5. Client counter-offer acceptance (POST /api/fleet/counter-offers/{id}/accept) locking agreed fare & net driver payout
6. Driver terminal login response structure (data.driver object) and active-trip endpoint
"""

import random
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_freight_pricing_and_counter_offer_flow():
    # 1. SuperAdmin Login
    admin_login = client.post("/api/auth/login", json={"email": "admin@kwdc.com.np", "password": "Admin@123"})
    assert admin_login.status_code == 200, admin_login.text
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Test Admin Fare Config GET
    cfg_res = client.get("/api/admin/fare-config", headers=admin_headers)
    assert cfg_res.status_code == 200, cfg_res.text
    cfg_data = cfg_res.json()
    assert "platform_margin_percent" in cfg_data
    assert "flag_drops" in cfg_data
    assert "rates_per_km" in cfg_data
    assert len(cfg_data["simulations_15km"]) == 4

    # 3. Test Admin Fare Config POST (Update margin to 12.0%)
    update_res = client.post("/api/admin/fare-config", headers=admin_headers, json={
        "platform_margin_percent": 12.0,
        "fuel_multiplier": 1.10,
        "flag_drop_van_pickup": 1300.0,
        "rate_per_km_van_pickup": 70.0,
        "weight_rate_per_tonne": 180.0
    })
    assert update_res.status_code == 200, update_res.text
    assert update_res.json()["platform_margin_percent"] == 12.0

    # 4. Test Public Calculate-Fare endpoint
    calc_res = client.get("/api/fleet/calculate-fare?vehicle_category=PICKUP_VAN&distance_km=20&cargo_weight_kg=2000")
    assert calc_res.status_code == 200, calc_res.text
    calc = calc_res.json()
    # Flag drop: 1300 + Distance: 20 * 70 * 1.10 = 1540 + Weight: 2 * 180 = 360 -> Total: 3200
    assert calc["benchmark_fare_npr"] == 3200.0
    assert calc["platform_margin_percent"] == 12.0
    assert calc["platform_revenue_npr"] == round(3200.0 * 0.12, 2)
    assert calc["driver_payout_npr"] == round(3200.0 - (3200.0 * 0.12), 2)

    # Helper to get authenticated user token
    def get_token(email, full_name, phone, role):
        from backend.database import SessionLocal
        from backend.auth_utils import get_password_hash
        import backend.models as models
        db = SessionLocal()
        try:
            u = db.query(models.User).filter(models.User.email == email.lower()).first()
            if not u:
                client.post("/api/auth/register", json={
                    "full_name": full_name,
                    "email": email,
                    "phone_number": phone,
                    "password": "Password@123",
                    "confirm_password": "Password@123",
                    "role": role
                })
                u = db.query(models.User).filter(models.User.email == email.lower()).first()
            if u:
                u.is_verified = True
                u.is_active = True
                u.hashed_password = get_password_hash("Password@123")
                db.commit()
        finally:
            db.close()
        res = client.post("/api/auth/login", json={"email": email, "password": "Password@123"})
        return res.json().get("access_token")

    # 5. Client creates a dispatch order
    client_token = get_token("client_opt_a@kwdc.com.np", "InDrive Client", "+977-9841122334", "commercial_client")
    assert client_token is not None, "Failed to get client token"
    client_headers = {"Authorization": f"Bearer {client_token}"}

    order_payload = {
        "movement_type": "DIRECT_HAUL",
        "cargo_description": "Consumer Electronics & Textiles",
        "required_vehicle_category": "PICKUP_VAN",
        "pickup_address": "Balaju Industrial Godown #4",
        "pickup_contact_name": "Suman Thapa",
        "pickup_contact_phone": "+977-9841000111",
        "destination_address": "Kalanki Distribution Depot",
        "consignee_name": "Hari Karki",
        "consignee_phone": "+977-9841000222",
        "estimated_distance_km": 15.0,
        "cargo_weight_kg": 1500.0,
        "client_offered_fare_npr": 2800.0
    }
    order_res = client.post("/api/fleet/client-orders", headers=client_headers, json={**order_payload})
    assert order_res.status_code == 200, order_res.text
    order_data = order_res.json()
    order_id = order_data["order_id"]
    assert order_data["client_offered_fare_npr"] == 2800.0
    assert order_data["benchmark_fare_npr"] > 0

    # 6. Fleet Partner signs in or registers with unique account
    rand_id = random.randint(10000, 99999)
    fleet_email = f"fleet_opt_a_{rand_id}@kwdc.com.np"
    fleet_token = get_token(fleet_email, "Bikash Transport Services", f"+977-9869{rand_id}", "fleet_partner")
    assert fleet_token is not None, "Failed to get fleet token"
    fleet_headers = {"Authorization": f"Bearer {fleet_token}"}

    unique_plate = f"Ba 4 Kha {random.randint(1000, 9999)}"
    # Register truck & driver
    v_res = client.post("/api/fleet/vehicles", headers=fleet_headers, json={
        "category": "PICKUP_VAN",
        "model_name": "Mahindra Bolero Maxi Truck",
        "license_plate": unique_plate,
        "bluebook_number": f"BB-2083-{random.randint(1000, 9999)}",
        "payload_capacity_kg": 1500.0
    })
    assert v_res.status_code == 200, v_res.text
    veh_id = v_res.json()["vehicle_id"]

    drv_phone = f"9869{random.randint(100000, 999999)}"
    unique_lic = f"LIC-{random.randint(100000, 999999)}"
    d_res = client.post("/api/fleet/drivers", headers=fleet_headers, json={
        "full_name": "Bikash Shrestha",
        "phone_number": drv_phone,
        "login_pin": "5566",
        "license_number": unique_lic,
        "license_category": "Category B (Delivery Van / Pickup)",
        "assigned_vehicle_id": veh_id
    })
    assert d_res.status_code == 200, d_res.text
    drv_id = d_res.json()["driver_id"]

    # 7. Fleet Partner submits counter-offer (InDrive style)
    counter_res = client.post(f"/api/fleet/dispatch-orders/{order_id}/counter-offer", headers=fleet_headers, json={
        "offered_fare_npr": 3100.0,
        "counter_note": "Includes 2 helpers for swift unloading at Kalanki",
        "vehicle_id": veh_id,
        "driver_id": drv_id
    })
    assert counter_res.status_code == 200, counter_res.text
    counter_data = counter_res.json()
    offer_id = counter_data["offer_id"]
    assert counter_data["offered_fare_npr"] == 3100.0

    # 8. Client checks incoming counter-offers
    offers_res = client.get(f"/api/fleet/dispatch-orders/{order_id}/counter-offers", headers=client_headers)
    assert offers_res.status_code == 200, offers_res.text
    offers_list = offers_res.json()["counter_offers"]
    assert len(offers_list) >= 1
    assert offers_list[0]["id"] == offer_id
    assert offers_list[0]["offered_fare_npr"] == 3100.0
    assert "Includes 2 helpers" in offers_list[0]["counter_note"]

    # 9. Client accepts counter-offer
    accept_res = client.post(f"/api/fleet/counter-offers/{offer_id}/accept", headers=client_headers)
    assert accept_res.status_code == 200, accept_res.text
    accept_data = accept_res.json()
    assert accept_data["agreed_fare_npr"] == 3100.0
    assert accept_data["status"].lower() == "assigned"
    assert "delivery_otp" in accept_data

    # 10. Field Driver Login test
    drv_login = client.post("/api/fleet/driver/login", json={
        "phone_number": drv_phone,
        "pin": "5566"
    })
    assert drv_login.status_code == 200, drv_login.text
    drv_data = drv_login.json()
    # Check that data.driver wrapper exists and contains full_name
    assert "driver" in drv_data
    assert drv_data["driver"]["full_name"] == "Bikash Shrestha"
    assert drv_data["full_name"] == "Bikash Shrestha"
    driver_jwt = drv_data["access_token"]

    # 11. Driver active trip test
    trip_res = client.get("/api/fleet/driver/active-trip", headers={"Authorization": f"Bearer {driver_jwt}"})
    assert trip_res.status_code == 200, trip_res.text
    trip_json = trip_res.json()
    assert trip_json["has_active_trip"] is True
    assert "trip" in trip_json
    assert "active_trip" in trip_json
    assert trip_json["trip"]["order_id"] == order_id

    print("\n✅ All 11 Option A Freight Pricing & Counter-Offer Negotiation Checks Passed!")

if __name__ == "__main__":
    test_freight_pricing_and_counter_offer_flow()
