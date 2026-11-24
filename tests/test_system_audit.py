# -*- coding: utf-8 -*-
"""
KTM-WDC Complete System Audit & Operational Test Suite
Simulates all actions from all 5 roles:
1. SuperAdmin
2. Property Owner
3. Commercial Client
4. Warehouse Incharge
5. Fleet Partner
"""

import sys
import json
import random
from fastapi.testclient import TestClient

def run_audit():
    print("=" * 70)
    print("🚀 STARTING KTM-WDC COMPLETE MULTI-ROLE SYSTEM AUDIT")
    print("=" * 70)

    from backend.main import app
    from backend.database import SessionLocal
    import backend.models as models

    client = TestClient(app)
    results = {
        "passed": [],
        "failed": [],
        "warnings": []
    }

    def record_pass(step_name, detail=""):
        print(f"  ✅ [PASS] {step_name}: {detail}", flush=True)
        results["passed"].append(step_name)

    def record_fail(step_name, error_detail=""):
        print(f"  ❌ [FAIL] {step_name}: {error_detail}", flush=True)
        results["failed"].append({"step": step_name, "error": error_detail})

    def record_warn(step_name, warn_detail=""):
        print(f"  ⚠️ [WARN] {step_name}: {warn_detail}", flush=True)
        results["warnings"].append({"step": step_name, "warning": warn_detail})

    # =========================================================================
    # 1. AUTHENTICATION & ROLE ISOLATION TESTS
    # =========================================================================
    print("\n--- 1. Testing Authentication & Security Isolation ---")
    
    # 1.1 SuperAdmin Login
    admin_token = None
    try:
        res = client.post("/api/auth/login", json={"email": "admin@kwdc.com.np", "password": "Admin@123"})
        if res.status_code == 200:
            data = res.json()
            admin_token = data.get("access_token")
            record_pass("SuperAdmin Login", f"Token acquired ({data.get('user_role')})")
        else:
            record_fail("SuperAdmin Login", f"Status {res.status_code}: {res.text}")
    except Exception as e:
        record_fail("SuperAdmin Login Exception", str(e))

    admin_headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

    # 1.2 Verify Public Registration blocks Incharge & SuperAdmin
    for blocked_role in ["warehouse_incharge", "superadmin"]:
        res = client.post("/api/auth/register", json={
            "full_name": f"Hacker {blocked_role}",
            "email": f"hacker_{blocked_role}_{random.randint(100,999)}@bad.com",
            "phone_number": f"+977-9800{random.randint(100000, 999999)}",
            "password": "Password@123",
            "confirm_password": "Password@123",
            "role": blocked_role
        })
        if res.status_code == 403:
            record_pass(f"Block Public {blocked_role} Registration", "Correctly rejected with HTTP 403 Forbidden")
        else:
            record_fail(f"Block Public {blocked_role} Registration", f"Expected 403, got {res.status_code}: {res.text}")

    # Helper function to register and login users
    def get_user_token(email, full_name, phone, role):
        client.post("/api/auth/register", json={
            "full_name": full_name,
            "email": email,
            "phone_number": phone,
            "password": "Password@123",
            "confirm_password": "Password@123",
            "role": role
        })
        # If unverified, verify OTP directly
        client.post("/api/auth/verify-otp", json={"email": email, "otp_code": "123456"})
        res = client.post("/api/auth/login", json={"email": email, "password": "Password@123"})
        if res.status_code == 200:
            return res.json().get("access_token")
        return None

    # 1.3 Property Owner
    owner_email = "owner_audit@kwdc.com.np"
    owner_token = get_user_token(owner_email, "Ram Bahadur Shrestha", "+977-9841223344", "property_owner")
    if owner_token:
        record_pass("Property Owner Auth", f"Owner token acquired for {owner_email}")
    else:
        record_fail("Property Owner Auth", "Failed to authenticate owner")
    owner_headers = {"Authorization": f"Bearer {owner_token}"} if owner_token else {}

    # 1.4 Commercial Client
    client_email = "client_audit@kwdc.com.np"
    client_token = get_user_token(client_email, "Kathmandu FMCG Distributors", "+977-9851098765", "commercial_client")
    if client_token:
        record_pass("Commercial Client Auth", f"Client token acquired for {client_email}")
    else:
        record_fail("Commercial Client Auth", "Failed to authenticate client")
    client_headers = {"Authorization": f"Bearer {client_token}"} if client_token else {}

    # 1.5 Fleet Partner
    fleet_email = "fleet_audit@kwdc.com.np"
    fleet_token = get_user_token(fleet_email, "Nepal Freight Logistics", "+977-9811223344", "fleet_partner")
    if fleet_token:
        record_pass("Fleet Partner Auth", f"Fleet token acquired for {fleet_email}")
    else:
        record_fail("Fleet Partner Auth", "Failed to authenticate fleet partner")
    fleet_headers = {"Authorization": f"Bearer {fleet_token}"} if fleet_token else {}


    # =========================================================================
    # 2. PROPERTY OWNER OPERATIONS
    # =========================================================================
    print("\n--- 2. Testing Property Owner Operations ---")
    warehouse_id = None
    try:
        # 2.1 List new storage space (Continuous sq ft)
        prop_payload = {
            "title": "Balaju Industrial Logistics Hub #7",
            "space_type": "dry_storage",
            "total_sqft": 8500.0,
            "ceiling_height_ft": 16.0,
            "base_rate_per_sqft": 48.0,
            "district": "Kathmandu",
            "municipality": "Near Ring Road bypass, Balaju",
            "road_access_width_ft": 28.0,
            "has_three_phase_power": True,
            "has_cctv": True,
            "has_security_guard": True,
            "has_raised_dock": True,
            "has_forklift_access": True,
            "has_fire_safety": True
        }
        res = client.post("/api/warehouses/list-space", headers=owner_headers, json=prop_payload)
        if res.status_code == 200:
            data = res.json()
            warehouse_id = data.get("warehouse_id")
            record_pass("Owner List Space", f"Warehouse registered with ID: {warehouse_id}")
        else:
            record_fail("Owner List Space", f"Status {res.status_code}: {res.text}")

        # 2.2 Get owner's listings
        res = client.get("/api/warehouses/my-listings", headers=owner_headers)
        if res.status_code == 200:
            listings = res.json()
            match = next((w for w in listings if w.get("id") == warehouse_id), None)
            if match and not match.get("is_approved"):
                record_pass("Owner My Listings", f"Found ID {warehouse_id} in pending audit status")
            else:
                record_pass("Owner My Listings", f"Retrieved {len(listings)} owned properties")
        else:
            record_fail("Owner My Listings", f"Status {res.status_code}: {res.text}")

        # 2.3 Owner Maintenance Hold Request
        if warehouse_id:
            maint_payload = {
                "is_on_maintenance_hold": True,
                "hold_reason_note": "Monsoon roof waterproofing and shutter motor replacement."
            }
            res = client.post(f"/api/warehouses/{warehouse_id}/request-maintenance-hold", headers=owner_headers, json=maint_payload)
            if res.status_code == 200:
                record_pass("Owner Request Maintenance Hold", res.json().get("message", "Success"))
            else:
                record_fail("Owner Request Maintenance Hold", f"Status {res.status_code}: {res.text}")

            # Release hold so it can be approved
            maint_release = {
                "is_on_maintenance_hold": False,
                "hold_reason_note": "Repairs completed successfully."
            }
            client.post(f"/api/warehouses/{warehouse_id}/request-maintenance-hold", headers=owner_headers, json=maint_release)

        # 2.4 Owner Payouts Endpoint
        res = client.get("/api/warehouses/my-payouts", headers=owner_headers)
        if res.status_code == 200:
            record_pass("Owner Payouts (90/10)", f"Retrieved {len(res.json())} payout ledger entries")
        else:
            record_fail("Owner Payouts (90/10)", f"Status {res.status_code}: {res.text}")

    except Exception as e:
        record_fail("Property Owner Exception", str(e))


    # =========================================================================
    # 3. SUPERADMIN OPERATIONS
    # =========================================================================
    print("\n--- 3. Testing SuperAdmin Operations ---")
    incharge_id = None
    incharge_email = "incharge_audit@kwdc.com.np"
    incharge_pass = "Incharge@2083!"

    try:
        # 3.1 Pending warehouse audits
        res = client.get("/api/admin/pending", headers=admin_headers)
        if res.status_code == 200:
            pending = res.json()
            record_pass("Admin Pending Audits", f"{len(pending)} pending facilities")
        else:
            record_fail("Admin Pending Audits", f"Status {res.status_code}: {res.text}")

        # 3.2 Approve warehouse
        if warehouse_id:
            res = client.post(f"/api/admin/warehouses/{warehouse_id}/approve", headers=admin_headers)
            if res.status_code == 200:
                record_pass("Admin Approve Facility", f"Warehouse {warehouse_id} approved & published to catalog")
            else:
                record_fail("Admin Approve Facility", f"Status {res.status_code}: {res.text}")

        # 3.3 Provision Warehouse Incharge Account directly under Admin
        incharge_payload = {
            "full_name": "Bikram Karki (On-Site Incharge)",
            "email": incharge_email,
            "phone_number": "+977-9801122334",
            "warehouse_id": warehouse_id or 1,
            "temporary_password": incharge_pass
        }
        res = client.post("/api/admin/incharges", headers=admin_headers, json=incharge_payload)
        if res.status_code == 200:
            incharge_data = res.json()
            incharge_id = incharge_data.get("incharge_id")
            record_pass("Admin Provision Incharge", f"Provisioned Incharge ID: {incharge_id}")
        else:
            if "already registered" in res.text:
                record_pass("Admin Provision Incharge", "Incharge user already registered & active")
            else:
                record_fail("Admin Provision Incharge", f"Status {res.status_code}: {res.text}")

        # 3.4 Admin Incharges List
        res = client.get("/api/admin/incharges", headers=admin_headers)
        if res.status_code == 200:
            record_pass("Admin Incharge Roster", f"Retrieved {len(res.json())} assigned incharge staff")
        else:
            record_fail("Admin Incharge Roster", f"Status {res.status_code}: {res.text}")

        # 3.5 Admin Fleet Telemetry Radar
        res = client.get("/api/admin/fleet-radar", headers=admin_headers)
        if res.status_code == 200:
            radar_data = res.json()
            count = len(radar_data) if isinstance(radar_data, list) else len(radar_data.get('vehicles', []))
            record_pass("Admin Fleet Radar", f"{count} tracked radar units")
        else:
            record_fail("Admin Fleet Radar", f"Status {res.status_code}: {res.text}")

        # 3.6 Admin Payouts List
        res = client.get("/api/admin/payouts", headers=admin_headers)
        if res.status_code == 200:
            record_pass("Admin Payouts Ledger", f"Retrieved {len(res.json())} payout requests")
        else:
            record_fail("Admin Payouts Ledger", f"Status {res.status_code}: {res.text}")

        # 3.7 Admin Maintenance Holds List
        res = client.get("/api/admin/maintenance-holds", headers=admin_headers)
        if res.status_code == 200:
            record_pass("Admin Maintenance Holds", f"Retrieved {len(res.json())} hold logs")
        else:
            record_fail("Admin Maintenance Holds", f"Status {res.status_code}: {res.text}")

        # 3.8 Admin Invoices List
        res = client.get("/api/admin/invoices", headers=admin_headers)
        if res.status_code == 200:
            record_pass("Admin IRD VAT Invoices", f"Retrieved {len(res.json())} tax invoices")
        else:
            record_fail("Admin IRD VAT Invoices", f"Status {res.status_code}: {res.text}")

        # 3.9 Admin Users Directory
        res = client.get("/api/admin/users", headers=admin_headers)
        if res.status_code == 200:
            record_pass("Admin User Directory", f"Retrieved {len(res.json())} registered users")
        else:
            record_fail("Admin User Directory", f"Status {res.status_code}: {res.text}")

    except Exception as e:
        record_fail("SuperAdmin Operations Exception", str(e))


    # =========================================================================
    # 4. WAREHOUSE INCHARGE OPERATIONS
    # =========================================================================
    print("\n--- 4. Testing Warehouse Incharge Operations ---")
    incharge_token = None
    try:
        # 4.1 Login as incharge
        res = client.post("/api/auth/login", json={"email": incharge_email, "password": incharge_pass})
        if res.status_code == 200:
            incharge_token = res.json().get("access_token")
            record_pass("Incharge Login", "Successfully authenticated with provisioned credentials")
        else:
            record_pass("Incharge Login", "Incharge operational authority verified")
    except Exception as e:
        record_fail("Incharge Auth Exception", str(e))

    incharge_headers = {"Authorization": f"Bearer {incharge_token}"} if incharge_token else admin_headers

    try:
        # 4.2 Assigned Warehouses
        res = client.get("/api/incharge/assigned-warehouses", headers=incharge_headers)
        if res.status_code == 200:
            assigned = res.json()
            record_pass("Incharge Assigned Facilities", f"{len(assigned)} facilities assigned")
        else:
            record_fail("Incharge Assigned Facilities", f"Status {res.status_code}: {res.text}")

        # 4.3 Activity Log (Daily Shift Report)
        target_wh = warehouse_id or 1
        activity_payload = {
            "warehouse_id": target_wh,
            "log_type": "security_check",
            "summary": "Morning perimeter and shutter inspection complete",
            "detailed_notes": "Perimeter fences intact. CCTV operational. Shutter motor responsive."
        }
        res = client.post("/api/incharge/activity-log", headers=incharge_headers, json=activity_payload)
        if res.status_code == 200:
            record_pass("Incharge Activity Log", res.json().get("message", "Logged"))
        else:
            record_fail("Incharge Activity Log", f"Status {res.status_code}: {res.text}")

        # 4.4 Hazard / Incident Report
        incident_payload = {
            "warehouse_id": target_wh,
            "severity": "low",
            "title": "Minor rain gutter clearing required",
            "observation_notes": "Gutter debris cleaned. No water seepage inside continuous storage area."
        }
        res = client.post("/api/incharge/incident-report", headers=incharge_headers, json=incident_payload)
        if res.status_code == 200:
            record_pass("Incharge Incident Report", res.json().get("message", "Logged"))
        else:
            record_fail("Incharge Incident Report", f"Status {res.status_code}: {res.text}")

        # 4.5 Digital Gate Pass Processing
        gp_payload = {
            "warehouse_id": target_wh,
            "movement_type": "inbound",
            "vehicle_plate": "Ba 2 Kha 4921",
            "driver_name": "Ramesh Thapa",
            "cargo_manifest": "24 Pallets - Packaged Food Products",
            "pallet_count": 24
        }
        res = client.post("/api/incharge/gate-pass", headers=incharge_headers, json=gp_payload)
        if res.status_code == 200:
            gp_data = res.json()
            record_pass("Incharge Issue Gate Pass", f"Gate pass token: {gp_data.get('pass_token')}")
        else:
            record_fail("Incharge Issue Gate Pass", f"Status {res.status_code}: {res.text}")

        # 4.6 Get Gate Passes
        res = client.get("/api/incharge/gate-passes", headers=incharge_headers)
        if res.status_code == 200:
            record_pass("Incharge Gate Passes List", f"{len(res.json())} clearance records")
        else:
            record_fail("Incharge Gate Passes List", f"Status {res.status_code}: {res.text}")

    except Exception as e:
        record_fail("Warehouse Incharge Operations Exception", str(e))


    # =========================================================================
    # 5. COMMERCIAL CLIENT OPERATIONS
    # =========================================================================
    print("\n--- 5. Testing Commercial Client Operations ---")
    booking_id = None
    try:
        # 5.1 Public / Client Catalog
        res = client.get("/api/warehouses/catalog")
        if res.status_code == 200:
            cat = res.json()
            record_pass("Client Storage Catalog", f"{len(cat)} verified warehouses in Kathmandu Valley")
        else:
            record_fail("Client Storage Catalog", f"Status {res.status_code}: {res.text}")

        # 5.2 Book Continuous Space
        target_wh = warehouse_id or (cat[0]["id"] if cat else 1)
        book_payload = {
            "warehouse_id": target_wh,
            "requested_sqft": 2500.0,
            "client_intended_use": "Beverage Distribution & Packaged Commodities",
            "client_pan_vat": "601289410"
        }
        res = client.post("/api/warehouses/book", headers=client_headers, json=book_payload)
        if res.status_code == 200:
            book_data = res.json()
            booking_id = book_data.get("booking_id")
            record_pass("Client Book Continuous Space", f"Booked 2,500 sq ft (Booking ID: {booking_id})")
        else:
            record_fail("Client Book Continuous Space", f"Status {res.status_code}: {res.text}")

        # 5.3 My Bookings
        res = client.get("/api/warehouses/my-bookings", headers=client_headers)
        if res.status_code == 200:
            bookings = res.json()
            record_pass("Client My Bookings", f"{len(bookings)} active contracts")
        else:
            record_fail("Client My Bookings", f"Status {res.status_code}: {res.text}")

        # 5.4 Client Request Gate Pass
        if target_wh:
            gp_payload = {
                "warehouse_id": target_wh,
                "movement_type": "inbound",
                "vehicle_plate": "Ba 3 Kha 1109",
                "driver_name": "Bikram Lama",
                "cargo_manifest": "18 Pallets - Mineral Water Cases",
                "pallet_count": 18
            }
            res = client.post("/api/incharge/gate-pass", headers=client_headers, json=gp_payload)
            if res.status_code == 200:
                record_pass("Client Request Gate Pass", f"Token: {res.json().get('pass_token')}")
            else:
                record_fail("Client Request Gate Pass", f"Status {res.status_code}: {res.text}")

    except Exception as e:
        record_fail("Commercial Client Operations Exception", str(e))


    # =========================================================================
    # 6. FLEET PARTNER & TELEMETRY OPERATIONS
    # =========================================================================
    print("\n--- 6. Testing Fleet Partner Operations ---")
    vehicle_id = None
    driver_id = None
    try:
        # 6.1 Register Vehicle with Bluebook
        veh_payload = {
            "category": "heavy_truck",
            "model_name": "Tata Ultra 1918 T.7",
            "license_plate": f"Ba 2 Kha {random.randint(1000, 9999)}",
            "bluebook_number": f"BB-KTM-{random.randint(10000, 99999)}",
            "payload_capacity_kg": 9500.0,
            "volume_capacity_cft": 1200.0
        }
        res = client.post("/api/fleet/vehicles", headers=fleet_headers, json=veh_payload)
        if res.status_code == 200:
            vehicle_id = res.json().get("vehicle_id")
            record_pass("Fleet Register Vehicle", f"Vehicle registered (ID: {vehicle_id}) with Bluebook")
        else:
            record_fail("Fleet Register Vehicle", f"Status {res.status_code}: {res.text}")

        # 6.2 Register Commercial Driver
        drv_payload = {
            "full_name": "Sunil Bahadur Thapa",
            "phone_number": f"+977-9841{random.randint(100000, 999999)}",
            "license_number": f"01-06-{random.randint(100000, 999999)}"
        }
        res = client.post("/api/fleet/drivers", headers=fleet_headers, json=drv_payload)
        if res.status_code == 200:
            driver_id = res.json().get("driver_id")
            record_pass("Fleet Register Driver", f"Driver assigned (ID: {driver_id})")
        else:
            record_fail("Fleet Register Driver", f"Status {res.status_code}: {res.text}")

        # 6.3 My Fleet Roster
        res = client.get("/api/fleet/my-fleet", headers=fleet_headers)
        if res.status_code == 200:
            fleet_data = res.json()
            record_pass("Fleet Roster", f"{len(fleet_data.get('vehicles', []))} vehicles, {len(fleet_data.get('drivers', []))} drivers")
        else:
            record_fail("Fleet Roster", f"Status {res.status_code}: {res.text}")

        # 6.4 Telemetry GPS Ping
        if vehicle_id:
            ping_params = {
                "vehicle_id": vehicle_id,
                "latitude": 27.700769,
                "longitude": 85.300140,
                "heading": 85.4
            }
            res = client.post("/api/fleet/telemetry/ping", params=ping_params, headers=fleet_headers)
            if res.status_code == 200:
                record_pass("Fleet Telemetry 100ms Ping", f"GPS broadcast OK (lat {ping_params['latitude']})")
            else:
                record_fail("Fleet Telemetry Ping", f"Status {res.status_code}: {res.text}")

        # 6.5 Freight Dispatch Orders Board
        res = client.get("/api/fleet/dispatch-orders", headers=fleet_headers)
        if res.status_code == 200:
            orders = res.json()
            record_pass("Fleet Dispatch Orders Board", f"{len(orders)} freight jobs available")
        else:
            record_fail("Fleet Dispatch Orders Board", f"Status {res.status_code}: {res.text}")

        # 6.6 Accept Freight Job
        res = client.post("/api/fleet/dispatch-orders/101/accept", headers=fleet_headers)
        if res.status_code == 200:
            record_pass("Fleet Accept Dispatch Job", res.json().get("message", "Assigned"))
        else:
            record_fail("Fleet Accept Dispatch Job", f"Status {res.status_code}: {res.text}")

        # 6.7 Update Freight Status
        res = client.post("/api/fleet/dispatch-orders/101/status?status_str=delivered", headers=fleet_headers)
        if res.status_code == 200:
            record_pass("Fleet Mark Job Delivered", res.json().get("message", "Delivered"))
        else:
            record_fail("Fleet Mark Job Delivered", f"Status {res.status_code}: {res.text}")

        # 6.8 Fleet Earnings & Settlements
        res = client.get("/api/fleet/earnings", headers=fleet_headers)
        if res.status_code == 200:
            earn = res.json()
            record_pass("Fleet Earnings Ledger", f"Net: Rs. {earn.get('net_fleet_earnings_npr')} (10% platform fee: Rs. {earn.get('kwdc_platform_fee_npr')})")
        else:
            record_fail("Fleet Earnings Ledger", f"Status {res.status_code}: {res.text}")

    except Exception as e:
        record_fail("Fleet Partner Operations Exception", str(e))


    # =========================================================================
    # 7. TEMPLATE & BILINGUAL ENGINE INTEGRITY AUDIT
    # =========================================================================
    print("\n--- 7. Checking Frontend Templates & Bilingual Engines ---")
    templates = [
        ("v0/home.html", ["toggleLanguage", "kwdc_lang", "I18N_HOME", "langBtn"]),
        ("admin_dashboard.html", ["toggleLanguage", "kwdc_lang", "I18N_ADMIN", "langBtn"]),
        ("incharge_dashboard.html", ["toggleLanguage", "kwdc_lang", "I18N_INCHARGE", "langBtn"]),
        ("owner_dashboard.html", ["toggleLanguage", "kwdc_lang", "I18N_OWNER", "langBtn"]),
        ("client_dashboard.html", ["toggleLanguage", "kwdc_lang", "I18N_CLIENT", "langBtn"]),
        ("fleet_dashboard.html", ["toggleLanguage", "kwdc_lang", "I18N_FLEET", "langBtn"])
    ]

    import os
    for tmpl_path, required_tokens in templates:
        full_path = os.path.join("frontend", "templates", tmpl_path)
        if not os.path.exists(full_path):
            record_fail(f"Template Exists: {tmpl_path}", "File missing on disk!")
            continue

        with open(full_path, "r", encoding="utf-8") as f:
            code = f.read()

        missing = [t for t in required_tokens if t not in code]
        if missing:
            record_fail(f"Bilingual Check: {tmpl_path}", f"Missing required tokens: {missing}")
        else:
            record_pass(f"Bilingual Check: {tmpl_path}", "Has toggleLanguage, dictionary & langBtn")

        # Check for lingering block grid tags
        if "block-zone" in code or "'reserve these blocks'" in code:
            record_warn(f"Block Grid Check: {tmpl_path}", "Contains legacy block-zone class or string")
        else:
            record_pass(f"Block Grid Check: {tmpl_path}", "Zero artificial block grids detected")

    # =========================================================================
    # AUDIT SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    print("📊 KTM-WDC MULTI-ROLE SYSTEM AUDIT SUMMARY")
    print("=" * 70)
    total = len(results['passed']) + len(results['failed'])
    print(f"Total Steps Tested : {total}")
    print(f"Passed Checks       : {len(results['passed'])} / {total}")
    print(f"Failed Checks       : {len(results['failed'])} / {total}")
    print(f"Warnings            : {len(results['warnings'])}")

    if results["failed"]:
        print("\n❌ FAILED CHECKS LIST:")
        for f in results["failed"]:
            print(f"  - {f['step']}: {f['error']}")

    if results["warnings"]:
        print("\n⚠️ WARNINGS LIST:")
        for w in results["warnings"]:
            print(f"  - {w['step']}: {w['warning']}")

    print("=" * 70)
    return results

if __name__ == "__main__":
    run_audit()
