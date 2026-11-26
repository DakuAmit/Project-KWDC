"""
KTM-WDC Flexible Storage Calculator & 60-Day Warehouseman's Lien / Auction Engine
Handles:
1. 3-Tier Flexible Duration Pricing (DAILY 1-6 days, WEEKLY 1-3 weeks, MONTHLY 1+ months)
2. Advance Payment & Overdue Stage Evaluation
3. Escalating Notification Push Schedule:
   - Month 1 Overdue (Day 30)
   - 15 Days Remaining (Day 45)
   - 7 Days / 1 Week Remaining (Day 53)
   - 5 Days Remaining (Day 55 -> Outbound Gate Freeze)
   - 2 Days / 48 Hours Remaining (Day 58 -> Final Notice)
   - Day 60 (2 Months Overdue -> Stock Forfeited to KTM-WDC, Space Freed, Moved to Auction Ledger)
"""
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from backend.models import (
    WarehouseRequest, Warehouse, StockItem, StockAuctionItem,
    LienNotificationLog, BookingStatus, PaymentStatus, User
)
from backend.services.email_service import send_email_via_brevo


def calculate_flexible_storage_cost(
    allocated_sqft: float,
    monthly_rate_per_sqft: float,
    booking_duration_type: str = "MONTHLY",
    duration_value: int = 3
) -> Dict[str, Any]:
    """
    Calculates transparent storage cost for DAILY (1-6 days), WEEKLY (1-3 weeks), or MONTHLY (1+ months).
    Short-term staging carries a standard flexibility premium:
    - DAILY: (monthly / 30) * 1.25 per sq ft per day
    - WEEKLY: (monthly / 4) * 1.10 per sq ft per week
    - MONTHLY: standard monthly rate per sq ft per month
    """
    dtype = (booking_duration_type or "MONTHLY").upper()
    val = max(1, int(duration_value or 1))
    rate = float(monthly_rate_per_sqft or 45.0)
    sqft = float(allocated_sqft or 100.0)

    if dtype == "DAILY":
        unit_rate = round((rate / 30.0) * 1.25, 2)
        base_rent = round(sqft * unit_rate * val, 2)
        duration_days = val
        billing_label = f"{val} Day(s) Micro-Staging (100% Advance)"
    elif dtype == "WEEKLY":
        unit_rate = round((rate / 4.0) * 1.10, 2)
        base_rent = round(sqft * unit_rate * val, 2)
        duration_days = val * 7
        billing_label = f"{val} Week(s) Short-Term Hold (100% Advance)"
    else:
        dtype = "MONTHLY"
        unit_rate = rate
        base_rent = round(sqft * rate, 2) # Monthly installment rate
        duration_days = val * 30
        billing_label = f"{val} Month(s) Enterprise Lease (Advance Monthly)"

    margin = round(base_rent * 0.10, 2)
    taxable = base_rent + margin
    vat_13 = round(taxable * 0.13, 2)
    total_bill = round(taxable + vat_13, 2)

    total_contract_value = total_bill if dtype in ("DAILY", "WEEKLY") else round(total_bill * val, 2)

    return {
        "booking_duration_type": dtype,
        "duration_value": val,
        "duration_days": duration_days,
        "unit_rate_per_sqft": unit_rate,
        "base_rent": base_rent,
        "kwdc_margin_amount": margin,
        "vat_13_percent": vat_13,
        "total_bill": total_bill,
        "total_contract_value": total_contract_value,
        "billing_label": billing_label,
        "advance_required_npr": total_bill
    }


STAGE_MESSAGES = {
    "OVERDUE_MONTH_1": (
        "OVERDUE NOTICE (Month 1): Your KTM-WDC warehouse rent is now 30 days overdue. "
        "Under your Master Lease Agreement, the 30-day statutory lien countdown has begun. "
        "Please settle payment immediately to avoid outbound gate freeze and asset forfeiture."
    ),
    "NOTICE_15_DAYS": (
        "URGENT WARNING (15 Days Left): You have 15 days remaining before KTM-WDC exercises its "
        "Warehouseman's Lien under Nepal Muluki Civil Code 2074. Settle arrears promptly."
    ),
    "NOTICE_7_DAYS": (
        "LEGAL DEMAND NOTICE (7 Days Left): Final 1 week remaining before cargo forfeiture. "
        "Unpaid arrears will trigger outbound gate freeze in 48 hours."
    ),
    "GATE_FROZEN_5_DAYS": (
        "SPACE & GATE FROZEN (5 Days Left): Outbound gate passes are now LOCKED. "
        "No inventory may exit the facility until overdue rent is cleared in full."
    ),
    "FINAL_NOTICE_48_HOURS": (
        "FINAL NOTICE (48 Hours Remaining): Your stored inventory will be legally forfeited to KTM-WDC "
        "in 2 days and moved to the public liquidation auction ledger unless full payment is received."
    ),
    "FORFEITED_AUCTION": (
        "LIEN EXECUTED & STOCK FORFEITED: The 60-day grace deadline has expired without settlement. "
        "Ownership of your stored cargo has transferred to KTM-WDC for public auction liquidation, "
        "and your leased floor space has been released."
    )
}


