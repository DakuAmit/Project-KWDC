"""
Automated UI Screenshot Pack Generator (KTM-WDC)
------------------------------------------------
Boots an isolated temporary SQLite FastAPI server, seeds realistic showcase data
across all 7+ platform roles, and captures organized Desktop (1440px) & Mobile (390px)
screenshots of every portal, tab, and key modal into ./ui_screenshots/ along with a
browsable ./ui_screenshots/index.html gallery for UI designers.

Usage:
    python scripts/capture_ui_screenshots.py
"""
import base64
import html
import os
import pathlib
import socket
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Use an isolated temporary SQLite database so production/dev DBs are untouched
TMP_DB_DIR = tempfile.TemporaryDirectory(prefix="kwdc_ui_snap_", ignore_cleanup_errors=True)
TEMP_DB_PATH = pathlib.Path(TMP_DB_DIR.name) / "ui_showcase.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEMP_DB_PATH.as_posix()}"

import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

import backend.models as models  # noqa: E402
from backend.auth_utils import get_password_hash  # noqa: E402
from backend.database import SessionLocal  # noqa: E402
from backend.main import app  # noqa: E402

OUT_DIR = ROOT / "ui_screenshots"

SAMPLE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def api_post(base_url: str, path: str, payload: dict, token: str | None = None):
    import json

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return 500, {"error": str(exc)}


