"""
End-to-End Verification Suite for Property Owner Bugs & 6 New Features:
1. List Space with Interactive GPS Pin (lat/lng) & Multi-Photo URLs (WarehousePhoto)
2. Realized vs Potential Revenue Yield & Occupancy % Meter on /my-listings
3. Executed Master Lease Agreement (MLA) Viewer (/owner-contract)
4. Bug Fixes & Accounting Accuracy: /owner-leases & /my-payouts (10% Platform Fee + 10% Rent TDS + Net Bank Deposit + DAILY/WEEKLY/MONTHLY yield)
5. Sanctioned 15-Day Delisting & Tariff Revision Requests (Owner submits, Admin approves/rejects)
6. Anonymized Facility Health & Incharge Audit Feed (/owner-facility-health Privacy Shield)
"""

import random
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def get_auth_headers(email: str, full_name: str, phone: str, role: str):
    from backend.database import SessionLocal
    from backend.auth_utils import get_password_hash
    import backend.models as models

    db = SessionLocal()
    try:
        u = db.query(models.User).filter(models.User.email == email.lower()).first()
        if not u:
            u = models.User(
                full_name=full_name,
                email=email.lower(),
                phone_number=phone,
                hashed_password=get_password_hash("Password@123"),
                role=models.UserRole(role),
                is_verified=True,
                is_active=True,
                kyc_status=models.KycStatus.VERIFIED
            )
            db.add(u)
        else:
            u.is_verified = True
            u.is_active = True
            u.hashed_password = get_password_hash("Password@123")
        db.commit()
    finally:
        db.close()

    res = client.post("/api/auth/login", json={"email": email.lower(), "password": "Password@123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_property_owner_end_to_end():
    admin_res = client.post("/api/auth/login", json={"email": "admin@kwdc.com.np", "password": "Admin@123"})
    assert admin_res.status_code == 200, admin_res.text
    admin_hdrs = {"Authorization": f"Bearer {admin_res.json()['access_token']}"}

    rand_id = random.randint(10000, 99999)
    owner_hdrs = get_auth_headers(
        f"owner_prop_{rand_id}@kwdc.com.np",
        "Sita Ram Owner",
        f"+977-9843{rand_id}",
        "property_owner"
    )
    client_hdrs = get_auth_headers(
        f"client_prop_{rand_id}@kwdc.com.np",
        "Everest Imports Secret Client",
        f"+977-9852{rand_id}",
        "commercial_client"
    )
    incharge_hdrs = get_auth_headers(
        f"inc_prop_{rand_id}@kwdc.com.np",
        "Ramesh Incharge",
        f"+977-9804{rand_id}",
        "warehouse_incharge"
    )

    # 1. List Space with GPS Pin + Photo URLs
    list_res = client.post("/api/warehouses/list-space", headers=owner_hdrs, json={
        "title": f"Satungal Prime Bay #{rand_id}",
        "space_type": "COVERED_GODOWN",
        "input_value": 5000,
        "input_unit": "sqft",
        "monthly_rate_per_sqft": 50.0,
        "ceiling_height_ft": 20.0,
        "road_access_width_ft": 28.0,
        "municipality": "Chandragiri",
        "district": "Kathmandu",
        "latitude": 27.6845,
        "longitude": 85.2521,
        "photo_urls": [
            "https://example.com/bay-front.jpg",
            "https://example.com/bay-interior.jpg"
        ]
    })
    assert list_res.status_code == 200, list_res.text
    wh_id = list_res.json()["warehouse_id"]

    # Approve warehouse
    app_res = client.post(f"/api/admin/warehouses/{wh_id}/approve", headers=admin_hdrs, json={"approved": True})
    assert app_res.status_code == 200, app_res.text

    # Assign incharge & create shift activity log to test Privacy Shield
    from backend.database import SessionLocal
    import backend.models as models
    db = SessionLocal()
    try:
        inc_user = db.query(models.User).filter(models.User.email == f"inc_prop_{rand_id}@kwdc.com.np").first()
        assign = models.WarehouseInchargeAssignment(
            warehouse_id=wh_id,
            incharge_id=inc_user.id,
            is_active=True
        )
        db.add(assign)
        act = models.WarehouseActivityLog(
            warehouse_id=wh_id,
            incharge_id=inc_user.id,
            log_type="FIRE_SAFETY_CHECK",
            summary="Fire hydrants & CCTV perimeter inspection passed for bay zone.",
            detailed_notes="All perimeter bays cleared fire safety audit."
        )
        db.add(act)
        db.commit()
    finally:
        db.close()

    # Verify catalog shows photos
    cat_res = client.get("/api/warehouses/catalog")
    assert cat_res.status_code == 200
    found = [w for w in cat_res.json() if w["id"] == wh_id]
    assert len(found) == 1
    assert len(found[0]["photos"]) == 2

    # 2. Client Books 2,000 sq ft MONTHLY (40% occupancy) and pays advance -> active lease
    book_res = client.post("/api/warehouses/book", headers=client_hdrs, json={
        "warehouse_id": wh_id,
        "requested_sqft": 2000.0,
        "booking_duration_type": "MONTHLY",
        "duration_value": 1,
        "client_intended_use": "Electronics & Appliances"
    })
    assert book_res.status_code == 200, book_res.text
    req_id = book_res.json()["booking_id"]

    b_app = client.post(f"/api/warehouses/bookings/{req_id}/pay-advance", headers=client_hdrs)
    assert b_app.status_code == 200, b_app.text

    # 3. Verify /my-listings Occupancy & Revenue Yield Meter
    listings_res = client.get("/api/warehouses/my-listings", headers=owner_hdrs)
    assert listings_res.status_code == 200, listings_res.text
    wh_data = [w for w in listings_res.json() if w["id"] == wh_id][0]
    assert wh_data["occupied_sqft"] == 2000.0
    assert wh_data["occupancy_percent"] == 40.0
    assert wh_data["potential_monthly_yield_npr"] == 225000.0
    assert wh_data["realized_monthly_yield_npr"] == 90000.0
    assert len(wh_data["photos"]) == 2

    # 4. Verify Executed Master Lease Agreement (/owner-contract)
    contract_res = client.get(f"/api/warehouses/{wh_id}/owner-contract", headers=owner_hdrs)
    assert contract_res.status_code == 200, contract_res.text
    c_json = contract_res.json()
    assert c_json["contract_number"].startswith("KWDC-MLA-")
    assert "MASTER COMMERCIAL REAL ESTATE STORAGE AGREEMENT" in c_json["contract_text"]

    # 5. Verify /owner-leases & /my-payouts (10% Platform Fee + 10% Rent TDS + Net Bank Deposit)
    leases_res = client.get("/api/warehouses/owner-leases", headers=owner_hdrs)
    assert leases_res.status_code == 200, leases_res.text
    leases = [l for l in leases_res.json() if l["booking_id"] == req_id]
    assert len(leases) == 1
    assert leases[0]["allocated_sqft"] == 2000.0
    assert leases[0]["rate_per_sqft"] == 50.0
    assert leases[0]["booking_duration_type"] == "MONTHLY"
    assert leases[0]["monthly_rent_disbursement"] == 100000.0

    payouts_res = client.get("/api/warehouses/my-payouts", headers=owner_hdrs)
    assert payouts_res.status_code == 200, payouts_res.text
    payouts = [p for p in payouts_res.json() if p["warehouse_title"] == f"Satungal Prime Bay #{rand_id}"]
    assert len(payouts) == 1
    assert payouts[0]["monthly_gross_rent"] == 100000.0
    assert payouts[0]["platform_fee_10pct"] == 10000.0
    assert payouts[0]["net_payout_90pct"] == 90000.0
    assert payouts[0]["tds_10pct"] == 10000.0
    assert payouts[0]["net_bank_deposit_npr"] == 80000.0
    assert payouts[0]["tds_certificate_number"].startswith("TDS-2083-")

    # 6. Sanctioned 15-Day Delisting & Tariff Revision Workflow
    # 6a. Delisting must be blocked while tenant occupies 2,000 sq ft
    bad_delist = client.post(f"/api/warehouses/{wh_id}/change-request", headers=owner_hdrs, json={
        "request_type": "DELISTING_15_DAYS",
        "reason_note": "Trying to delist with active tenant"
    })
    assert bad_delist.status_code == 400, bad_delist.text

    # 6b. Rate revision submission & Admin approval
    rate_req = client.post(f"/api/warehouses/{wh_id}/change-request", headers=owner_hdrs, json={
        "request_type": "RATE_REVISION",
        "requested_rate_per_sqft": 55.0,
        "reason_note": "Market revision for upcoming empty bays"
    })
    assert rate_req.status_code == 200, rate_req.text
    cr_id = rate_req.json()["request_id"]

    admin_cr_list = client.get("/api/admin/change-requests", headers=admin_hdrs)
    assert admin_cr_list.status_code == 200
    assert any(r["id"] == cr_id for r in admin_cr_list.json())

    proc_res = client.post(f"/api/admin/change-requests/{cr_id}/process", headers=admin_hdrs, json={
        "status": "APPROVED",
        "admin_notes": "Approved tariff hike to NPR 55/sqft"
    })
    assert proc_res.status_code == 200, proc_res.text

    # Verify warehouse rate updated to 55.0
    listings_after = client.get("/api/warehouses/my-listings", headers=owner_hdrs).json()
    wh_after = [w for w in listings_after if w["id"] == wh_id][0]
    assert wh_after["monthly_rate_per_sqft"] == 55.0

    # 7. Anonymized Facility Health & Privacy Shield Verification
    health_res = client.get("/api/warehouses/owner-facility-health", headers=owner_hdrs)
    assert health_res.status_code == 200, health_res.text
    health_text = health_res.text
    assert "Fire hydrants & CCTV perimeter inspection passed" in health_text
    assert "Everest Imports Secret Client" not in health_text
    assert "Electronics & Appliances" not in health_text

    # 8. Verify Admin UI & Owner UI pages render cleanly
    assert client.get("/owner").status_code == 200
    admin_html = client.get("/admin").text
    assert "Owner 15-Day Delisting &amp; Tariff Revision Queue" in admin_html

    print("ALL PROPERTY OWNER BUG FIXES & 6 FEATURES VERIFIED SUCCESSFULLY!")


if __name__ == "__main__":
    test_property_owner_end_to_end()
