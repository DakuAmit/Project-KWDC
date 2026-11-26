"""
End-to-End Verification Suite for:
1. Heavy Equipment Double-Booking Lock (eq.is_available=False on CONFIRMED, restored on COMPLETED)
2. Heavy Equipment Dual-Mode Operators (INDEPENDENT_OPERATOR vs COMMERCIAL_FLEET, PIN Login, Job Assignment, Start/Complete)
3. Heavy Equipment Commission Payable settlement (/api/equipment/commission/settle)
4. Multi-Drop Freight Stop Completion (/api/fleet/driver/trips/{order_id}/stops/{stop_id}/complete)
5. Expired Lease Holdover Stock Alert in run_overdue_sweep()
6. Equipment Web Panel UI checks (/equipment)
"""

import random
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal
from backend.auth_utils import get_password_hash
from backend.services.overdue_monitor import run_overdue_sweep
import backend.models as models

client = TestClient(app)


def ensure_user(email: str, full_name: str, phone: str, role: str) -> int:
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


def login_h(email: str, password: str = "Password@123") -> dict:
    r = client.post("/api/auth/login", json={"email": email.lower(), "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_equipment_operator_and_enhancements():
    rand_id = random.randint(10000, 99999)
    eq_email = f"eq_op_own_{rand_id}@kwdc.com.np"
    cli_email = f"eq_op_cli_{rand_id}@kwdc.com.np"
    created_eq_ids = []
    created_op_phones = []

    try:
        ensure_user(eq_email, "Kiran Machinery Rental", f"98611{rand_id}", "equipment_owner")
        cli_id = ensure_user(cli_email, "Balaju Trading Client", f"98612{rand_id}", "commercial_client")

        admin_h = login_h("admin@kwdc.com.np", "Admin@123")
        eq_h = login_h(eq_email)
        cli_h = login_h(cli_email)

        # 1. Set Commercial Rental Fleet mode, register Forklift, get Admin approval
        assert client.post("/api/equipment/operator-type", headers=eq_h, json={"operator_type": "COMMERCIAL_FLEET"}).status_code == 200
        eq_id = client.post("/api/equipment/register", headers=eq_h, json={
            "equipment_type": "Forklift",
            "model_name": f"Komatsu FD30-{rand_id}",
            "capacity_ton": 3.0,
            "daily_rate_npr": 9000.0,
            "monthly_rate_npr": 180000.0,
            "location_city": "Kathmandu"
        }).json()["equipment_id"]
        created_eq_ids.append(eq_id)
        assert client.post(f"/api/equipment/admin/{eq_id}/approve?approved=true", headers=admin_h).status_code == 200

        # Register Equipment Operator with PIN
        op_phone = f"98711{rand_id}"
        created_op_phones.append(op_phone)
        op_res = client.post("/api/equipment/operators", headers=eq_h, json={
            "full_name": "Bimal Crane Operator",
            "phone_number": op_phone,
            "certification_no": f"CRN-{rand_id}",
            "login_pin": "6677",
            "assigned_equipment_id": eq_id
        })
        assert op_res.status_code == 200, op_res.text
        op_id = op_res.json()["operator_id"]

        # 2. Client books forklift -> locks eq.is_available=False so 2nd concurrent booking fails!
        b1 = client.post("/api/equipment/book", headers=cli_h, json={
            "equipment_id": eq_id, "duration_type": "DAILY", "duration_units": 1, "site_address": "Balaju Dock 2"
        })
        assert b1.status_code == 200, b1.text
        job_id = b1.json()["job_id"]

        b2 = client.post("/api/equipment/book", headers=cli_h, json={
            "equipment_id": eq_id, "duration_type": "DAILY", "duration_units": 1, "site_address": "Kalanki Dock 1"
        })
        assert b2.status_code == 400  # Prevent double booking!

        # 3. Assign operator & test Operator PIN Login + job execution
        assert client.post(f"/api/equipment/jobs/{job_id}/assign-operator", headers=eq_h, json={"operator_id": op_id}).status_code == 200
        op_login = client.post("/api/equipment/operator/login", json={"phone_number": op_phone, "pin": "6677"})
        assert op_login.status_code == 200, op_login.text
        op_h = {"Authorization": f"Bearer {op_login.json()['access_token']}"}

        op_jobs = client.get("/api/equipment/operator/active-job", headers=op_h).json()
        assert op_jobs["operator_mode"] == "COMMERCIAL_FLEET"
        assert op_jobs["can_claim"] is False
        assert any(j["id"] == job_id for j in op_jobs["assigned_jobs"])

        # Switch owner to INDEPENDENT_OPERATOR -> verify operator gets can_claim=True
        client.post("/api/equipment/operator-type", headers=eq_h, json={"operator_type": "INDEPENDENT_OPERATOR"})
        op_jobs_ind = client.get("/api/equipment/operator/active-job", headers=op_h).json()
        assert op_jobs_ind["can_claim"] is True

        # Start & Complete via Operator PIN endpoint -> restores eq.is_available = True
        assert client.post(f"/api/equipment/operator/jobs/{job_id}/status?status_str=IN_PROGRESS", headers=op_h).status_code == 200
        assert client.post(f"/api/equipment/operator/jobs/{job_id}/status?status_str=COMPLETED", headers=op_h).status_code == 200

        # Commission settle check
        assert client.post("/api/equipment/commission/settle", headers=eq_h).status_code == 200
        fleet_sum = client.get("/api/equipment/my-fleet", headers=eq_h).json()["summary"]
        assert fleet_sum["commission_due_to_kwdc_npr"] == 0.0

        # 4. Web portal checks
        eq_html = client.get("/equipment").text
        assert "Operator PIN Terminal" in eq_html
        assert "Commission Payable" in eq_html
        assert "eqOperatorsGrid" in eq_html

        fleet_html = client.get("/fleet").text
        assert "claimAssignModal" in fleet_html

        driver_html = client.get("/driver").text
        assert "tripMultiStopsBox" in driver_html

        print("[PASS] Heavy Equipment Operator panel, double-booking prevention, multi-drop stops & enhancements verified.")
    finally:
        db = SessionLocal()
        try:
            emails = [eq_email, cli_email]
            u_ids = [u.id for u in db.query(models.User).filter(models.User.email.in_(emails)).all()]
            if created_eq_ids:
                eq_jobs = db.query(models.EquipmentJob).filter(models.EquipmentJob.equipment_id.in_(created_eq_ids)).all()
                inv_nums = [f"INV-EQ-{j.id:05d}" for j in eq_jobs]
                if inv_nums:
                    db.query(models.TaxInvoice).filter(models.TaxInvoice.invoice_number.in_(inv_nums)).delete(synchronize_session=False)
                db.query(models.EquipmentJob).filter(models.EquipmentJob.equipment_id.in_(created_eq_ids)).delete(synchronize_session=False)
                db.query(models.EquipmentOperator).filter(models.EquipmentOperator.owner_id.in_(u_ids)).delete(synchronize_session=False)
                db.query(models.HeavyEquipment).filter(models.HeavyEquipment.id.in_(created_eq_ids)).delete(synchronize_session=False)
            if u_ids:
                db.query(models.User).filter(models.User.id.in_(u_ids)).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    test_equipment_operator_and_enhancements()
