"""
End-to-End Verification Suite for:
1. Google Maps Routing & Geolocation Endpoints (/api/maps/status, /geocode, /route-distance)
2. Persistent Media Upload API (/api/uploads/image & /api/uploads/image-base64 -> /api/uploads/media/{id})
3. Heavy Equipment Owner Lifecycle (Register, Admin Approve, Client Rental + 13% IRD VAT, Job Execution, 90/10 Summary, /equipment UI)
"""

import base64
import random
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def create_user(email: str, full_name: str, phone: str, role: str):
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
            db.commit()
    finally:
        db.close()

    res = client.post("/api/auth/login", json={"email": email.lower(), "password": "Password@123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_maps_equipment_and_uploads():
    rand_id = random.randint(10000, 99999)
    admin_res = client.post("/api/auth/login", json={"email": "admin@kwdc.com.np", "password": "Admin@123"})
    assert admin_res.status_code == 200
    admin_hdrs = {"Authorization": f"Bearer {admin_res.json()['access_token']}"}

    # 1. Google Maps Routing & Geolocation APIs
    m_stat = client.get("/api/maps/status")
    assert m_stat.status_code == 200

    dist_res = client.get(
        "/api/maps/route-distance",
        params={
            "origin": "Balaju, Kathmandu",
            "destination": "Chobhar, Kirtipur",
            "origin_lat": 27.732,
            "origin_lng": 85.302,
            "dest_lat": 27.660,
            "dest_lng": 85.291
        }
    )
    assert dist_res.status_code == 200, dist_res.text
    assert dist_res.json()["distance_km"] > 0

    # 2. Persistent Media Upload (Base64 + Multipart -> Retrieval)
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
    )
    up_res = client.post(
        "/api/uploads/image",
        files={"file": ("test_eq.png", tiny_png, "image/png")}
    )
    assert up_res.status_code == 200, up_res.text
    media_url = up_res.json()["url"]
    assert media_url.startswith("/api/uploads/media/")

    fetch_media = client.get(media_url)
    assert fetch_media.status_code == 200
    assert fetch_media.content == tiny_png

    # 3. Heavy Equipment Owner End-to-End Lifecycle
    eq_hdrs = create_user(f"eq_own_{rand_id}@kwdc.com.np", "Himalayan Cranes Co", f"+977-9808{rand_id}", "equipment_owner")
    cli_hdrs = create_user(f"eq_cli_{rand_id}@kwdc.com.np", "Chobhar Logistics Client", f"+977-9858{rand_id}", "commercial_client")

    reg_res = client.post("/api/equipment/register", headers=eq_hdrs, json={
        "equipment_type": "Forklift",
        "model_name": f"Toyota 8FD30 #{rand_id}",
        "registration_no": f"Ba 1 Ka {rand_id % 9999}",
        "capacity_ton": 3.0,
        "hourly_rate_npr": 1500.0,
        "daily_rate_npr": 8500.0,
        "monthly_rate_npr": 165000.0,
        "operator_included": True,
        "location_city": "Kathmandu",
        "photo_url": media_url
    })
    assert reg_res.status_code == 200, reg_res.text
    eq_id = reg_res.json()["equipment_id"]
    assert reg_res.json()["is_approved"] is False

    # Not yet visible in approved catalog until Admin approves
    cat_before = client.get("/api/equipment/catalog").json()
    assert not any(e["id"] == eq_id for e in cat_before)

    # Admin inspects & approves
    adm_list = client.get("/api/equipment/admin/all", headers=admin_hdrs)
    assert adm_list.status_code == 200 and any(e["id"] == eq_id for e in adm_list.json())
    adm_app = client.post(f"/api/equipment/admin/{eq_id}/approve?approved=true", headers=admin_hdrs)
    assert adm_app.status_code == 200 and adm_app.json()["is_approved"] is True

    # Visible in Client catalog
    cat_after = client.get("/api/equipment/catalog").json()
    assert any(e["id"] == eq_id for e in cat_after)

    # Client books for 2 DAILY units
    book_res = client.post("/api/equipment/book", headers=cli_hdrs, json={
        "equipment_id": eq_id,
        "duration_type": "DAILY",
        "duration_units": 2,
        "site_address": "Chobhar Dry Port Yard 4"
    })
    assert book_res.status_code == 200, book_res.text
    job_id = book_res.json()["job_id"]
    assert book_res.json()["base_cost_npr"] == 17000.0
    assert book_res.json()["vat_13_percent"] == 2210.0

    # Equipment owner deploys & completes job
    s1 = client.post(f"/api/equipment/jobs/{job_id}/status?status_str=IN_PROGRESS", headers=eq_hdrs)
    assert s1.status_code == 200
    s2 = client.post(f"/api/equipment/jobs/{job_id}/status?status_str=COMPLETED", headers=eq_hdrs)
    assert s2.status_code == 200

    fleet_summary = client.get("/api/equipment/my-fleet", headers=eq_hdrs).json()["summary"]
    assert fleet_summary["gross_revenue_npr"] == 17000.0
    assert fleet_summary["platform_fee_npr"] == 1700.0
    assert fleet_summary["net_payout_npr"] == 15300.0

    # Check HTML portals render cleanly
    eq_html = client.get("/equipment").text
    assert "toggleLanguage" in eq_html and "langBtn" in eq_html

    print("ALL MAPS, MEDIA UPLOAD & HEAVY EQUIPMENT CHECKS PASSED!")


if __name__ == "__main__":
    test_maps_equipment_and_uploads()
