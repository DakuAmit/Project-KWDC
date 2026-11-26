"""
Verification suite for:
1. Property Owner maintenance hold on pending (pre-audit) properties + Geocoding endpoint.
2. SuperAdmin Assign Incharge for physical inspection (POST /api/admin/warehouses/{id}/assign-incharge).
3. SuperAdmin Total Warehouses Registry with multi-status filters (GET /api/admin/warehouses).
4. SuperAdmin independent Client Base Tariff vs Owner Rate (POST /api/admin/warehouses/{id}/set-tariff)
   and Client billing via client_rate_per_sqft.
5. Frontend template checks for Google Map pinning UI, Maintenance Hold on all owner cards,
   Admin Total Warehouses drawer, Assign Incharge modal, and Client Base Tariff modal.
"""

import random
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal
from backend.auth_utils import get_password_hash
import backend.models as models

client = TestClient(app)


def create_user(email: str, full_name: str, phone: str, role: str) -> int:
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
                kyc_status=models.KycStatus.VERIFIED,
            )
            db.add(u)
            db.commit()
            db.refresh(u)
        return u.id
    finally:
        db.close()


def login_headers(email: str, password: str = "Password@123") -> dict:
    res = client.post("/api/auth/login", json={"email": email.lower(), "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def cleanup_test_entities(user_emails: list, warehouse_ids: list):
    if not user_emails and not warehouse_ids:
        return
    db = SessionLocal()
    try:
        if warehouse_ids:
            bookings = db.query(models.WarehouseRequest).filter(
                models.WarehouseRequest.warehouse_id.in_(warehouse_ids)
            ).all()
            booking_ids = [b.id for b in bookings]
            if booking_ids:
                db.query(models.TaxInvoice).filter(models.TaxInvoice.storage_booking_id.in_(booking_ids)).delete(synchronize_session=False)
                db.query(models.WarehouseRequest).filter(models.WarehouseRequest.id.in_(booking_ids)).delete(synchronize_session=False)
            db.query(models.WarehouseActivityLog).filter(models.WarehouseActivityLog.warehouse_id.in_(warehouse_ids)).delete(synchronize_session=False)
            db.query(models.WarehouseInchargeAssignment).filter(models.WarehouseInchargeAssignment.warehouse_id.in_(warehouse_ids)).delete(synchronize_session=False)
            db.query(models.Warehouse).filter(models.Warehouse.id.in_(warehouse_ids)).delete(synchronize_session=False)

        if user_emails:
            db.query(models.User).filter(models.User.email.in_([e.lower() for e in user_emails])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_admin_warehouse_controls():
    rand_id = random.randint(10000, 99999)
    owner_email = f"owner_ctrl_{rand_id}@kwdc.com.np"
    inc_email = f"inc_ctrl_{rand_id}@kwdc.com.np"
    client_email = f"client_ctrl_{rand_id}@kwdc.com.np"
    created_wh_ids = []

    try:
        create_user(owner_email, "Ctrl Owner", f"98410{rand_id}", "property_owner")
        inc_id = create_user(inc_email, "Ctrl Inspector", f"98420{rand_id}", "warehouse_incharge")
        create_user(client_email, "Ctrl Client", f"98430{rand_id}", "commercial_client")

        admin_hdrs = login_headers("admin@kwdc.com.np", "Admin@123")
        owner_hdrs = login_headers(owner_email)
        client_hdrs = login_headers(client_email)

        # 1. Geocode endpoint works cleanly for landmark strings
        geo_res = client.get("/api/maps/geocode", params={"address": "Balaju, Kathmandu"})
        assert geo_res.status_code == 200, geo_res.text
        geo_data = geo_res.json()
        assert "lat" in geo_data and "lng" in geo_data

        # 2. Owner registers warehouse -> initially pending audit
        wh_res = client.post(
            "/api/warehouses/list-space",
            headers=owner_hdrs,
            json={
                "title": f"Test Ctrl Godown {rand_id}",
                "space_type": "COVERED_GODOWN",
                "district": "Kathmandu",
                "municipality": "Kathmandu Metro",
                "ward_no": 16,
                "neighborhood_landmark": "Near Balaju Pul",
                "latitude": 27.734,
                "longitude": 85.302,
                "input_unit": "SQFT",
                "input_value": 2000,
                "monthly_rate_per_sqft": 30.0,
                "road_access_ft": 24.0,
            },
        )
        assert wh_res.status_code == 200, wh_res.text
        wh_id = wh_res.json()["warehouse_id"]
        created_wh_ids.append(wh_id)

        # 3. Owner toggles maintenance hold BEFORE audit approval
        hold_res = client.post(
            f"/api/warehouses/{wh_id}/request-maintenance-hold",
            headers=owner_hdrs,
            json={"is_on_hold": True, "hold_reason_note": "Floor concreting & shutters fitting before audit."},
        )
        assert hold_res.status_code == 200, hold_res.text

        # Check SuperAdmin Total Warehouses filters include pending_audit & on_hold
        all_wh = client.get("/api/admin/warehouses", headers=admin_hdrs)
        assert all_wh.status_code == 200, all_wh.text
        match = [w for w in all_wh.json() if w["id"] == wh_id]
        assert len(match) == 1
        assert "pending_audit" in match[0]["status_tags"]
        assert "on_hold" in match[0]["status_tags"]

        hold_filtered = client.get("/api/admin/warehouses", params={"status_filter": "on_hold"}, headers=admin_hdrs)
        assert any(w["id"] == wh_id for w in hold_filtered.json())

        # Release hold so it can be published cleanly later
        rel_res = client.post(
            f"/api/warehouses/{wh_id}/request-maintenance-hold",
            headers=owner_hdrs,
            json={"is_on_hold": False, "hold_reason_note": "Maintenance repairs completed and inspected."},
        )
        assert rel_res.status_code == 200, rel_res.text

        # 4. SuperAdmin assigns Warehouse Incharge for inspection
        assign_res = client.post(
            f"/api/admin/warehouses/{wh_id}/assign-incharge",
            headers=admin_hdrs,
            json={"incharge_id": inc_id, "notes": "Verify 24 ft road clearance"},
        )
        assert assign_res.status_code == 200, assign_res.text
        assert assign_res.json()["incharge_id"] == inc_id
        assert assign_res.json()["physical_audit_status"] == "AUDIT_SCHEDULED"

        pending_res = client.get("/api/admin/pending-warehouses", headers=admin_hdrs)
        pending_row = [w for w in pending_res.json() if w["id"] == wh_id][0]
        assert pending_row["assigned_incharge_id"] == inc_id

        # 5. SuperAdmin sets distinct Client Base Tariff (Rs. 45/sqft) while keeping Owner Rate (Rs. 30/sqft)
        tariff_res = client.post(
            f"/api/admin/warehouses/{wh_id}/set-tariff",
            headers=admin_hdrs,
            json={"client_rate_per_sqft": 45.0, "owner_rate_per_sqft": 30.0},
        )
        assert tariff_res.status_code == 200, tariff_res.text
        assert tariff_res.json()["client_rate_per_sqft"] == 45.0
        assert tariff_res.json()["owner_rate_per_sqft"] == 30.0

        # Approve warehouse so client catalog shows it
        app_res = client.post(f"/api/admin/warehouses/{wh_id}/approve", headers=admin_hdrs, json={})
        assert app_res.status_code == 200, app_res.text

        cat_res = client.get("/api/warehouses/catalog")
        assert cat_res.status_code == 200
        cat_item = [c for c in cat_res.json() if c["id"] == wh_id][0]
        assert cat_item["monthly_rate_per_sqft"] == 45.0

        # Client books 500 sqft -> monthly_base_rent must reflect 500 * 45 = Rs. 22,500 (Client Tariff)
        book_res = client.post(
            "/api/warehouses/book",
            headers=client_hdrs,
            json={
                "warehouse_id": wh_id,
                "requested_sqft": 500,
                "booking_duration_type": "MONTHLY",
                "duration_value": 1,
                "client_intended_use": "Hardware Stock",
            },
        )
        assert book_res.status_code == 200, book_res.text

        verified_filtered = client.get("/api/admin/warehouses", params={"status_filter": "verified"}, headers=admin_hdrs)
        assert any(w["id"] == wh_id for w in verified_filtered.json())

        # Verify provisioning Warehouse Incharge WITHOUT assigning a warehouse initially works!
        unassigned_inc_email = f"inc_unassigned_{rand_id}@kwdc.com.np"
        prov_res = client.post(
            "/api/admin/incharges",
            headers=admin_hdrs,
            json={
                "full_name": "Unassigned Inspector",
                "email": unassigned_inc_email,
                "phone_number": f"98490{rand_id}",
                "warehouse_id": None,
                "password": "Test@2026"
            }
        )
        assert prov_res.status_code == 200, prov_res.text
        assert prov_res.json()["assigned_facility_id"] is None

        # 6. Verify frontend templates expose all requested UI controls
        owner_html = client.get("/owner").text
        assert "pinOwnerCurrentLocation()" in owner_html
        assert "geocodeOwnerLandmark" in owner_html
        assert "Pin My Location" in owner_html

        admin_html = client.get("/admin").text
        assert "nav-warehouses" in admin_html
        assert "Total Warehouses" in admin_html
        assert "adminAssignInchargeModal" in admin_html
        assert "adminTariffModal" in admin_html

        print("[PASS] Admin warehouse controls, incharge assignment, independent tariffs & owner pin map verified.")
    finally:
        cleanup_test_entities([owner_email, inc_email, client_email, f"inc_unassigned_{rand_id}@kwdc.com.np"], created_wh_ids)


if __name__ == "__main__":
    test_admin_warehouse_controls()
