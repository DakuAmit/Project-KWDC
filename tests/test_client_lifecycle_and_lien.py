"""
End-to-End Verification Suite for:
1. 3-Tier Flexible Storage (Daily 1-6d, Weekly 1-3w, Monthly 1+m) & Advance Payment ("Pay First")
2. Stored Inventory & ISO/IEC 18004 QR Stock Ledger
3. Continuous Sq Ft Lifecycle (Expand, Downsize, Renew) & Client Contract Verification
4. Saved Consignee Address Book & Corporate KYC
5. 60-Day Overdue Lien Escalation (Month 1, 15d, 7d, 5d Gate Freeze, 48h Final Notice, Day 60 Forfeiture)
6. Outbound Gate Pass Lockout on Frozen Leases & Public Stock Auction Ledger
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
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_client_lifecycle_and_lien_auction():
    # 1. Admin login & seed warehouse
    admin_res = client.post("/api/auth/login", json={"email": "admin@kwdc.com.np", "password": "Admin@123"})
    assert admin_res.status_code == 200, admin_res.text
    admin_hdrs = {"Authorization": f"Bearer {admin_res.json()['access_token']}"}

    rand_id = random.randint(10000, 99999)
    owner_hdrs = get_auth_headers(f"owner_lien_{rand_id}@kwdc.com.np", "Gopal Owner", f"+977-9841{rand_id}", "property_owner")
    client_hdrs = get_auth_headers(f"client_lien_{rand_id}@kwdc.com.np", "Himalayan Traders Pvt Ltd", f"+977-9851{rand_id}", "commercial_client")

    # Owner creates warehouse -> Admin approves
    w_res = client.post("/api/warehouses/list-space", headers=owner_hdrs, json={
        "title": f"Chobhar Flex Hub #{rand_id}",
        "space_type": "COVERED_GODOWN",
        "input_value": 10000,
        "input_unit": "sqft",
        "monthly_rate_per_sqft": 40.0,
        "ceiling_height_ft": 18.0,
        "road_access_width_ft": 30.0,
        "municipality": "Kirtipur",
        "district": "Kathmandu"
    })
    assert w_res.status_code == 200, w_res.text
    wh_id = w_res.json()["warehouse_id"]

    app_res = client.post(f"/api/admin/warehouses/{wh_id}/approve", headers=admin_hdrs, json={"approved": True})
    assert app_res.status_code == 200, app_res.text

    # 2. Test 3-Tier Storage Estimate Endpoint
    est_daily = client.get("/api/warehouses/estimate-storage?sqft=1000&monthly_rate_per_sqft=40&booking_duration_type=DAILY&duration_value=3")
    assert est_daily.status_code == 200
    assert est_daily.json()["duration_days"] == 3
    assert est_daily.json()["booking_duration_type"] == "DAILY"

    est_weekly = client.get("/api/warehouses/estimate-storage?sqft=1000&monthly_rate_per_sqft=40&booking_duration_type=WEEKLY&duration_value=2")
    assert est_weekly.status_code == 200
    assert est_weekly.json()["duration_days"] == 14
    assert est_weekly.json()["booking_duration_type"] == "WEEKLY"

    # 3. Client Books DAILY (3 Days) and pays Advance ("Pay First")
    b_daily = client.post("/api/warehouses/book", headers=client_hdrs, json={
        "warehouse_id": wh_id,
        "requested_sqft": 1000.0,
        "booking_duration_type": "DAILY",
        "duration_value": 3,
        "client_intended_use": "Dry Port Transshipment Cross-Dock"
    })
    assert b_daily.status_code == 200, b_daily.text
    daily_data = b_daily.json()
    assert daily_data["duration_days"] == 3
    assert "SHORT-TERM MICRO-STAGING AGREEMENT" in daily_data["contract_text"]
    daily_id = daily_data["booking_id"]

    # Pay advance -> unlocks and activates lease!
    pay_res = client.post(f"/api/warehouses/bookings/{daily_id}/pay-advance", headers=client_hdrs)
    assert pay_res.status_code == 200, pay_res.text
    assert pay_res.json()["advance_payment_status"] == "PAID"
    assert pay_res.json()["status"] == "ACTIVE_LEASED"

    # 4. Client Books MONTHLY (6 Months) & Tests Expand / Downsize / Renew + Contract
    b_monthly = client.post("/api/warehouses/book", headers=client_hdrs, json={
        "warehouse_id": wh_id,
        "requested_sqft": 2000.0,
        "booking_duration_type": "MONTHLY",
        "duration_value": 6,
        "client_intended_use": "Consumer Appliances Inventory",
        "buyer_pan": "601289410"
    })
    assert b_monthly.status_code == 200, b_monthly.text
    m_id = b_monthly.json()["booking_id"]
    assert "60-DAY WAREHOUSEMAN'S LIEN" in b_monthly.json()["contract_text"]

    # Activate Monthly Lease
    act_res = client.post(f"/api/admin/bookings/{m_id}/activate", headers=admin_hdrs)
    assert act_res.status_code == 200, act_res.text

    # Expand +500 sqft, Downsize -200 sqft, Renew +3 months
    exp_res = client.post(f"/api/warehouses/bookings/{m_id}/modify", headers=client_hdrs, json={"action": "EXPAND", "delta_sqft": 500})
    assert exp_res.status_code == 200 and exp_res.json()["allocated_billed_sqft"] == 2500.0
    dn_res = client.post(f"/api/warehouses/bookings/{m_id}/modify", headers=client_hdrs, json={"action": "DOWNSIZE", "delta_sqft": 200})
    assert dn_res.status_code == 200 and dn_res.json()["allocated_billed_sqft"] == 2300.0
    ren_res = client.post(f"/api/warehouses/bookings/{m_id}/modify", headers=client_hdrs, json={"action": "RENEW", "extra_duration_value": 3, "duration_type": "MONTHLY"})
    assert ren_res.status_code == 200

    # Verify contract endpoint
    c_res = client.get(f"/api/warehouses/bookings/{m_id}/contract", headers=client_hdrs)
    assert c_res.status_code == 200
    assert "60-DAY WAREHOUSEMAN'S LIEN" in c_res.json()["contract_text"]

    # 5. Stored Inventory & ISO/IEC 18004 QR Ledger
    inv_add = client.post("/api/warehouses/my-inventory", headers=client_hdrs, json={
        "warehouse_id": wh_id,
        "item_name": "CG Refrigerator 260L",
        "unit_type": "CARTOON",
        "quantity": 40,
        "bay_rack_location": "Zone B / Rack 4"
    })
    assert inv_add.status_code == 200, inv_add.text
    assert inv_add.json()["qr_code_hash"].startswith("ISO18004-")

    inv_get = client.get("/api/warehouses/my-inventory", headers=client_hdrs)
    assert inv_get.status_code == 200
    assert inv_get.json()["summary"]["total_stored_units"] >= 40

    # 6. Saved Consignee Address Book & Corporate KYC
    addr_add = client.post("/api/warehouses/saved-addresses", headers=client_hdrs, json={
        "label": "Kalanki Main Hub",
        "address": "Kalanki Chowk, Ring Road, Kathmandu",
        "contact_name": "Bishnu Pandey",
        "contact_phone": "9841223344"
    })
    assert addr_add.status_code == 200
    addr_id = addr_add.json()["id"]
    assert len(client.get("/api/warehouses/saved-addresses", headers=client_hdrs).json()) >= 1
    assert client.delete(f"/api/warehouses/saved-addresses/{addr_id}", headers=client_hdrs).status_code == 200

    kyc_sub = client.post("/api/auth/submit-kyc", headers=client_hdrs, json={
        "company_reg_number": "OCR-991122/080",
        "company_pan_vat": "601289410",
        "authorized_signatory_name": "Ram Kumar KC"
    })
    assert kyc_sub.status_code == 200
    assert client.get("/api/auth/kyc-profile", headers=client_hdrs).json()["kyc_status"] == "UNDER_REVIEW"

    # 7. 60-Day Overdue Escalation, Gate Freeze & Stock Auction Forfeiture!
    for stage in ["OVERDUE_MONTH_1", "NOTICE_15_DAYS", "NOTICE_7_DAYS", "GATE_FROZEN_5_DAYS"]:
        r = client.post(f"/api/admin/bookings/{m_id}/push-lien-reminder", headers=admin_hdrs, json={"stage": stage})
        assert r.status_code == 200, r.text

    # Verify OUTWARD Gate Pass is BLOCKED while Gate is Frozen (5 Days Left)
    gp_blocked = client.post("/api/incharge/gate-pass", headers=client_hdrs, json={
        "warehouse_id": wh_id,
        "movement_type": "OUTWARD",
        "vehicle_plate": "Ba 2 Kha 9001",
        "driver_name": "Surya Lama",
        "pallet_count": 5
    })
    assert gp_blocked.status_code == 403, f"Expected 403 Gate Frozen, got {gp_blocked.status_code}: {gp_blocked.text}"
    assert "GATE FROZEN" in gp_blocked.json()["detail"]

    # INWARD is still allowed even when Outbound Gate is Frozen!
    gp_inward = client.post("/api/incharge/gate-pass", headers=client_hdrs, json={
        "warehouse_id": wh_id,
        "movement_type": "INWARD",
        "vehicle_plate": "Ba 2 Kha 9001",
        "driver_name": "Surya Lama",
        "pallet_count": 5
    })
    assert gp_inward.status_code == 200
    assert len(client.get("/api/incharge/my-gate-passes", headers=client_hdrs).json()) >= 1

    # Push 48h Final Notice then Day 60 Forfeiture
    assert client.post(f"/api/admin/bookings/{m_id}/push-lien-reminder", headers=admin_hdrs, json={"stage": "FINAL_NOTICE_48_HOURS"}).status_code == 200
    forfeit_res = client.post(f"/api/admin/bookings/{m_id}/push-lien-reminder", headers=admin_hdrs, json={"stage": "FORFEITED_AUCTION"})
    assert forfeit_res.status_code == 200, forfeit_res.text
    f_data = forfeit_res.json()
    assert f_data["is_forfeited"] is True
    assert f_data["auction_lot_number"].startswith("AUC-2083-")

    # Verify lot appears in Admin Auction Ledger and can be marked SOLD
    auc_list = client.get("/api/admin/auctions", headers=admin_hdrs).json()
    lot = next((a for a in auc_list if a["lot_number"] == f_data["auction_lot_number"]), None)
    assert lot is not None
    assert "CG Refrigerator 260L" in lot["item_summary"]

    sold_res = client.post(f"/api/admin/auctions/{lot['id']}/update", headers=admin_hdrs, json={
        "auction_status": "SOLD",
        "winning_bid_npr": 180000.0,
        "buyer_name": "Kathmandu Liquidators"
    })
    assert sold_res.status_code == 200
    assert sold_res.json()["auction_status"] == "SOLD"

    print("\n✅ All Client Lifecycle, 3-Tier Storage, Inventory QR, Gate Freeze & 60-Day Lien Auction Checks Passed!")


if __name__ == "__main__":
    test_client_lifecycle_and_lien_auction()
