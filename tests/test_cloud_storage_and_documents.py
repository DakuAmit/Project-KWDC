"""
Verification Suite for Cloud Object Storage & Multi-Format Document Uploads:
1. /api/uploads/status and multi-format uploads (Photo JPG, Video MP4, KYC PDF, Packing List CSV)
2. Supabase Storage REST / Signed-URL & /api/uploads/confirm redirect path (mocked HTTP)
3. Warehouse listing video_urls & Client inward StockItem packing_list_doc_url persistence
4. Twilio SMS provider integration formatting check
"""
import io
import random
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import SessionLocal
from backend.auth_utils import get_password_hash
from backend.config import settings
from backend.services import cloud_storage, sms_service
import backend.models as models

client = TestClient(app)


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


def test_cloud_storage_uploads_and_supabase_mock():
    rnd = random.randint(10000, 99999)
    owner_id, own_h = _create_verified_user(f"cs_own_{rnd}@kwdc.com.np", "Cloud Owner", f"98015{rnd}", "property_owner")
    cli_id, cli_h = _create_verified_user(f"cs_cli_{rnd}@kwdc.com.np", "Cloud Client", f"98025{rnd}", "commercial_client")
    inc_id, inc_h = _create_verified_user(f"cs_inc_{rnd}@kwdc.com.np", "Site Incharge", f"98035{rnd}", "warehouse_incharge")
    adm_res = client.post("/api/auth/login", json={"email": "admin@kwdc.com.np", "password": "Admin@123"})
    assert adm_res.status_code == 200
    adm_h = {"Authorization": f"Bearer {adm_res.json()['access_token']}"}
    asset_ids = []
    wh_id = None
    stock_id = None

    try:
        # 1. Storage status
        st = client.get("/api/uploads/status")
        assert st.status_code == 200
        assert st.json()["bucket"] == settings.SUPABASE_STORAGE_BUCKET

        # 2. Fallback /api/uploads/file for Photo, Video, KYC PDF & Packing List CSV
        uploads = [
            ("godown.jpg", b"\xff\xd8\xff\xe0MOCK_JPG", "image/jpeg", "WAREHOUSE_PHOTO"),
            ("walkthrough.mp4", b"\x00\x00\x00\x18ftypmp42MOCK_VIDEO", "video/mp4", "WAREHOUSE_VIDEO"),
            ("citizenship.pdf", b"%PDF-1.4\n1 0 obj\nMOCK_PDF\n%%EOF", "application/pdf", "KYC_DOCUMENT"),
            ("packing_list.csv", b"sku,item,qty\nSKU1,TV,20\n", "text/csv", "INVOICE_PACKING_LIST"),
        ]
        urls = {}
        for fname, raw, ctype, cat in uploads:
            res = client.post(
                "/api/uploads/file",
                headers=cli_h,
                data={"category": cat},
                files={"file": (fname, io.BytesIO(raw), ctype)},
            )
            assert res.status_code == 200, res.text
            d = res.json()
            asset_ids.append(d["asset_id"])
            urls[cat] = d["url"]
            get_res = client.get(d["url"], follow_redirects=False)
            assert get_res.status_code == 200
            assert get_res.content == raw
            assert ctype.split("/")[0] in get_res.headers.get("content-type", "")

        # 3. Signed URL + Confirm Cloud flow with mocked Supabase Storage key (including new sb_secret_ format)
        orig_key = settings.SUPABASE_SERVICE_ROLE_KEY
        orig_post = cloud_storage.requests.post
        orig_get = cloud_storage.requests.get
        try:
            settings.SUPABASE_SERVICE_ROLE_KEY = "sb_secret_test_key_123"
            hdrs = cloud_storage._supabase_headers("application/json")
            assert hdrs.get("apikey") == "sb_secret_test_key_123"
            assert "Authorization" not in hdrs

            class _FakeResp:
                def __init__(self, code, data=None, text="ok"):
                    self.status_code = code
                    self._data = data or {}
                    self.text = text

                def json(self):
                    return self._data

            cloud_storage.requests.get = lambda *a, **kw: _FakeResp(200, {"id": "kwdc-media"})
            cloud_storage.requests.post = lambda *a, **kw: _FakeResp(
                200, {"url": "/object/upload/sign/kwdc-media/warehouse_video/abc_vid.mp4?token=xyz"}
            )

            su = client.post(
                "/api/uploads/signed-url",
                headers=own_h,
                json={"filename": "tour.mp4", "content_type": "video/mp4", "category": "WAREHOUSE_VIDEO", "file_size_bytes": 12000000},
            )
            assert su.status_code == 200, su.text
            sud = su.json()
            assert sud["direct_upload"] is True
            assert "token=xyz" in sud["upload_url"]

            conf = client.post(
                "/api/uploads/confirm",
                headers=own_h,
                json={
                    "filename": "tour.mp4",
                    "content_type": "video/mp4",
                    "category": "WAREHOUSE_VIDEO",
                    "storage_path": sud["storage_path"],
                    "cloud_url": sud["cloud_url"],
                    "file_size_bytes": 12000000,
                },
            )
            assert conf.status_code == 200, conf.text
            cd = conf.json()
            asset_ids.append(cd["asset_id"])
            assert cd["storage_provider"] == "SUPABASE_STORAGE"

            redir = client.get(cd["proxy_url"], follow_redirects=False)
            assert redir.status_code == 307
            assert redir.headers["location"] == sud["cloud_url"]
        finally:
            settings.SUPABASE_SERVICE_ROLE_KEY = orig_key
            cloud_storage.requests.post = orig_post
            cloud_storage.requests.get = orig_get
            cloud_storage._BUCKET_CHECKED = False

        # 4. Warehouse listing video_urls & Stock inward packing_list_doc_url
        wh_res = client.post(
            "/api/warehouses/list-space",
            headers=own_h,
            json={
                "title": f"Cloud Video Godown {rnd}",
                "total_sqft": 2500,
                "base_rate_per_sqft": 35,
                "municipality": "Kathmandu",
                "neighborhood_landmark": "Kalanki",
                "photo_urls": [urls["WAREHOUSE_PHOTO"]],
                "video_urls": [urls["WAREHOUSE_VIDEO"]],
            },
        )
        assert wh_res.status_code == 200, wh_res.text
        wh_id = wh_res.json()["warehouse_id"]

        listings = client.get("/api/warehouses/my-listings", headers=own_h)
        assert listings.status_code == 200
        mine = [x for x in listings.json() if x["id"] == wh_id][0]
        assert urls["WAREHOUSE_VIDEO"] in mine["video_urls"]

        # 4B. Property Owner appends extra photo & video to existing warehouse
        own_media = client.post(
            f"/api/warehouses/{wh_id}/media",
            headers=own_h,
            json={
                "photo_urls": ["/api/uploads/media/extra_owner_photo"],
                "video_urls": ["/api/uploads/media/extra_owner_video"],
                "caption": "Updated Loading Bay Angle",
            },
        )
        assert own_media.status_code == 200, own_media.text
        assert "/api/uploads/media/extra_owner_photo" in own_media.json()["photos"]
        assert "/api/uploads/media/extra_owner_video" in own_media.json()["video_urls"]

        # 4C. Unassigned Incharge is blocked from adding media/details
        unassigned_try = client.post(
            f"/api/incharge/warehouses/{wh_id}/media-details",
            headers=inc_h,
            json={"photo_urls": ["/api/uploads/media/bad"], "audit_notes": "Unauthorized"},
        )
        assert unassigned_try.status_code == 403

        # 4D. Assign Incharge -> add on-site inspection photos, video & verified physical details
        assign_res = client.post(
            f"/api/admin/warehouses/{wh_id}/assign-incharge",
            headers=adm_h,
            json={"incharge_id": inc_id},
        )
        assert assign_res.status_code == 200, assign_res.text

        assigned_list = client.get("/api/incharge/assigned-warehouses", headers=inc_h)
        assert assigned_list.status_code == 200
        assert any(a["warehouse_id"] == wh_id for a in assigned_list.json())

        inc_media = client.post(
            f"/api/incharge/warehouses/{wh_id}/media-details",
            headers=inc_h,
            json={
                "photo_urls": ["/api/uploads/media/incharge_gate_photo"],
                "video_urls": ["/api/uploads/media/incharge_walkthrough_video"],
                "clear_ceiling_height_ft": 16.5,
                "road_access_ft": 26.0,
                "has_cctv": True,
                "physical_audit_status": "VERIFIED_PASSED",
                "audit_notes": "Verified 16.5ft ceiling, 26ft blacktop road, CCTV & damp-proof floor.",
            },
        )
        assert inc_media.status_code == 200, inc_media.text
        assert "/api/uploads/media/incharge_gate_photo" in inc_media.json()["photos"]
        assert "/api/uploads/media/incharge_walkthrough_video" in inc_media.json()["video_urls"]
        assert inc_media.json()["clear_ceiling_height_ft"] == 16.5
        assert inc_media.json()["physical_audit_status"] == "VERIFIED_PASSED"

        stk_res = client.post(
            "/api/warehouses/my-inventory",
            headers=cli_h,
            json={
                "warehouse_id": wh_id,
                "item_name": "Imported Solar Inverters",
                "quantity": 10,
                "packing_list_doc_url": urls["INVOICE_PACKING_LIST"],
            },
        )
        assert stk_res.status_code == 200, stk_res.text
        stock_id = stk_res.json()["stock_item_id"]

        inv = client.get("/api/warehouses/my-inventory", headers=cli_h)
        assert inv.status_code == 200
        item_row = [i for i in inv.json()["items"] if i["id"] == stock_id][0]
        assert item_row["packing_list_doc_url"] == urls["INVOICE_PACKING_LIST"]

        # 5. Twilio SMS formatting check (mocked HTTP)
        orig_sid, orig_tok, orig_num = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_FROM_NUMBER
        orig_sms_post = sms_service.requests.post
        captured = {}
        try:
            settings.TWILIO_ACCOUNT_SID = "AC_TEST_123"
            settings.TWILIO_AUTH_TOKEN = "auth_secret"
            settings.TWILIO_FROM_NUMBER = "+15550001111"

            class _TwResp:
                status_code = 201
                text = "ok"
                def json(self):
                    return {"sid": "SM_TEST_999"}

            def _fake_tw(url, **kw):
                captured["url"] = url
                captured["data"] = kw.get("data")
                return _TwResp()

            sms_service.requests.post = _fake_tw
            tw_out = sms_service.send_sms(None, "9841000001", "Test OTP: 112233", purpose="OTP")
            assert tw_out["provider"] == "TWILIO"
            assert tw_out["status"] == "SENT"
            assert captured["data"]["To"] == "+9779841000001"
            assert "api.twilio.com/2010-04-01/Accounts/AC_TEST_123/Messages.json" in captured["url"]
        finally:
            settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_FROM_NUMBER = orig_sid, orig_tok, orig_num
            sms_service.requests.post = orig_sms_post
    finally:
        db = SessionLocal()
        try:
            if stock_id:
                db.query(models.StockMovementLog).filter(models.StockMovementLog.stock_item_id == stock_id).delete()
                db.query(models.InventoryUnit).filter(models.InventoryUnit.stock_item_id == stock_id).delete()
                db.query(models.StockItem).filter(models.StockItem.id == stock_id).delete()
            if wh_id:
                db.query(models.WarehouseActivityLog).filter(models.WarehouseActivityLog.warehouse_id == wh_id).delete()
                db.query(models.WarehouseInchargeAssignment).filter(models.WarehouseInchargeAssignment.warehouse_id == wh_id).delete()
                db.query(models.WarehousePhoto).filter(models.WarehousePhoto.warehouse_id == wh_id).delete()
                db.query(models.Warehouse).filter(models.Warehouse.id == wh_id).delete()
            if asset_ids:
                db.query(models.MediaAsset).filter(models.MediaAsset.id.in_(asset_ids)).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id.in_([owner_id, cli_id, inc_id])).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


