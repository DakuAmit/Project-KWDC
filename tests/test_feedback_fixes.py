"""
Focused End-to-End Verification for May Test Feedback Fixes:
1. Selecting Independent Driver prompts KYC & PIN onboarding (no auto-seeded dummy driver).
2. Driver KYC requires License #, supports multiple license categories, Citizenship/NID Front & Back, Standby option, and returns Driver App URL + Play/App Store preview UI.
3. Zero fake template Freight Dispatch jobs (3) or fake Freight Yield (Rs. 41,220) when DB has no dispatches; real client dispatch jobs immediately appear on fleet dispatch board.
4. Pending KYC/Bank Property Owner cannot register space via UI gate or POST /api/warehouses/list-space (returns 403 until KYC is verified).
"""

import random
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def create_user(email: str, full_name: str, phone: str, role: str, verified_kyc: bool = False):
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
                kyc_status=models.KycStatus.VERIFIED if verified_kyc else models.KycStatus.PENDING_SUBMISSION
            )
            db.add(u)
            db.commit()
    finally:
        db.close()

    res = client.post("/api/auth/login", json={"email": email.lower(), "password": "Password@123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_feedback_fixes():
    rand_id = random.randint(10000, 99999)

    # 1. Clean Fleet / Independent Driver Onboarding & Zero Fake Templates
    ind_hdrs = create_user(f"ind_drv_{rand_id}@kwdc.com.np", "Pawan Test Driver", f"+977-9864{rand_id}", "fleet_partner")

    # Select Independent Driver -> must ask for KYC, NOT auto-seed dummy LIC- driver
    op_res = client.post("/api/fleet/operator-type", headers=ind_hdrs, json={"operator_type": "INDEPENDENT_OWNER"})
    assert op_res.status_code == 200, op_res.text
    assert op_res.json()["needs_driver_kyc"] is True
    assert op_res.json()["driver_pin"] is None

    roster_before = client.get("/api/fleet/my-fleet", headers=ind_hdrs).json()
    assert len(roster_before["drivers"]) == 0

    # Earnings on brand-new driver must be 0, NOT 41,220
    earn_res = client.get("/api/fleet/earnings", headers=ind_hdrs).json()
    assert earn_res["net_fleet_earnings_npr"] == 0.0
    assert earn_res["completed_trips_count"] == 0
    assert earn_res["settlements"] == []

    # Submit complete Independent Driver KYC (Driving License + Citizenship Front/Back + Vehicle + Bluebook + PIN)
    drv_res = client.post("/api/fleet/drivers", headers=ind_hdrs, json={
        "full_name": "Pawan Test Driver",
        "phone_number": f"+977-9864{rand_id}",
        "license_number": f"01-06-{rand_id}",
        "license_categories": [
            "Category B (Van / Pickup / Light 4-Wheeler)",
            "Category G (Heavy / Multi-Axle Truck)"
        ],
        "id_document_type": "CITIZENSHIP",
        "citizenship_no": f"27-01-74-{rand_id}",
        "id_doc_front_url": "https://example.com/ctz-front.jpg",
        "id_doc_back_url": "https://example.com/ctz-back.jpg",
        "license_photo_front_url": "https://example.com/lic-front.jpg",
        "license_photo_back_url": "https://example.com/lic-back.jpg",
        "vehicle_category": "MINI_TRUCK",
        "vehicle_model_name": "Tata Ace Gold",
        "vehicle_license_plate": f"Ba 2 Cha {rand_id}",
        "bluebook_number": f"BB-IND-{rand_id}",
        "bluebook_photo_url": "https://example.com/bluebook.jpg",
        "payload_capacity_kg": 1500,
        "blood_group": "O+",
        "emergency_contact_name": "Suman Pandey",
        "emergency_contact_phone": "+977-9841000999",
        "is_standby": False,
        "is_self_driver": True,
        "login_pin": "7412"
    })
    assert drv_res.status_code == 200, drv_res.text
    drv_json = drv_res.json()
    assert drv_json["driver_app_url"] == "/driver"
    assert drv_json["driver_pin"] == "7412"
    assert "Category B" in drv_json["license_category"] and "Category G" in drv_json["license_category"]

    # Also test adding a Standby driver with National ID (NID) Front & Back
    standby_res = client.post("/api/fleet/drivers", headers=ind_hdrs, json={
        "full_name": "Kuber Standby",
        "phone_number": f"+977-9810{rand_id}",
        "license_number": f"02-09-{rand_id}",
        "license_categories": ["Category H (Tractor / Trailer)"],
        "id_document_type": "NID",
        "id_document_number": f"999-{rand_id}",
        "id_doc_front_url": "https://example.com/nid-front.jpg",
        "id_doc_back_url": "https://example.com/nid-back.jpg",
        "license_photo_front_url": "https://example.com/lic2-front.jpg",
        "blood_group": "AB+",
        "emergency_contact_name": "Rama Shah",
        "emergency_contact_phone": "+977-9811112233",
        "is_standby": True,
        "login_pin": "9999"
    })
    assert standby_res.status_code == 200, standby_res.text
    assert standby_res.json()["is_standby"] is True
    assert standby_res.json()["id_document_type"] == "NID"

    # 2. Verify Real Client Dispatch Order appears cleanly on Fleet Board after KYC verification (blocked with 403 while unverified)
    client_hdrs = create_user(f"cli_fb_{rand_id}@kwdc.com.np", "Client Co", f"+977-9855{rand_id}", "commercial_client", verified_kyc=True)
    ord_res = client.post("/api/fleet/dispatch-orders", headers=client_hdrs, json={
        "dispatch_mode": "DIRECT_HAUL",
        "pickup_address": "Kalanki Yard",
        "pickup_contact_name": "Ram Client",
        "pickup_contact_phone": "+977-9851112233",
        "destination_address": "Koteshwor Hub",
        "consignee_name": "Sita Receiver",
        "consignee_phone": "+977-9841223344",
        "total_distance_km": 11.5,
        "cargo_description": f"Real Feedback Test Cargo #{rand_id}",
        "required_vehicle_category": "mini_truck",
        "cargo_weight_kg": 1200.0
    })
    assert ord_res.status_code == 200, ord_res.text
    blocked_jobs = client.get("/api/fleet/dispatch-orders", headers=ind_hdrs)
    assert blocked_jobs.status_code == 403, f"Unverified independent driver must not view jobs: {blocked_jobs.text}"

    # Admin verifies Individual Driver KYC -> dispatch board unlocks
    admin_hdrs = create_user(f"adm_fb_{rand_id}@kwdc.com.np", "Admin FB", f"+977-9801{rand_id}", "superadmin", verified_kyc=True)
    ind_uid = client.get("/api/auth/me", headers=ind_hdrs).json()["id"]
    ver_res = client.post(f"/api/admin/users/{ind_uid}/kyc-verify", headers=admin_hdrs, json={"kyc_status": "VERIFIED", "admin_notes": "License & Bluebook OK"})
    assert ver_res.status_code == 200, ver_res.text

    jobs = client.get("/api/fleet/dispatch-orders", headers=ind_hdrs).json()
    assert not any(j.get("order_number") == "FRT-2083-0012" for j in jobs), "Fake template jobs must not appear!"
    assert any(f"Real Feedback Test Cargo #{rand_id}" in j.get("cargo_description", "") for j in jobs)

    # 3. Property Owner Pending KYC Gate Blocks Listing Space
    owner_hdrs = create_user(f"own_fb_{rand_id}@kwdc.com.np", "Sujata Owner", f"+977-9848{rand_id}", "property_owner", verified_kyc=False)
    blocked_list = client.post("/api/warehouses/list-space", headers=owner_hdrs, json={
        "title": "Should Be Blocked Pending KYC",
        "space_type": "dry_storage",
        "input_value": 5000,
        "input_unit": "sqft",
        "base_rate_per_sqft": 45.0,
        "district": "Kathmandu"
    })
    assert blocked_list.status_code == 403, blocked_list.text
    assert "KYC" in blocked_list.json()["detail"]

    # Check HTML UI markers exist cleanly
    fleet_html = client.get("/fleet").text
    assert 'id="driverAppLinkModal"' in fleet_html
    assert 'id="drvDocType"' in fleet_html
    assert 'id="drvIsStandby"' in fleet_html
    assert 'Rs. 41,220' not in fleet_html

    owner_html = client.get("/owner").text
    assert 'window.ownerKycStatus' in owner_html
    assert 'id="listSpaceForm" novalidate' in owner_html

    # 4. Verify ALL Admin GET endpoints including /incharge-logs with a real WarehouseActivityLog row
    admin_res = client.post("/api/auth/login", json={"email": "admin@kwdc.com.np", "password": "Admin@123"})
    assert admin_res.status_code == 200
    admin_hdrs = {"Authorization": f"Bearer {admin_res.json()['access_token']}"}

    from backend.database import SessionLocal
    import backend.models as models
    db = SessionLocal()
    try:
        wh = db.query(models.Warehouse).first()
        admin_u = db.query(models.User).filter(models.User.email == "admin@kwdc.com.np").first()
        if wh and admin_u:
            db.add(models.WarehouseActivityLog(
                warehouse_id=wh.id,
                incharge_id=admin_u.id,
                log_type="SECURITY_CHECK",
                summary="Smoke test shift log",
                detailed_notes="Automated verification of created_at formatting"
            ))
            db.commit()
    finally:
        db.close()

    admin_gets = [
        "/api/admin/pending-warehouses",
        "/api/admin/pending",
        "/api/admin/bookings",
        "/api/admin/incharges",
        "/api/admin/incharge-logs",
        "/api/admin/fleet-radar",
        "/api/admin/payouts",
        "/api/admin/maintenance-holds",
        "/api/admin/users",
        "/api/admin/system-status",
        "/api/admin/invoices",
        "/api/admin/fare-config",
        "/api/admin/lien-overdue-leases",
        "/api/admin/auctions",
        "/api/admin/change-requests",
    ]
    for ep in admin_gets:
        r = client.get(ep, headers=admin_hdrs)
        assert r.status_code == 200, f"{ep} failed: {r.status_code} {r.text}"

    print("ALL USER FEEDBACK FIXES VERIFIED SUCCESSFULLY!")


if __name__ == "__main__":
    test_feedback_fixes()
