"""
Verification Suite for:
1. SMS Sandbox Outbox Dispatch (/api/auth/register, /resend-otp, /forgot-password, /api/admin/sms-outbox)
2. Forgot Password & Reset Password OTP Flow (/api/auth/forgot-password, /api/auth/reset-password)
3. Stock Insurance Premium Payment Proof & Claims Lifecycle
4. Security Agency Roster, Guard Assignment, Perimeter Patrol Logs & Admin License Verify + /security UI
5. Automated Cron Sweep (/api/cron/overdue-sweep) & Holdover Lease Monitoring (/api/admin/holdover-leases)
6. Mobile Endpoint Alignment & Google Maps Tile Check
"""
import glob
import random
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import SessionLocal
from backend.auth_utils import get_password_hash
import backend.models as models

client = TestClient(app)


def _login_admin():
    r = client.post("/api/auth/login", json={"email": "admin@kwdc.com.np", "password": "Admin@123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _create_verified_user(email: str, name: str, phone: str, role: str):
    db = SessionLocal()
    try:
        u = db.query(models.User).filter(models.User.email == email.lower()).first()
        if not u:
            u = models.User(
                full_name=name,
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
        uid = u.id
    finally:
        db.close()

    r = client.post("/api/auth/login", json={"email": email.lower(), "password": "Password@123"})
    assert r.status_code == 200, r.text
    return uid, {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_sms_outbox_and_password_reset():
    rnd = random.randint(10000, 99999)
    reg_email = f"sms_test_{rnd}@kwdc.com.np"
    reg_phone = f"+977-98410{rnd}"
    created_ids = []

    try:
        # 1. Register triggers OTP SMS -> Sandbox Outbox
        r = client.post(
            "/api/auth/register",
            json={
                "full_name": "SMS Audit Client",
                "email": reg_email,
                "phone_number": reg_phone,
                "operating_location": "Kathmandu",
                "role": "commercial_client",
                "password": "OldPassword@123",
                "confirm_password": "OldPassword@123",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["sms_dispatched"] is True
        assert data["sms_provider"] in ("SANDBOX_OUTBOX", "SPARROW_SMS", "TWILIO")

        # Verify via Sandbox Outbox OTP captured in Admin log
        adm_headers = _login_admin()
        outbox_res = client.get("/api/admin/sms-outbox", headers=adm_headers)
        assert outbox_res.status_code == 200, outbox_res.text
        logs = outbox_res.json()["logs"]
        matching = [l for l in logs if l["phone_number"] == reg_phone and l["purpose"] == "OTP"]
        assert len(matching) >= 1
        # Extract 6-digit OTP from SMS message text
        otp_code = [w.strip(".") for w in matching[0]["message"].split() if w.strip(".").isdigit() and len(w.strip(".")) == 6][0]

        v = client.post("/api/auth/verify-otp", json={"email": reg_email, "otp_code": otp_code})
        assert v.status_code == 200, v.text
        assert v.json()["is_verified"] is True

        # 2. Forgot & Reset Password flow
        fp = client.post("/api/auth/forgot-password", json={"email": reg_email})
        assert fp.status_code == 200, fp.text
        assert fp.json()["sms_dispatched"] is True

        outbox_res2 = client.get("/api/admin/sms-outbox", headers=adm_headers)
        pw_logs = [l for l in outbox_res2.json()["logs"] if l["phone_number"] == reg_phone and l["purpose"] == "PASSWORD_RESET"]
        assert len(pw_logs) >= 1
        reset_otp = [w.strip(".") for w in pw_logs[0]["message"].split() if w.strip(".").isdigit() and len(w.strip(".")) == 6][0]

        rp = client.post(
            "/api/auth/reset-password",
            json={
                "email": reg_email,
                "otp_code": reset_otp,
                "new_password": "NewPassword@456",
                "confirm_password": "NewPassword@456",
            },
        )
        assert rp.status_code == 200, rp.text

        login_ok = client.post("/api/auth/login", json={"email": reg_email, "password": "NewPassword@456"})
        assert login_ok.status_code == 200, login_ok.text
        created_ids.append(login_ok.json()["user_id"])
    finally:
        db = SessionLocal()
        try:
            db.query(models.SmsOutboxLog).filter(models.SmsOutboxLog.phone_number == reg_phone).delete()
            if created_ids:
                db.query(models.User).filter(models.User.id.in_(created_ids)).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


def test_insurance_payment_claims_security_cron_and_templates():
    rnd = random.randint(10000, 99999)
    adm_headers = _login_admin()
    owner_id, owner_headers = _create_verified_user(f"ins_own_{rnd}@kwdc.com.np", "Ins Owner", f"98011{rnd}", "property_owner")
    client_id, cli_headers = _create_verified_user(f"ins_cli_{rnd}@kwdc.com.np", "Ins Client", f"98022{rnd}", "commercial_client")
    sec_id, sec_headers = _create_verified_user(f"sec_ag_{rnd}@kwdc.com.np", "Gorkha Sec", f"98033{rnd}", "security_agency")

    wh_id = None
    policy_id = None
    claim_id = None
    agency_id = None
    guard_id = None
    patrol_id = None

    try:
        # 1. Create approved warehouse
        db = SessionLocal()
        wh = models.Warehouse(
            owner_id=owner_id,
            title=f"Security Test Hub {rnd}",
            province="Bagmati",
            district="Kathmandu",
            municipality="Kathmandu Metro",
            neighborhood_landmark="Kalanki",
            latitude=27.6937,
            longitude=85.2816,
            total_sqft=5000,
            available_sqft=5000,
            monthly_rate_per_sqft=30.0,
            is_approved=True,
            is_available=True,
        )
        db.add(wh)
        db.commit()
        db.refresh(wh)
        wh_id = wh.id
        db.close()

        # 2. Insurance request -> Admin bind -> Client pay premium -> File Claim -> Admin settle
        ins_req = client.post(
            "/api/insurance/request",
            headers=cli_headers,
            json={
                "warehouse_id": wh_id,
                "commodity_type": "Electronics",
                "declared_valuation_npr": 1000000,
                "stock_manifest_summary": "100 Cartons LED TVs",
            },
        )
        assert ins_req.status_code == 200, ins_req.text
        policy_id = ins_req.json()["policy_id"]

        proc = client.post(
            f"/api/insurance/admin/{policy_id}/process",
            headers=adm_headers,
            json={"underwriter_name": "Shikhar Insurance Co. Ltd.", "premium_rate_percent": 0.25, "status": "ACTIVE_INSURED"},
        )
        assert proc.status_code == 200, proc.text

        pay = client.post(
            f"/api/insurance/{policy_id}/pay-premium",
            headers=cli_headers,
            json={"payment_method": "BANK_TRANSFER", "payment_ref": f"IPS-{rnd}"},
        )
        assert pay.status_code == 200, pay.text
        assert pay.json()["payment_status"] == "PAID"

        clm = client.post(
            f"/api/insurance/{policy_id}/claim",
            headers=cli_headers,
            json={
                "incident_type": "MONSOON_FLOOD",
                "incident_date": "2026-11-26",
                "claim_amount_npr": 75000,
                "description": "Water seepage damaged 5 bottom cartons",
            },
        )
        assert clm.status_code == 200, clm.text
        claim_id = clm.json()["claim_id"]

        my_clms = client.get("/api/insurance/my-claims", headers=cli_headers)
        assert my_clms.status_code == 200
        assert any(c["id"] == claim_id for c in my_clms.json())

        adm_clm = client.post(
            f"/api/insurance/admin/claims/{claim_id}/process",
            headers=adm_headers,
            json={"status": "APPROVED", "approved_payout_npr": 65000, "admin_notes": "Surveyor verified"},
        )
        assert adm_clm.status_code == 200, adm_clm.text
        assert adm_clm.json()["approved_payout_npr"] == 65000

        # 3. Security Agency profile, SuperAdmin license verify, Guard create/assign, Patrol Log
        ag = client.post(
            "/api/security/agency-profile",
            headers=sec_headers,
            json={
                "agency_name": f"Himalayan Watch {rnd}",
                "home_ministry_license_no": f"MOHA-{rnd}",
                "emergency_contact_phone": "+977-9801009988",
            },
        )
        assert ag.status_code == 200, ag.text
        agency_id = ag.json()["agency_id"]

        ver = client.post(
            f"/api/admin/security-agencies/{agency_id}/verify",
            headers=adm_headers,
            json={"approve": True},
        )
        assert ver.status_code == 200 and ver.json()["is_verified"] is True

        grd = client.post(
            "/api/security/guards",
            headers=sec_headers,
            json={"guard_name": "Bahadur Magar", "phone_number": f"98490{rnd}", "assigned_warehouse_id": wh_id, "shift_type": "NIGHT"},
        )
        assert grd.status_code == 200, grd.text
        guard_id = grd.json()["guard_id"]

        pat = client.post(
            "/api/security/patrol-log",
            headers=sec_headers,
            json={"warehouse_id": wh_id, "guard_id": guard_id, "shift_type": "NIGHT", "perimeter_status": "ALL_CLEAR", "notes": "Gates locked"},
        )
        assert pat.status_code == 200, pat.text
        patrol_id = pat.json()["patrol_id"]

        sec_dash = client.get("/api/security/dashboard", headers=sec_headers)
        assert sec_dash.status_code == 200
        assert len(sec_dash.json()["guards"]) >= 1
        assert len(sec_dash.json()["patrol_logs"]) >= 1

        # 4. Cron sweep + Holdover endpoint + /security template UI compliance
        cron = client.get("/api/cron/overdue-sweep")
        assert cron.status_code == 200 and cron.json()["status"] == "completed"

        holdovers = client.get("/api/admin/holdover-leases", headers=adm_headers)
        assert holdovers.status_code == 200

        sec_html = client.get("/security")
        assert sec_html.status_code == 200
        for marker in ("toggleLanguage", "DICTIONARY", "langBtn"):
            assert marker in sec_html.text

        # 5. Ensure OpenStreetMap tiles are replaced and Incharge Mobile API bug is fixed
        for tpl in glob.glob("frontend/templates/**/*.html", recursive=True) + glob.glob("frontend/templates/*.html"):
            with open(tpl, "r", encoding="utf-8") as fh:
                content = fh.read()
            assert "tile.openstreetmap.org" not in content, f"Leftover OSM tile URL in {tpl}"

        with open("mobile/src/screens/InchargeHomeScreen.js", "r", encoding="utf-8") as mf:
            m_src = mf.read()
        assert "/api/incharge/my-warehouses" not in m_src
        assert "/api/incharge/assigned-warehouses" in m_src
    finally:
        db = SessionLocal()
        try:
            if patrol_id:
                db.query(models.SecurityPatrolLog).filter(models.SecurityPatrolLog.id == patrol_id).delete()
            if guard_id:
                db.query(models.GuardPersonnel).filter(models.GuardPersonnel.id == guard_id).delete()
            if agency_id:
                db.query(models.SecurityAgency).filter(models.SecurityAgency.id == agency_id).delete()
            if claim_id:
                db.query(models.InsuranceClaim).filter(models.InsuranceClaim.id == claim_id).delete()
            if policy_id:
                db.query(models.StockInsurancePolicy).filter(models.StockInsurancePolicy.id == policy_id).delete()
            if wh_id:
                db.query(models.Warehouse).filter(models.Warehouse.id == wh_id).delete()
            db.query(models.User).filter(models.User.id.in_([owner_id, client_id, sec_id])).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    test_sms_outbox_and_password_reset()
    print("[PASS] SMS Outbox & Password Reset tests")
    test_insurance_payment_claims_security_cron_and_templates()
    print("[PASS] Insurance Claims, Security Agency, Cron Sweep & Mobile API Parity tests")