def seed_showcase_data(base_url: str) -> dict:
    """Create verified showcase users & rich operational data in temp SQLite."""
    db = SessionLocal()
    try:
        def ensure_account(email: str, full_name: str, phone: str, role: models.UserRole, kyc=models.KycStatus.VERIFIED, op_type=None):
            u = db.query(models.User).filter(models.User.email == email).first()
            if not u:
                u = models.User(
                    email=email,
                    full_name=full_name,
                    phone_number=phone,
                    hashed_password=get_password_hash("Demo@1234"),
                    role=role,
                    fleet_operator_type=op_type,
                    is_active=True,
                    is_verified=True,
                    kyc_status=kyc,
                )
                db.add(u)
                db.commit()
                db.refresh(u)
            return u

        owner = ensure_account("owner_ui@kwdc.com.np", "Ram Bahadur Shrestha", "+977-9849100001", models.UserRole.PROPERTY_OWNER)
        client = ensure_account("client_ui@kwdc.com.np", "Himalayan FMCG Pvt Ltd", "+977-9849100002", models.UserRole.COMMERCIAL_CLIENT)
        fleet = ensure_account("fleet_ui@kwdc.com.np", "Sagarmatha Freight & 3PL", "+977-9849100003", models.UserRole.FLEET_PARTNER, op_type="INDEPENDENT_OWNER")
        incharge = ensure_account("incharge_ui@kwdc.com.np", "Bikram Karki", "+977-9849100004", models.UserRole.WAREHOUSE_INCHARGE)
        equip = ensure_account("equip_ui@kwdc.com.np", "Nepal Heavy Lift Co.", "+977-9849100005", models.UserRole.EQUIPMENT_OWNER)
        security = ensure_account("security_ui@kwdc.com.np", "Gorkha Sentinel Security", "+977-9849100006", models.UserRole.SECURITY_AGENCY)

        # Sample media image asset for inline document previews
        img_bytes = base64.b64decode(SAMPLE_PNG_B64)
        asset = db.query(models.MediaAsset).first()
        if not asset:
            asset = models.MediaAsset(
                uploader_id=owner.id,
                category="image",
                filename="sample_doc_preview.png",
                content_type="image/png",
                file_size_bytes=len(img_bytes),
                storage_provider="postgres",
                data_base64=SAMPLE_PNG_B64,
            )
            db.add(asset)
            db.commit()
            db.refresh(asset)
        media_url = f"/api/uploads/media/{asset.id}"

        # Seed verified + pending warehouses
        wh = db.query(models.Warehouse).filter(models.Warehouse.owner_id == owner.id).first()
        if not wh:
            wh = models.Warehouse(
                owner_id=owner.id,
                title="Balaju Industrial Logistics Hub #1",
                space_type=models.SpaceType.COVERED_GODOWN,
                district="Kathmandu",
                municipality="Kathmandu Metro",
                neighborhood_landmark="Balaju Industrial Estate, Ring Road",
                latitude=27.7340,
                longitude=85.3012,
                total_sqft=12000.0,
                available_sqft=8500.0,
                monthly_rate_per_sqft=24.0,
                client_rate_per_sqft=28.0,
                clear_ceiling_height_ft=24.0,
                road_access_ft=30.0,
                has_cctv=True,
                has_forklift_ramp=True,
                is_approved=True,
                is_available=True,
                physical_audit_status=models.PhysicalAuditStatus.VERIFIED_PASSED,
            )
            db.add(wh)
            wh_pending = models.Warehouse(
                owner_id=owner.id,
                title="Kalanki Highway Cold Annex",
                space_type=models.SpaceType.COMMERCIAL_SHUTTER,
                district="Kathmandu",
                municipality="Kathmandu Metro",
                neighborhood_landmark="Kalanki Chowk",
                latitude=27.6933,
                longitude=85.2816,
                total_sqft=4500.0,
                available_sqft=4500.0,
                monthly_rate_per_sqft=28.0,
                client_rate_per_sqft=32.0,
                is_approved=False,
                is_available=True,
                physical_audit_status=models.PhysicalAuditStatus.PENDING_INSPECTION,
            )
            db.add(wh_pending)
            db.commit()
            db.refresh(wh)

            db.add(models.WarehousePhoto(warehouse_id=wh.id, photo_url=media_url, caption="Main Loading Bay"))
            db.add(models.WarehouseInchargeAssignment(incharge_id=incharge.id, warehouse_id=wh.id, is_active=True))
            db.commit()

        # Owner KYC Profile
        if not db.query(models.UserKycProfile).filter(models.UserKycProfile.user_id == owner.id).first():
            db.add(models.UserKycProfile(
                user_id=owner.id,
                role=models.UserRole.PROPERTY_OWNER,
                citizenship_number="27-01-74-10982",
                citizenship_front_url=media_url,
                citizenship_back_url=media_url,
                bank_name="Nabil Bank Ltd.",
                bank_account_number="0110017500123",
                bank_account_name="Ram Bahadur Shrestha",
                bank_branch="Balaju Branch",
                bank_proof_doc_url=media_url,
                kyc_status=models.KycStatus.VERIFIED,
            ))
            db.commit()

        # Booking + StockItem + GatePass + SecurityAgency
        bk = db.query(models.WarehouseRequest).filter(models.WarehouseRequest.client_id == client.id).first()
        if not bk:
            bk = models.WarehouseRequest(
                client_id=client.id,
                warehouse_id=wh.id,
                requested_sqft=3500.0,
                allocated_billed_sqft=3500.0,
                monthly_base_rent=98000.0,
                kwdc_margin_amount=9800.0,
                vat_13_percent=14014.0,
                total_monthly_bill=121814.0,
                status=models.BookingStatus.ACTIVE_LEASED,
            )
            db.add(bk)
            db.commit()
            db.refresh(bk)

        if not db.query(models.StockItem).filter(models.StockItem.client_id == client.id).first():
            st = models.StockItem(
                client_id=client.id,
                warehouse_id=wh.id,
                booking_id=bk.id,
                sku_code="SKU-RICE-001",
                item_name="Basmati Rice 25kg Sacks",
                category="FMCG / Grains",
                unit_type=models.InventoryUnitType.PALLET,
                total_quantity=240,
                reserved_quantity=30,
                dispatched_quantity=0,
                verification_status="VERIFIED",
                bay_rack_location="Zone A / Rack 04",
                packing_list_doc_url=media_url,
            )
            db.add(st)
            db.commit()
            db.refresh(st)
            db.add(models.GatePass(
                warehouse_id=wh.id,
                client_id=client.id,
                incharge_id=incharge.id,
                stock_item_id=st.id,
                booking_id=bk.id,
                pass_type="INWARD",
                vehicle_plate="Ba 2 Cha 4488",
                driver_name="Prakash Tamang",
                unit_type=models.InventoryUnitType.PALLET,
                scanned_units_count=40,
                remarks="UI Showcase Inward Gate Pass",
            ))
            db.commit()

        if not db.query(models.SecurityAgency).filter(models.SecurityAgency.user_id == security.id).first():
            ag = models.SecurityAgency(
                user_id=security.id,
                agency_name="Gorkha Sentinel Security",
                home_ministry_license_no="HM-SEC-2081-77",
                emergency_contact_phone="+977-9803344556",
                is_verified=True,
            )
            db.add(ag)
            db.commit()
            db.refresh(ag)
            db.add(models.GuardPersonnel(
                agency_id=ag.id,
                guard_name="Sher Bahadur Magar",
                phone_number="9841778899",
                assigned_warehouse_id=wh.id,
                shift_type="NIGHT",
                is_active=True,
            ))
            db.commit()
    finally:
        db.close()

    tokens = {}
    for key, (email, pwd) in {
        "admin": ("admin@kwdc.com.np", "Admin@123"),
        "owner": ("owner_ui@kwdc.com.np", "Demo@1234"),
        "client": ("client_ui@kwdc.com.np", "Demo@1234"),
        "fleet": ("fleet_ui@kwdc.com.np", "Demo@1234"),
        "incharge": ("incharge_ui@kwdc.com.np", "Demo@1234"),
        "equipment": ("equip_ui@kwdc.com.np", "Demo@1234"),
        "security": ("security_ui@kwdc.com.np", "Demo@1234"),
    }.items():
        _, res = api_post(base_url, "/api/auth/login", {"email": email, "password": pwd})
        tokens[key] = res.get("access_token", "")

    # Add Vehicle + Driver (with Bluebook KYC), Dispatch Order, and Heavy Equipment
    _, d_res = api_post(
        base_url,
        "/api/fleet/drivers",
        {
            "full_name": "Prakash Tamang",
            "phone_number": "9841990011",
            "login_pin": "2468",
            "license_number": "01-06-884422",
            "license_categories": ["Category B (Van / Pickup)", "Category G (Heavy Truck)"],
            "id_document_type": "CITIZENSHIP",
            "citizenship_no": "27-01-75-44556",
            "id_doc_front_url": "/api/uploads/media/1",
            "id_doc_back_url": "/api/uploads/media/1",
            "license_photo_front_url": "/api/uploads/media/1",
            "license_photo_back_url": "/api/uploads/media/1",
            "vehicle_category": "MINI_TRUCK",
            "vehicle_model_name": "Tata Ace Gold",
            "vehicle_license_plate": "Ba 2 Cha 4488",
            "bluebook_number": "BB-KATH-99881",
            "bluebook_photo_url": "/api/uploads/media/1",
            "payload_capacity_kg": 1500,
            "blood_group": "O+",
            "is_self_driver": True,
        },
        tokens["fleet"],
    )
    _, drv_login = api_post(base_url, "/api/fleet/driver/login", {"phone_number": "9841990011", "pin": "2468"})
    tokens["driver"] = drv_login.get("access_token", "")
    tokens["driver_profile"] = drv_login.get("driver", {"full_name": "Prakash Tamang", "phone_number": "9841990011"})

    api_post(
        base_url,
        "/api/fleet/dispatch-orders",
        {
            "dispatch_mode": "DIRECT_HAUL",
            "pickup_address": "Kalanki Yard, Kathmandu",
            "pickup_contact_name": "Himalayan FMCG",
            "pickup_contact_phone": "+977-9851098765",
            "destination_address": "Koteshwor Hub, Ring Road",
            "consignee_name": "Sita Traders",
            "consignee_phone": "+977-9841112233",
            "total_distance_km": 12.5,
            "cargo_description": "40 Pallets Packaged Beverages",
            "required_vehicle_category": "MINI_TRUCK",
            "cargo_weight_kg": 1250.0,
        },
        tokens["client"],
    )

    api_post(
        base_url,
        "/api/equipment/register",
        {
            "equipment_type": "FORKLIFT",
            "model_name": "Toyota 3-Ton Diesel Forklift",
            "capacity_ton": 3.0,
            "registration_no": "EQ-KTM-301",
            "hourly_rate_npr": 1800,
            "daily_rate_npr": 9500,
            "monthly_rate_npr": 175000,
            "location_city": "Kathmandu",
            "operator_included": True,
            "photo_url": "/api/uploads/media/1",
        },
        tokens["equipment"],
    )

    return tokens


