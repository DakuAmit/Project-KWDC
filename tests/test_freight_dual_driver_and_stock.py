"""
End-to-end verification suite for:
1. Zero Freight VAT unified Trip Fare across Client, Fleet Partner, and Driver (COD view) + Commission Ledger
2. Dual Driver Logics:
   - INDEPENDENT_OWNER driver sees vehicle-matching open jobs, can Accept / Bid / Decline
   - COMMERCIAL_3PL logistics-associated driver gets can_bid=False & only sees senior-assigned runs with COD fare
3. Client Catalog base_rate_per_sqft & monthly_rate_per_sqft parity
4. Double-entry Client Stock Movement Ledger (Partial inward, Incharge dock verify, Partial outward, Full clearance)
"""

import random
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal
from backend.auth_utils import get_password_hash
import backend.models as models

client = TestClient(app)


def ensure_user(email: str, full_name: str, phone: str, role: str, fleet_op: str = None) -> int:
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
                fleet_operator_type=fleet_op,
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


def login_token(email: str, password: str = "Password@123") -> dict:
    res = client.post("/api/auth/login", json={"email": email.lower(), "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_freight_dual_driver_and_stock_flow():
    rand_id = random.randint(10000, 99999)
    owner_email = f"own_stk_{rand_id}@kwdc.com.np"
    inc_email = f"inc_stk_{rand_id}@kwdc.com.np"
    cli_email = f"cli_stk_{rand_id}@kwdc.com.np"
    ind_fleet_email = f"ind_flt_{rand_id}@kwdc.com.np"
    corp_fleet_email = f"corp_flt_{rand_id}@kwdc.com.np"

    created_wh_ids = []
    created_order_ids = []
    try:
        ensure_user(owner_email, "Stock Owner", f"98411{rand_id}", "property_owner")
        inc_id = ensure_user(inc_email, "Stock Incharge", f"98412{rand_id}", "warehouse_incharge")
        ensure_user(cli_email, "Stock Client", f"98413{rand_id}", "commercial_client")
        ensure_user(ind_fleet_email, "Solo Pickup Owner", f"98414{rand_id}", "fleet_partner", "INDEPENDENT_OWNER")
        ensure_user(corp_fleet_email, "ABC 3PL Logistics", f"98415{rand_id}", "fleet_partner", "COMMERCIAL_3PL")

        admin_h = login_token("admin@kwdc.com.np", "Admin@123")
        owner_h = login_token(owner_email)
        inc_h = login_token(inc_email)
        cli_h = login_token(cli_email)
        ind_h = login_token(ind_fleet_email)
        corp_h = login_token(corp_fleet_email)

        # 1. Setup vehicles & drivers for Individual Driver vs Logistics 3PL Driver
        ind_v = client.post("/api/fleet/vehicles", headers=ind_h, json={
            "category": "MINI_TRUCK", "model_name": "Tata Ace", "license_plate": f"Ba 1 Pa {rand_id}",
            "bluebook_number": f"BB-IND-{rand_id}", "payload_capacity_kg": 1500.0
        }).json()["vehicle_id"]
        ind_phone = f"98511{rand_id}"
        client.post("/api/fleet/drivers", headers=ind_h, json={
            "full_name": "Solo Ram Driver", "phone_number": ind_phone, "login_pin": "2233",
            "license_number": f"LIC-IND-{rand_id}", "assigned_vehicle_id": ind_v, "is_self_driver": True
        })

        corp_v = client.post("/api/fleet/vehicles", headers=corp_h, json={
            "category": "MINI_TRUCK", "model_name": "Bolero", "license_plate": f"Ba 2 Pa {rand_id}",
            "bluebook_number": f"BB-CORP-{rand_id}", "payload_capacity_kg": 1500.0
        }).json()["vehicle_id"]
        corp_phone = f"98512{rand_id}"
        corp_d = client.post("/api/fleet/drivers", headers=corp_h, json={
            "full_name": "Staff Shyam Driver", "phone_number": corp_phone, "login_pin": "4455",
            "license_number": f"LIC-CORP-{rand_id}", "assigned_vehicle_id": corp_v
        }).json()["driver_id"]

        ind_drv_h = {"Authorization": f"Bearer {client.post('/api/fleet/driver/login', json={'phone_number': ind_phone, 'pin': '2233'}).json()['access_token']}"}
        corp_drv_h = {"Authorization": f"Bearer {client.post('/api/fleet/driver/login', json={'phone_number': corp_phone, 'pin': '4455'}).json()['access_token']}"}

        # 2. Client posts two open orders: matching MINI_TRUCK & non-matching SIX_WHEELER
        o_match_res = client.post("/api/fleet/client-orders", headers=cli_h, json={
            "movement_type": "DIRECT_HAUL", "cargo_description": "Carton Boxes", "required_vehicle_category": "mini_truck",
            "pickup_address": "Balaju", "pickup_contact_name": "A", "pickup_contact_phone": "9800000001",
            "destination_address": "Kalanki", "consignee_name": "B", "consignee_phone": "9800000002",
            "estimated_distance_km": 10, "cargo_weight_kg": 800, "client_offered_fare_npr": 2500.0
        }).json()
        assert o_match_res["vat_13_percent_npr"] == 0.0
        assert o_match_res["total_fare_npr"] == 2500.0
        o_match_id = o_match_res["order_id"]
        created_order_ids.append(o_match_id)

        o_heavy_id = client.post("/api/fleet/client-orders", headers=cli_h, json={
            "movement_type": "DIRECT_HAUL", "cargo_description": "Heavy Steel", "required_vehicle_category": "six_wheeler",
            "pickup_address": "Chobhar", "pickup_contact_name": "A", "pickup_contact_phone": "9800000001",
            "destination_address": "Koteshwor", "consignee_name": "B", "consignee_phone": "9800000002",
            "estimated_distance_km": 12, "cargo_weight_kg": 5000, "client_offered_fare_npr": 7000.0
        }).json()["order_id"]
        created_order_ids.append(o_heavy_id)

        # Dual driver feed assertions:
        ind_feed = client.get("/api/fleet/driver/available-jobs", headers=ind_drv_h).json()
        assert ind_feed["driver_mode"] == "INDEPENDENT_OWNER" and ind_feed["can_bid"] is True
        assert any(j["id"] == o_match_id for j in ind_feed["jobs"])
        assert not any(j["id"] == o_heavy_id for j in ind_feed["jobs"])  # non-matching vehicle filtered out!

        corp_feed = client.get("/api/fleet/driver/available-jobs", headers=corp_drv_h).json()
        assert corp_feed["driver_mode"] == "COMMERCIAL_3PL" and corp_feed["can_bid"] is False
        assert corp_feed["jobs"] == []
        # Logistics driver blocked from self-accepting
        assert client.post(f"/api/fleet/driver/jobs/{o_match_id}/accept", headers=corp_drv_h).status_code == 403

        # Independent driver can raise fare (counter-offer) OR decline OR accept -> test counter-offer + decline
        bid_res = client.post(f"/api/fleet/driver/jobs/{o_match_id}/counter-offer", headers=ind_drv_h, json={"offered_fare_npr": 2700.0})
        assert bid_res.status_code == 200
        dec_res = client.post(f"/api/fleet/driver/jobs/{o_match_id}/decline", headers=ind_drv_h)
        assert dec_res.status_code == 200
        ind_after_dec = client.get("/api/fleet/driver/available-jobs", headers=ind_drv_h).json()["jobs"]
        assert not any(j["id"] == o_match_id for j in ind_after_dec)

        # Logistics company accepts the job and assigns Staff Shyam Driver -> Staff driver sees COD fare!
        assert client.post(f"/api/fleet/dispatch-orders/{o_match_id}/accept", headers=corp_h).status_code == 200
        assert client.post(f"/api/fleet/orders/{o_match_id}/assign?vehicle_id={corp_v}&driver_id={corp_d}", headers=corp_h).status_code == 200
        corp_trip = client.get("/api/fleet/driver/active-trip", headers=corp_drv_h).json()["trip"]
        assert corp_trip["id"] == o_match_id
        assert corp_trip["agreed_fare_npr"] == 2500.0  # Exact same Net Trip Fare for COD!

        # Fleet Commission settle check
        earn = client.get("/api/fleet/earnings", headers=corp_h).json()
        assert earn["total_gross_npr"] == 2500.0
        assert earn["commission_due_to_kwdc_npr"] > 0
        assert earn["net_fleet_earnings_npr"] == round(2500.0 - earn["kwdc_platform_fee_npr"], 2)
        assert client.post("/api/fleet/commission/settle", headers=corp_h).status_code == 200
        earn_after = client.get("/api/fleet/earnings", headers=corp_h).json()
        assert earn_after["commission_due_to_kwdc_npr"] == 0.0

        # 3. Client Catalog Rate + Double-Entry Stock Ledger + Partial & Full Clear
        wh_id = client.post("/api/warehouses/list-space", headers=owner_h, json={
            "title": f"Stock Test Godown {rand_id}", "space_type": "COVERED_GODOWN",
            "input_unit": "SQFT", "input_value": 5000, "monthly_rate_per_sqft": 25.0, "road_access_ft": 24.0
        }).json()["warehouse_id"]
        created_wh_ids.append(wh_id)
        client.post(f"/api/admin/warehouses/{wh_id}/assign-incharge", headers=admin_h, json={"incharge_id": inc_id})
        client.post(f"/api/admin/warehouses/{wh_id}/set-tariff", headers=admin_h, json={"client_rate_per_sqft": 35.0})
        client.post(f"/api/admin/warehouses/{wh_id}/approve", headers=admin_h, json={})

        cat_item = [c for c in client.get("/api/warehouses/catalog").json() if c["id"] == wh_id][0]
        assert cat_item["base_rate_per_sqft"] == 35.0 and cat_item["monthly_rate_per_sqft"] == 35.0

        bk_id = client.post("/api/warehouses/book", headers=cli_h, json={
            "warehouse_id": wh_id, "requested_sqft": 1000, "booking_duration_type": "MONTHLY", "duration_value": 2
        }).json()["booking_id"]
        client.post(f"/api/warehouses/bookings/{bk_id}/pay-advance", headers=cli_h)

        # Log 100 units inward -> Incharge verifies -> Partial dispatch 30 -> Clear remaining 70 -> Incharge clears outward
        stk = client.post("/api/warehouses/my-inventory", headers=cli_h, json={
            "warehouse_id": wh_id, "booking_id": bk_id, "item_name": "Solar Batteries", "unit_type": "CARTOON", "quantity": 100
        }).json()
        stk_id = stk["stock_item_id"]

        assert client.post(f"/api/incharge/stock/{stk_id}/verify", headers=inc_h, json={"bay_rack_location": "Zone B / Rack 3"}).status_code == 200
        p_disp = client.post("/api/warehouses/my-inventory/dispatch", headers=cli_h, json={
            "stock_item_id": stk_id, "quantity": 30, "dispatch_mode": "SELF_PICKUP", "vehicle_plate": "Ba 2 Kha 9988"
        })
        assert p_disp.status_code == 200, p_disp.text

        inv_mid = client.get("/api/warehouses/my-inventory", headers=cli_h).json()
        it_mid = [i for i in inv_mid["items"] if i["id"] == stk_id][0]
        assert it_mid["available_quantity"] == 70 and it_mid["reserved_quantity"] == 30

        # Clear remaining 70 via Clear All Stock
        full_disp = client.post("/api/warehouses/my-inventory/dispatch", headers=cli_h, json={
            "booking_id": bk_id, "dispatch_all": True, "dispatch_mode": "SELF_PICKUP"
        })
        assert full_disp.status_code == 200, full_disp.text

        # Incharge clears reserved units at dock
        assert client.post(f"/api/incharge/stock/{stk_id}/verify", headers=inc_h, json={}).status_code == 200
        inv_end = client.get("/api/warehouses/my-inventory", headers=cli_h).json()
        it_end = [i for i in inv_end["items"] if i["id"] == stk_id][0]
        assert it_end["available_quantity"] == 0 and it_end["reserved_quantity"] == 0 and it_end["dispatched_quantity"] == 100
        assert len(inv_end["movements"]) >= 4

        print("[PASS] Zero-VAT unified fares, Dual Driver Logics, Client catalog rates & Double-Entry Stock Ledger verified.")
    finally:
        db = SessionLocal()
        try:
            emails = [owner_email, inc_email, cli_email, ind_fleet_email, corp_fleet_email]
            u_ids = [u.id for u in db.query(models.User).filter(models.User.email.in_(emails)).all()]
            if created_order_ids:
                db.query(models.DriverDismissedOrder).filter(models.DriverDismissedOrder.order_id.in_(created_order_ids)).delete(synchronize_session=False)
                db.query(models.FreightCounterOffer).filter(models.FreightCounterOffer.order_id.in_(created_order_ids)).delete(synchronize_session=False)
                db.query(models.DeliveryStop).filter(models.DeliveryStop.dispatch_order_id.in_(created_order_ids)).delete(synchronize_session=False)
                db.query(models.DispatchOrder).filter(models.DispatchOrder.id.in_(created_order_ids)).delete(synchronize_session=False)
            if u_ids:
                db.query(models.StockMovementLog).filter(models.StockMovementLog.client_id.in_(u_ids)).delete(synchronize_session=False)
                s_ids = [s.id for s in db.query(models.StockItem).filter(models.StockItem.client_id.in_(u_ids)).all()]
                if s_ids:
                    db.query(models.InventoryUnit).filter(models.InventoryUnit.stock_item_id.in_(s_ids)).delete(synchronize_session=False)
                    db.query(models.StockItem).filter(models.StockItem.id.in_(s_ids)).delete(synchronize_session=False)
                db.query(models.GatePass).filter(models.GatePass.client_id.in_(u_ids)).delete(synchronize_session=False)
                db.query(models.Driver).filter(models.Driver.fleet_partner_id.in_(u_ids)).delete(synchronize_session=False)
                db.query(models.Vehicle).filter(models.Vehicle.fleet_partner_id.in_(u_ids)).delete(synchronize_session=False)
            if created_wh_ids:
                b_ids = [b.id for b in db.query(models.WarehouseRequest).filter(models.WarehouseRequest.warehouse_id.in_(created_wh_ids)).all()]
                if b_ids:
                    db.query(models.TaxInvoice).filter(models.TaxInvoice.storage_booking_id.in_(b_ids)).delete(synchronize_session=False)
                    db.query(models.WarehouseRequest).filter(models.WarehouseRequest.id.in_(b_ids)).delete(synchronize_session=False)
                db.query(models.WarehouseActivityLog).filter(models.WarehouseActivityLog.warehouse_id.in_(created_wh_ids)).delete(synchronize_session=False)
                db.query(models.WarehouseInchargeAssignment).filter(models.WarehouseInchargeAssignment.warehouse_id.in_(created_wh_ids)).delete(synchronize_session=False)
                db.query(models.Warehouse).filter(models.Warehouse.id.in_(created_wh_ids)).delete(synchronize_session=False)
            if u_ids:
                db.query(models.User).filter(models.User.id.in_(u_ids)).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    test_freight_dual_driver_and_stock_flow()