def _create_pending_user(email: str, name: str, phone: str, role: str):
    db = SessionLocal()
    try:
        u = models.User(
            full_name=name,
            email=email.lower(),
            phone_number=phone,
            hashed_password=get_password_hash("Password@123"),
            role=models.UserRole(role),
            is_verified=True,
            is_active=True,
            kyc_status=models.KycStatus.PENDING_SUBMISSION,
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


def test_individual_driver_kyc_bluebook_and_job_gate():
    rnd = random.randint(10000, 99999)
    ind_id, ind_h = _create_pending_user(f"ind_kyc_{rnd}@kwdc.com.np", "Solo Trucker", f"98491{rnd}", "fleet_partner")
    cli_id, cli_h = _create_verified_user(f"ind_cli_{rnd}@kwdc.com.np", "Cargo Shipper", f"98591{rnd}", "commercial_client")
    adm_r = client.post("/api/auth/login", json={"email": "admin@kwdc.com.np", "password": "Admin@123"})
    adm_h = {"Authorization": f"Bearer {adm_r.json()['access_token']}"}
    order_id = None

    try:
        # Client creates an open mini_truck dispatch order
        o_res = client.post(
            "/api/fleet/dispatch-orders",
            headers=cli_h,
            json={
                "dispatch_mode": "DIRECT_HAUL",
                "pickup_address": "Kalanki",
                "pickup_contact_name": "Shipper",
                "pickup_contact_phone": "9801112233",
                "destination_address": "Koteshwor",
                "consignee_name": "Receiver",
                "consignee_phone": "9802223344",
                "total_distance_km": 10.0,
                "cargo_description": f"KYC Gated Order #{rnd}",
                "required_vehicle_category": "mini_truck",
                "cargo_weight_kg": 900.0,
            },
        )
        assert o_res.status_code == 200, o_res.text
        order_id = o_res.json()["order_id"]

        # Switch to INDEPENDENT_OWNER
        op = client.post("/api/fleet/operator-type", headers=ind_h, json={"operator_type": "INDEPENDENT_OWNER"})
        assert op.status_code == 200

        # Cannot view dispatch-orders while KYC unverified
        blocked_board = client.get("/api/fleet/dispatch-orders", headers=ind_h)
        assert blocked_board.status_code == 403

        # Cannot submit self-driver KYC without Vehicle + Bluebook
        missing_veh = client.post(
            "/api/fleet/drivers",
            headers=ind_h,
            json={
                "full_name": "Solo Trucker",
                "phone_number": f"98491{rnd}",
                "license_number": f"DL-{rnd}",
                "citizenship_no": f"CTZ-{rnd}",
                "id_doc_front_url": "/api/uploads/media/1",
                "id_doc_back_url": "/api/uploads/media/2",
                "license_photo_front_url": "/api/uploads/media/3",
                "is_self_driver": True,
                "login_pin": "5566",
            },
        )
        assert missing_veh.status_code == 400

        # Submit complete KYC: Driving License + Citizenship + Vehicle Details + Bluebook
        full_kyc = client.post(
            "/api/fleet/drivers",
            headers=ind_h,
            json={
                "full_name": "Solo Trucker",
                "phone_number": f"98491{rnd}",
                "license_number": f"DL-{rnd}",
                "citizenship_no": f"CTZ-{rnd}",
                "id_doc_front_url": "/api/uploads/media/1",
                "id_doc_back_url": "/api/uploads/media/2",
                "license_photo_front_url": "/api/uploads/media/3",
                "is_self_driver": True,
                "login_pin": "5566",
                "vehicle_category": "mini_truck",
                "vehicle_model_name": "Tata Ace Gold",
                "vehicle_license_plate": f"BA-2-KHA-{rnd}",
                "bluebook_number": f"BB-{rnd}",
                "bluebook_photo_url": "/api/uploads/media/4",
                "payload_capacity_kg": 1500.0,
            },
        )
        assert full_kyc.status_code == 200, full_kyc.text
        assert full_kyc.json()["kyc_status"] == "UNDER_REVIEW"

        # Log into Driver Cab App -> available-jobs MUST remain locked until SuperAdmin verifies KYC
        d_login = client.post("/api/fleet/driver/login", json={"phone_number": f"98491{rnd}", "pin": "5566"})
        assert d_login.status_code == 200, d_login.text
        d_h = {"Authorization": f"Bearer {d_login.json()['access_token']}"}

        locked_jobs = client.get("/api/fleet/driver/available-jobs", headers=d_h)
        assert locked_jobs.status_code == 200
        assert locked_jobs.json()["can_bid"] is False
        assert locked_jobs.json()["kyc_required"] is True
        assert locked_jobs.json()["jobs"] == []
        assert client.post(f"/api/fleet/driver/jobs/{order_id}/accept", headers=d_h).status_code == 403

        # SuperAdmin reviews full dossier (License + Vehicle + Bluebook) and Approves KYC
        dossier = client.get(f"/api/admin/users/{ind_id}/kyc", headers=adm_h)
        assert dossier.status_code == 200, dossier.text
        dj = dossier.json()
        assert len(dj["vehicles"]) == 1 and dj["vehicles"][0]["bluebook_photo_url"] == "/api/uploads/media/4"
        assert len(dj["drivers"]) == 1 and dj["drivers"][0]["license_photo_front_url"] == "/api/uploads/media/3"

        ver = client.post(
            f"/api/admin/users/{ind_id}/kyc-verify",
            headers=adm_h,
            json={"kyc_status": "VERIFIED", "admin_notes": "License & Bluebook verified"},
        )
        assert ver.status_code == 200

        # Now BOTH Fleet Dispatch Board & Driver Cab Available Jobs UNLOCK
        ok_board = client.get("/api/fleet/dispatch-orders", headers=ind_h)
        assert ok_board.status_code == 200
        assert any(o["id"] == order_id for o in ok_board.json())

        unlocked_jobs = client.get("/api/fleet/driver/available-jobs", headers=d_h)
        assert unlocked_jobs.status_code == 200
        assert unlocked_jobs.json()["can_bid"] is True
        assert any(j["id"] == order_id for j in unlocked_jobs.json()["jobs"])
    finally:
        db = SessionLocal()
        try:
            if order_id:
                db.query(models.DeliveryStop).filter(models.DeliveryStop.dispatch_order_id == order_id).delete()
                db.query(models.DispatchOrder).filter(models.DispatchOrder.id == order_id).delete()
            db.query(models.Driver).filter(models.Driver.fleet_partner_id == ind_id).delete()
            db.query(models.Vehicle).filter(models.Vehicle.fleet_partner_id == ind_id).delete()
            db.query(models.UserKycProfile).filter(models.UserKycProfile.user_id == ind_id).delete()
            db.query(models.User).filter(models.User.id.in_([ind_id, cli_id])).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    test_cloud_storage_uploads_and_supabase_mock()
    print("[PASS] Cloud Storage (Photo, Video, KYC PDF, Packing List) & Twilio SMS tests")
    test_individual_driver_kyc_bluebook_and_job_gate()
    print("[PASS] Individual Driver KYC (License + Vehicle + Bluebook) & Job Visibility Gate tests")