def launch_browser(p):
    for kwargs in (
        {"channel": "chrome", "headless": True},
        {"channel": "msedge", "headless": True},
        {"headless": True},
    ):
        try:
            return p.chromium.launch(**kwargs)
        except Exception:
            continue
    raise RuntimeError("No Chromium/Chrome/Edge browser executable found for Playwright.")


def open_portal(page, base_url: str, path: str, token: str = "", extra_ls: dict | None = None):
    page.goto(f"{base_url}/", wait_until="domcontentloaded")
    page.evaluate(
        """([tok, extra]) => {
            localStorage.clear();
            if (tok) {
                localStorage.setItem('kwdc_token', tok);
                localStorage.setItem('kwdc_admin_token', tok);
            }
            if (extra) {
                for (const [k, v] of Object.entries(extra)) {
                    localStorage.setItem(k, typeof v === 'string' ? v : JSON.stringify(v));
                }
            }
        }""",
        [token, extra_ls or {}],
    )
    page.goto(f"{base_url}{path}", wait_until="load", timeout=15000)
    page.wait_for_timeout(1200)


def snap(page, folder: pathlib.Path, filename: str, manifest: list, category: str, caption: str):
    folder.mkdir(parents=True, exist_ok=True)
    out_file = folder / filename
    try:
        page.screenshot(path=str(out_file), full_page=True)
        rel = out_file.relative_to(OUT_DIR).as_posix()
        manifest.append({"cat": category, "file": rel, "caption": caption})
        print(f"  [SHOT] {rel}")
    except Exception as exc:
        print(f"  [WARN] Could not capture {filename}: {exc}")