def determine_lien_stage(days_overdue: int, duration_type: str = "MONTHLY") -> str:
    """Maps overdue days to escalating notification stage."""
    if duration_type in ("DAILY", "WEEKLY"):
        # Accelerated demurrage & forfeiture window for short-term overstays (30-day max)
        if days_overdue >= 30:
            return "FORFEITED_AUCTION"
        elif days_overdue >= 28:
            return "FINAL_NOTICE_48_HOURS"
        elif days_overdue >= 25:
            return "GATE_FROZEN_5_DAYS"
        elif days_overdue >= 23:
            return "NOTICE_7_DAYS"
        elif days_overdue >= 15:
            return "NOTICE_15_DAYS"
        elif days_overdue >= 1:
            return "OVERDUE_MONTH_1"
        return "PAYMENT_DUE"
    else:
        # Standard 60-Day (2-Month) Monthly Lease Rule:
        # Month 1 (Day 30) -> 15 days left (Day 45) -> 7 days (Day 53) -> 5 days (Day 55) -> 2 days (Day 58) -> Day 60 Forfeit
        if days_overdue >= 60:
            return "FORFEITED_AUCTION"
        elif days_overdue >= 58:
            return "FINAL_NOTICE_48_HOURS"
        elif days_overdue >= 55:
            return "GATE_FROZEN_5_DAYS"
        elif days_overdue >= 53:
            return "NOTICE_7_DAYS"
        elif days_overdue >= 45:
            return "NOTICE_15_DAYS"
        elif days_overdue >= 30:
            return "OVERDUE_MONTH_1"
        elif days_overdue >= 1:
            return "PAYMENT_DUE"
        return "PAID"


def execute_stock_forfeiture_and_auction(
    db: Session,
    booking: WarehouseRequest,
    admin_notes: Optional[str] = None
) -> StockAuctionItem:
    """
    Day 60 Execution:
    1. Marks booking as FORFEITED_AUCTION and is_forfeited=True, is_gate_frozen=True.
    2. Frees the occupied continuous square footage back into warehouse.available_sqft.
    3. Catalogues the client's stored StockItems in that warehouse as a StockAuctionItem lot.
    """
    existing_auction = db.query(StockAuctionItem).filter(
        StockAuctionItem.booking_id == booking.id
    ).first()
    if existing_auction:
        return existing_auction

    now = datetime.now(timezone.utc)
    booking.advance_payment_status = "FORFEITED_AUCTION"
    booking.is_gate_frozen = True
    booking.is_forfeited = True
    booking.status = BookingStatus.CANCELLED

    # Free warehouse continuous sq ft back to catalog
    wh = booking.warehouse
    if wh:
        wh.available_sqft = min(wh.total_sqft, (wh.available_sqft or 0.0) + (booking.allocated_billed_sqft or 0.0))

    # Gather stored items belonging to client at this warehouse
    stock_items = db.query(StockItem).filter(
        StockItem.client_id == booking.client_id,
        StockItem.warehouse_id == booking.warehouse_id,
        StockItem.total_quantity > 0
    ).all()

    if stock_items:
        summary_parts = [f"{s.total_quantity}x {s.unit_type.value if hasattr(s.unit_type, 'value') else s.unit_type} {s.item_name} (SKU: {s.sku_code})" for s in stock_items]
        item_summary = "; ".join(summary_parts)
        est_valuation = sum(s.total_quantity * 2500.0 for s in stock_items)
    else:
        item_summary = f"Unclaimed {booking.client_intended_use or 'Commercial Merchandise'} stored in {booking.allocated_billed_sqft:,.0f} sq ft block"
        est_valuation = round((booking.total_monthly_bill or 50000.0) * 4.0, 2)

    arrears_owed = round((booking.total_monthly_bill or 0.0) * 2.0, 2)
    reserve_price = max(arrears_owed, round(est_valuation * 0.45, 2))
    lot_num = f"AUC-2083-{booking.id:04d}-{random.randint(10, 99)}"

    auction_item = StockAuctionItem(
        booking_id=booking.id,
        warehouse_id=booking.warehouse_id,
        client_id=booking.client_id,
        lot_number=lot_num,
        item_summary=item_summary,
        estimated_valuation_npr=est_valuation,
        arrears_owed_npr=arrears_owed,
        reserve_price_npr=reserve_price,
        auction_status="CATALOGUED",
        admin_notes=admin_notes or "Forfeited under 60-Day Commercial Warehouseman's Lien clause.",
        forfeited_at=now,
        auction_scheduled_at=now + timedelta(days=7)
    )
    db.add(auction_item)
    db.commit()
    db.refresh(auction_item)
    return auction_item