def click_safe(page, js_call: str):
    try:
        page.evaluate(js_call)
        page.wait_for_timeout(450)
        return True
    except Exception:
        return False


def build_gallery_html(manifest: list):
    groups = {}
    for item in manifest:
        groups.setdefault(item["cat"], []).append(item)

    sections_html = []
    for cat, items in groups.items():
        cards = "\n".join(
            f"""
            <a href="{html.escape(it['file'])}" target="_blank" class="card">
              <img src="{html.escape(it['file'])}" loading="lazy" alt="{html.escape(it['caption'])}">
              <div class="meta"><strong>{html.escape(it['caption'])}</strong><span>{html.escape(it['file'])}</span></div>
            </a>"""
            for it in items
        )
        sections_html.append(f"<section><h2>{html.escape(cat)} ({len(items)})</h2><div class='grid'>{cards}</div></section>")

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>KTM-WDC UI Screenshot Gallery (Designer Handoff)</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; padding: 32px; }}
  h1 {{ margin: 0 0 6px; font-size: 24px; color: #fff; }}
  p.sub {{ color: #94a3b8; margin: 0 0 28px; font-size: 14px; }}
  section {{ margin-bottom: 42px; }}
  h2 {{ font-size: 17px; color: #38bdf8; border-bottom: 1px solid #1e293b; padding-bottom: 8px; margin-bottom: 16px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 18px; }}
  .card {{ display: block; background: #1e293b; border: 1px solid #334155; border-radius: 12px; overflow: hidden; text-decoration: none; color: inherit; transition: transform .15s, border-color .15s; }}
  .card:hover {{ transform: translateY(-2px); border-color: #38bdf8; }}
  .card img {{ width: 100%; height: 210px; object-fit: cover; object-position: top; background: #fff; display: block; }}
  .meta {{ padding: 12px; display: flex; flex-direction: column; gap: 4px; }}
  .meta strong {{ font-size: 13px; color: #f8fafc; }}
  .meta span {{ font-size: 11px; color: #94a3b8; font-family: monospace; }}
</style>
</head>
<body>
  <h1>KTM-WDC Complete Portal & Modal Screenshot Pack</h1>
  <p class="sub">Total captured screens: {len(manifest)} &bull; Click any frame to inspect full-resolution PNG.</p>
  {''.join(sections_html)}
</body>
</html>"""
    (OUT_DIR / "index.html").write_text(html_doc, encoding="utf-8")


def main():
    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(40):
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.25)

    tokens = seed_showcase_data(base_url)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []

    with sync_playwright() as p:
        browser = launch_browser(p)
        desktop = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)

        try:
            # 1. Public & Invoice
            dp = desktop.new_page()
            open_portal(dp, base_url, "/")
            snap(dp, OUT_DIR / "01_public", "01_landing_desktop.png", manifest, "01. Public Landing & Invoice", "Landing Page & Estimator (Desktop)")
            if click_safe(dp, "if (typeof openPartnerModal==='function') openPartnerModal()"):
                snap(dp, OUT_DIR / "01_public", "02_auth_modal_desktop.png", manifest, "01. Public Landing & Invoice", "Partner Registration Modal")
            open_portal(dp, base_url, "/invoice")
            snap(dp, OUT_DIR / "01_public", "03_ird_tax_invoice.png", manifest, "01. Public Landing & Invoice", "IRD Tax Invoice Print Layout")

            mp = mobile.new_page()
            open_portal(mp, base_url, "/")
            snap(mp, OUT_DIR / "01_public", "04_landing_mobile.png", manifest, "01. Public Landing & Invoice", "Landing Page (Mobile 390px)")

            # 2. Commercial Client Hub
            open_portal(dp, base_url, "/client", tokens["client"])
            for idx, (tab, title) in enumerate([
                ("catalog", "Storage Catalog"),
                ("bookings", "My Active Leases"),
                ("inventory", "Stored Inventory & SKUs"),
                ("calculator", "Area & Tariff Estimator"),
                ("equipment", "Heavy Equipment Rental"),
                ("gatepass", "Digital Gate Passes"),
                ("invoices", "IRD Tax Invoices"),
                ("insurance", "Cargo & Stock Insurance"),
                ("pickup-dispatch", "Warehouse Dispatch"),
                ("pickup-drop", "Direct Haul"),
            ], 1):
                click_safe(dp, f"switchTab('{tab}')")
                snap(dp, OUT_DIR / "02_client", f"{idx:02d}_{tab}.png", manifest, "02. Commercial Client Hub", f"Tab: {title}")

            for m_fn, m_file, m_lbl in [
                ("openKycModal()", "11_modal_corporate_kyc.png", "Modal: Corporate KYC + Previews"),
                ("openStockEntryModal()", "12_modal_stock_inward.png", "Modal: Log Stock Batch + Packing List"),
                ("openInsuranceModal()", "13_modal_insurance_req.png", "Modal: Cargo Insurance + Invoice Doc"),
            ]:
                if click_safe(dp, m_fn):
                    snap(dp, OUT_DIR / "02_client", m_file, manifest, "02. Commercial Client Hub", m_lbl)
                    click_safe(dp, "document.querySelectorAll('dialog[open]').forEach(d=>d.close())")

            # 3. Property Owner Cockpit
            open_portal(dp, base_url, "/owner", tokens["owner"])
            for idx, (tab, title) in enumerate([
                ("properties", "My Registered Spaces"),
                ("leases", "Active Tenant Leases"),
                ("payouts", "Rental Payouts & TDS"),
                ("maintenance", "Maintenance Hold Manager"),
                ("health", "Facility Health & Audits"),
                ("governance", "Master Legal Covenant"),
                ("kyc", "KYC & Bank Verification + Previews"),
            ], 1):
                click_safe(dp, f"switchTab('{tab}')")
                snap(dp, OUT_DIR / "03_owner", f"{idx:02d}_{tab}.png", manifest, "03. Property Owner Cockpit", f"Tab: {title}")

            if click_safe(dp, "openListingModal()"):
                snap(dp, OUT_DIR / "03_owner", "08_modal_list_space_map.png", manifest, "03. Property Owner Cockpit", "Modal: Register Space + Unit Converter & Map")
                click_safe(dp, "document.getElementById('listSpaceModal').close()")

            # 4. Fleet Partner Console
            open_portal(dp, base_url, "/fleet", tokens["fleet"])
            for idx, (tab, title) in enumerate([
                ("telemetry", "Fleet Radar & GPS"),
                ("jobs", "Freight Dispatch Jobs"),
                ("vehicles", "Commercial Fleet & Bluebook"),
                ("drivers", "Driver Crew Roster"),
                ("earnings", "Freight Earnings & Payouts"),
            ], 1):
                click_safe(dp, f"switchTab('{tab}')")
                snap(dp, OUT_DIR / "04_fleet", f"{idx:02d}_{tab}.png", manifest, "04. Fleet Partner Console", f"Tab: {title}")

            for m_fn, m_file, m_lbl in [
                ("openVehicleModal()", "06_modal_register_vehicle.png", "Modal: Register Vehicle + Bluebook"),
                ("openDriverModal(true)", "07_modal_individual_driver_kyc.png", "Modal: Individual Driver + License + Bluebook KYC"),
            ]:
                if click_safe(dp, m_fn):
                    snap(dp, OUT_DIR / "04_fleet", m_file, manifest, "04. Fleet Partner Console", m_lbl)
                    click_safe(dp, "document.querySelectorAll('dialog[open]').forEach(d=>d.close())")

            # 5. Driver Cab Terminal (Mobile-First 390px)
            open_portal(mp, base_url, "/driver", "", extra_ls={"kwdc_driver_token": ""})
            snap(mp, OUT_DIR / "05_driver_mobile", "01_driver_pin_login.png", manifest, "05. Driver Cab Terminal (Mobile)", "Phone + 4-Digit PIN Login")
            open_portal(mp, base_url, "/driver", "", extra_ls={"kwdc_driver_token": tokens["driver"], "kwdc_driver": tokens["driver_profile"]})
            snap(mp, OUT_DIR / "05_driver_mobile", "02_driver_cockpit_and_loads.png", manifest, "05. Driver Cab Terminal (Mobile)", "Driver Cockpit & KYC Gate / Jobs Feed")

            # 6. Warehouse Incharge Operations
            open_portal(dp, base_url, "/incharge", tokens["incharge"])
            for idx, (tab, title) in enumerate([
                ("facilities", "Assigned Facilities"),
                ("gatepass", "Digital Gate Passes"),
                ("stock", "Client Stock Dock"),
                ("logs", "Shift Inspection Logs"),
                ("hazards", "Hazard / Seepage Alert"),
            ], 1):
                click_safe(dp, f"switchTab('{tab}')")
                snap(dp, OUT_DIR / "06_incharge", f"{idx:02d}_{tab}.png", manifest, "06. Warehouse Incharge Operations", f"Tab: {title}")
            open_portal(mp, base_url, "/incharge", tokens["incharge"])
            snap(mp, OUT_DIR / "06_incharge", "06_incharge_mobile.png", manifest, "06. Warehouse Incharge Operations", "Incharge Dock Mobile View")

            # 7. Heavy Equipment Portal
            open_portal(dp, base_url, "/equipment", tokens["equipment"])
            snap(dp, OUT_DIR / "07_equipment", "01_owner_fleet.png", manifest, "07. Heavy Equipment Portal", "Owner Fleet & Rental Jobs")
            if click_safe(dp, "openRegisterModal()"):
                snap(dp, OUT_DIR / "07_equipment", "02_modal_register_machinery.png", manifest, "07. Heavy Equipment Portal", "Modal: Register Machinery + Photo Preview")
                click_safe(dp, "document.getElementById('registerEqModal').close()")
            if click_safe(dp, "switchEqPortalView('operator')"):
                snap(dp, OUT_DIR / "07_equipment", "03_operator_pin_terminal.png", manifest, "07. Heavy Equipment Portal", "Operator PIN Terminal View")

            # 8. Security Agency Portal
            open_portal(dp, base_url, "/security", tokens["security"])
            for idx, (tab, title) in enumerate([
                ("roster", "Guard Roster & Sites"),
                ("patrols", "Shift Patrol Logs"),
                ("incidents", "Police & Hazard Alert"),
            ], 1):
                click_safe(dp, f"switchTab('{tab}')")
                snap(dp, OUT_DIR / "08_security", f"{idx:02d}_{tab}.png", manifest, "08. Security Agency Portal", f"Tab: {title}")

            # 9. SuperAdmin Governance Console
            open_portal(dp, base_url, "/admin", tokens["admin"])
            for idx, (tab, title) in enumerate([
                ("overview", "Executive Overview"),
                ("pending", "Property & Equipment Audits"),
                ("warehouses", "Master Warehouse Registry"),
                ("bookings", "Client Leases"),
                ("incharges", "Incharge Staff"),
                ("logs", "Facility Shift Logs"),
                ("fleet-radar", "Fleet Telemetry Radar"),
                ("payouts", "Owner Payouts Ledger"),
                ("invoices", "IRD VAT Invoices"),
                ("tariff-margin", "Freight Tariff & Margin"),
                ("maintenance-holds", "Holds & Delisting Queue"),
                ("lien-auctions", "60-Day Lien & Auctions"),
                ("insurance", "Stock Insurance & Claims"),
                ("users", "User Directory & SMS Outbox"),
            ], 1):
                click_safe(dp, f"switchTab('{tab}')")
                snap(dp, OUT_DIR / "09_admin", f"{idx:02d}_{tab}.png", manifest, "09. SuperAdmin Governance Console", f"Tab: {title}")

            if click_safe(dp, "openProvisionModal()"):
                snap(dp, OUT_DIR / "09_admin", "15_modal_provision_incharge.png", manifest, "09. SuperAdmin Governance Console", "Modal: Provision Warehouse Incharge")
                click_safe(dp, "closeProvisionModal()")
        finally:
            browser.close()
    server.should_exit = True
    build_gallery_html(manifest)
    print(f"\nDONE! Captured {len(manifest)} screenshots into: {OUT_DIR}")
    print(f"Open gallery: {(OUT_DIR / 'index.html')}")


if __name__ == "__main__":
    main()