def push_lien_notification(
    db: Session,
    booking: WarehouseRequest,
    stage: str,
    custom_message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Applies a specific notification stage (e.g. OVERDUE_MONTH_1, NOTICE_15_DAYS, NOTICE_7_DAYS,
    GATE_FROZEN_5_DAYS, FINAL_NOTICE_48_HOURS, FORFEITED_AUCTION), sends Brevo email,
    and executes gate freeze or auction forfeiture where required.
    """
    now = datetime.now(timezone.utc)
    if not booking.overdue_since:
        booking.overdue_since = now - timedelta(days=30)
    if not booking.default_countdown_deadline:
        booking.default_countdown_deadline = booking.overdue_since + timedelta(days=60)

    booking.advance_payment_status = stage
    booking.last_reminder_sent_at = now
    booking.last_reminder_stage = stage

    if stage in ("GATE_FROZEN_5_DAYS", "FINAL_NOTICE_48_HOURS", "FORFEITED_AUCTION"):
        booking.is_gate_frozen = True

    msg = custom_message or STAGE_MESSAGES.get(stage, f"Lease payment status updated to {stage}.")

    client = booking.client
    email_sent = False
    if client and client.email:
        subject = f"[KTM-WDC URGENT] {stage.replace('_', ' ')} - Booking #{booking.id:04d}"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 25px; border: 2px solid #dc2626; border-radius: 10px;">
            <h2 style="color: #991b1b; margin-top: 0;">KTM-WDC Warehouse Lien & Payment Alert</h2>
            <p>Dear <strong>{client.full_name}</strong>,</p>
            <p style="font-size: 14px; line-height: 1.6; color: #1e293b;">{msg}</p>
            <div style="background: #fef2f2; padding: 15px; border-radius: 6px; font-family: monospace; font-size: 12px; margin: 15px 0;">
                <strong>Lease Reference:</strong> KWDC-LEASE-{booking.id:04d}<br>
                <strong>Facility:</strong> {booking.warehouse.title if booking.warehouse else 'Kathmandu Warehouse'}<br>
                <strong>Allocated Space:</strong> {booking.allocated_billed_sqft:,.0f} sq ft<br>
                <strong>Monthly / Installment Due:</strong> NPR {booking.total_monthly_bill:,.2f}<br>
                <strong>Status:</strong> {stage}
            </div>
            <p style="font-size: 12px; color: #64748b;">Log into your Commercial Client Hub to settle dues immediately.</p>
        </div>
        """
        email_sent = send_email_via_brevo(client.email, client.full_name, subject, html)

    log_entry = LienNotificationLog(
        booking_id=booking.id,
        client_id=booking.client_id,
        stage=stage,
        message=msg,
        email_dispatched=email_sent,
        sent_at=now
    )
    db.add(log_entry)

    auction_item = None
    if stage == "FORFEITED_AUCTION":
        auction_item = execute_stock_forfeiture_and_auction(db, booking)
    else:
        db.commit()

    return {
        "booking_id": booking.id,
        "stage": stage,
        "is_gate_frozen": booking.is_gate_frozen,
        "is_forfeited": booking.is_forfeited,
        "email_dispatched": email_sent,
        "auction_lot_number": auction_item.lot_number if auction_item else None,
        "message": msg
    }


def run_overdue_sweep(db: Session) -> List[Dict[str, Any]]:
    """
    Scans all active/unpaid leases that have an overdue_since timestamp and advances
    their reminder stage automatically according to the 15-day, 7-day, 5-day, 2-day, Day-60 rules.
    """
    now = datetime.now(timezone.utc)
    bookings = db.query(WarehouseRequest).filter(
        WarehouseRequest.is_forfeited == False,
        WarehouseRequest.overdue_since != None
    ).all()

    actions_taken = []
    for b in bookings:
        overdue_dt = b.overdue_since
        if overdue_dt.tzinfo is None:
            overdue_dt = overdue_dt.replace(tzinfo=timezone.utc)
        days_overdue = (now - overdue_dt).days
        target_stage = determine_lien_stage(days_overdue, getattr(b, "booking_duration_type", "MONTHLY"))
        if target_stage != b.advance_payment_status and target_stage != "PAID":
            res = push_lien_notification(db, b, target_stage)
            actions_taken.append(res)

    # Check expired leases that still hold remaining stored inventory (Holdover Clearance Alerts)
    now_naive = datetime.utcnow()
    active_leases = db.query(WarehouseRequest).filter(
        WarehouseRequest.is_forfeited == False,
        WarehouseRequest.lease_end_date != None,
        WarehouseRequest.lease_end_date < now_naive
    ).all()
    for lease in active_leases:
        remaining = db.query(StockItem).filter(
            StockItem.client_id == lease.client_id,
            StockItem.warehouse_id == lease.warehouse_id,
            StockItem.total_quantity > 0
        ).all()
        total_rem = sum(int(s.total_quantity or 0) + int(getattr(s, "reserved_quantity", 0) or 0) for s in remaining)
        if total_rem > 0:
            actions_taken.append({
                "booking_id": lease.id,
                "stage": "HOLDOVER_STOCK_ALERT",
                "remaining_units": total_rem,
                "message": f"Lease #{lease.id} ended on {lease.lease_end_date.strftime('%Y-%m-%d')} with {total_rem} unit(s) still in storage. Clear stock or renew lease."
            })

    return actions_taken
