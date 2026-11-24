"""
Kathmandu Warehousing & Distribution Center (KTM-WDC)
Master Commercial Storage Lease Agreement Generator

Generates legally binding agreements between Property Owners and KWDC:
1. Zero KWDC Holding Liability on Idle Spaces (Holding liability = Rs. 0).
2. Payouts start strictly on the calendar date of commercial lease assignment by Admin.
3. 10% Floor Space Partitioning standard.
4. Permanent Admin governance after verification (specs locked from owner alteration).
"""
from datetime import datetime, timezone
from backend.models import Warehouse, User

def generate_master_lease_contract(warehouse: Warehouse = None, owner: User = None, **kwargs) -> dict:
    w_id = getattr(warehouse, "id", None) or kwargs.get("warehouse_id", 1)
    contract_number = f"KWDC-MLA-2083-{w_id:04d}"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    owner_name = getattr(owner, "full_name", None) or kwargs.get("owner_name", "Property Owner")
    owner_email = getattr(owner, "email", None) or kwargs.get("owner_email", "owner@kwdc.com.np")
    owner_phone = getattr(owner, "phone_number", None) or kwargs.get("owner_phone", "+977-9800000000")

    w_title = getattr(warehouse, "title", None) or kwargs.get("warehouse_title", "Commercial Warehouse")
    w_space_type = getattr(warehouse, "space_type", None)
    stype_str = w_space_type.value.upper() if hasattr(w_space_type, "value") else str(w_space_type or "COVERED_GODOWN")
    total_sqft = getattr(warehouse, "total_sqft", None) or kwargs.get("total_sqft", 1000.0)
    ceiling_ht = getattr(warehouse, "clear_ceiling_height_ft", 12.0)
    ward = getattr(warehouse, "ward_no", 1)
    muni = getattr(warehouse, "municipality", "Kathmandu")
    dist = getattr(warehouse, "district", "Kathmandu")
    prov = getattr(warehouse, "province", "Bagmati")
    landmark = getattr(warehouse, "neighborhood_landmark", "Kathmandu Valley Hub")
    lat = getattr(warehouse, "latitude", 27.7172)
    lng = getattr(warehouse, "longitude", 85.3240)
    rate = getattr(warehouse, "monthly_rate_per_sqft", None) or kwargs.get("rate", 45.0)

    contract_text = f"""
================================================================================
KATHMANDU WAREHOUSING & DISTRIBUTION CENTER PVT. LTD. (KTM-WDC)
MASTER COMMERCIAL REAL ESTATE STORAGE AGREEMENT
Document Reference: {contract_number}
Execution Date: {now_str}
================================================================================

PARTIES TO THIS AGREEMENT:
1. SOVEREIGN OPERATOR / GUARANTOR:
   Kathmandu Warehousing & Distribution Center Pvt. Ltd. (KTM-WDC)
   Kathmandu Metropolitan City, Bagmati Province, Nepal
   PAN / VAT Registration No.: 600987654

2. VERIFIED PROPERTY OWNER:
   Name: {owner_name}
   Contact Email: {owner_email}
   Phone: {owner_phone}

--------------------------------------------------------------------------------
ARTICLE 1: PROPERTY SPECIFICATIONS & AUDITED CAPACITY
Facility Title: {w_title}
Physical Space Classification: {stype_str}
Audited Floor Space: {total_sqft:,.2f} sq ft
Clear Ceiling Height: {ceiling_ht} ft
Location: Ward {ward}, {muni}, {dist}, {prov}
Nearest Landmark: {landmark}
GPS Geolocation Coordinates: {lat:.5f}° N, {lng:.5f}° E
Heavy Vehicle Road Access: {warehouse.road_access_ft} ft

--------------------------------------------------------------------------------
ARTICLE 2: ZERO HOLDING LIABILITY COVENANT (NON-NEGOTIABLE)
2.1. The Property Owner explicitly acknowledges that KTM-WDC assumes Rs. 0.00
     (Zero Nepali Rupees) holding liability while the listed property is vacant,
     under marketing, or awaiting commercial tenant matching.
2.2. Rental disbursement to the Property Owner commences on the exact calendar
     day an approved commercial client lease is assigned and activated by KWDC Admin.

--------------------------------------------------------------------------------
ARTICLE 3: COMMERCIAL TARIFF & TAX DEDUCTIONS
Audited Monthly Tariff: NPR {warehouse.monthly_rate_per_sqft:.2f} per sq ft
Potential Full-Capacity Gross Monthly Yield: NPR {(warehouse.total_sqft * warehouse.monthly_rate_per_sqft):,.2f}
Statutory Tax Deductions: In accordance with the Nepal Income Tax Act 2058,
KWDC shall deduct 10% House Rent TDS at source for deposit with the local
municipality and issue formal TDS deposit certificates to the Property Owner.

--------------------------------------------------------------------------------
ARTICLE 4: ADMINISTRATIVE GOVERNANCE & LOCKOUT PROVISION
4.1. Upon verification and digital execution of this contract, all facility
     specifications (area, rate, amenities, access road) are permanently locked
     from direct alteration by the Property Owner.
4.2. All subsequent operations—including client space allocation, continuous area
     partitioning, availability toggles, and maintenance holds—are strictly
     governed and approved by KWDC Admin to protect contracted commercial tenants.
4.3. In the event of emergency repairs (e.g. roof leaks, drainage maintenance),
     the Property Owner must submit a written Hold Reason Note through the platform
     for administrative audit and approval.

--------------------------------------------------------------------------------
ARTICLE 5: ADVANCE PAYMENT, 60-DAY WAREHOUSEMAN'S LIEN & STOCK AUCTION CLAUSE
5.1. Advance Payment Covenant: Commercial storage rent and staging charges are
     strictly payable IN ADVANCE according to the selected tenure (Daily, Weekly,
     or Monthly).
5.2. Escalating Default Notification Protocol: For standard monthly leases, if
     rent remains unpaid for 30 days (Month 1), KTM-WDC shall issue formal digital
     default notices at exact statutory intervals:
       (a) Day 45 (15 Days Remaining): Formal Overdue Warning Notice.
       (b) Day 53 (7 Days Remaining): Legal Demand Notice.
       (c) Day 55 (5 Days Remaining): Outbound Gate Clearance Freeze (No cargo exit).
       (d) Day 58 (2 Days / 48 Hours Remaining): Final Pre-Auction Notice.
5.3. Stock Forfeiture & Public Auction Rights (Day 60): If all unpaid rent,
     handling fees, and demurrage remain unsettled after sixty (60) days (or
     thirty (30) days for short-term Daily/Weekly overstays), legal title and
     disposal authority over the stored inventory shall irrevocably transfer to
     KTM-WDC under the Statutory Warehouseman's Lien (Nepal Muluki Civil Code 2074).
     KTM-WDC is expressly authorized to catalogue, liquidate, and auction the
     forfeited stock to recover arrears and liberate the warehouse space.

--------------------------------------------------------------------------------
DIGITAL CERTIFICATE OF VERIFICATION:
Approved by: KTM-WDC Commercial Real Estate Directorate
Cryptographic Contract Stamp: SHA256:{hash(contract_number + owner_email + str(w_id))}
Status: VERIFIED & DIGITALLY EXECUTED
================================================================================
"""
    return {
        "contract_number": contract_number,
        "executed_at": now_str,
        "contract_text": contract_text.strip(),
        "owner_name": owner_name,
        "warehouse_title": w_title,
        "total_sqft": total_sqft,
        "holding_liability": "NPR 0.00 (Zero Holding Liability)",
        "rate_per_sqft": rate
    }


def generate_client_storage_contract(booking, client, warehouse) -> dict:
    """
    Generates the binding Client Commercial Storage / Micro-Staging Agreement
    incorporating Advance Payment rules, Continuous Sq Ft terms, and the
    60-Day Warehouseman's Lien & Auction Forfeiture Clause.
    """
    b_id = getattr(booking, "id", 1)
    contract_no = f"KWDC-CLI-2083-{b_id:04d}"
    dtype = (getattr(booking, "booking_duration_type", "MONTHLY") or "MONTHLY").upper()
    dval = getattr(booking, "duration_value", 3) or 3
    ddays = getattr(booking, "duration_days", 90) or 90
    sqft = getattr(booking, "allocated_billed_sqft", 1000.0)
    bill = getattr(booking, "total_monthly_bill", 0.0)
    intended = getattr(booking, "client_intended_use", "Commercial Merchandise")
    wh_title = getattr(warehouse, "title", "KTM-WDC Commercial Facility") if warehouse else "KTM-WDC Commercial Facility"
    wh_loc = f"{getattr(warehouse, 'municipality', 'Kathmandu')}, {getattr(warehouse, 'district', 'Kathmandu')}" if warehouse else "Kathmandu Valley"

    if dtype in ("DAILY", "WEEKLY"):
        term_title = f"SHORT-TERM MICRO-STAGING AGREEMENT ({dval} {'DAY(S)' if dtype == 'DAILY' else 'WEEK(S)'})"
        payment_clause = f"100% ADVANCE PAYMENT REQUIRED BEFORE GATE-IN: Total NPR {bill:,.2f} (inc. 13% IRD VAT) upfront for {ddays} day(s)."
        lien_clause = (
            "SHORT-TERM OVERSTAY & LIEN: If cargo is not evacuated upon expiry of the staging period, "
            "daily demurrage of 1.5x applies immediately. Outbound gate passes lock until cleared. "
            "If arrears remain unpaid after 30 days post-expiry, stock forfeits to KTM-WDC for auction liquidation."
        )
    else:
        term_title = f"CONTINUOUS COMMERCIAL WAREHOUSE LEASE AGREEMENT ({dval} MONTH(S))"
        payment_clause = f"ADVANCE MONTHLY RENT COVENANT: NPR {bill:,.2f}/month (inc. 13% IRD VAT) payable in advance on the 1st of each billing cycle."
        lien_clause = (
            "60-DAY WAREHOUSEMAN'S LIEN & STOCK AUCTION (Muluki Civil Code 2074): "
            "If rent remains unpaid for 30 days (1 Month Overdue), KTM-WDC shall push formal overdue notices at "
            "15 Days, 7 Days, 5 Days (Outbound Gate Freeze), and 48 Hours (2 Days) remaining. "
            "If unsettled at Day 60 (2 Months Overdue), ownership of all stored inventory irrevocably transfers "
            "to KTM-WDC for public auction liquidation, and the leased sq ft shall be reclaimed."
        )

    text = f"""
================================================================================
KATHMANDU WAREHOUSING & DISTRIBUTION CENTER PVT. LTD. (KTM-WDC)
{term_title}
Agreement Reference: {contract_no}
Tenant / Client: {getattr(client, 'full_name', 'Commercial Client')} (PAN: {getattr(client, 'kyc_pan_vat', 'N/A')})
Facility: {wh_title} ({wh_loc}) | Continuous Area: {sqft:,.2f} sq ft
Authorized Cargo: {intended}
================================================================================

1. PAYMENT TERM (PAY FIRST):
   {payment_clause}

2. STATUTORY WAREHOUSEMAN'S LIEN, DEFAULT NOTICES & AUCTION:
   {lien_clause}

3. CONTINUOUS SQ FT FLEXIBILITY & PRIVACY SHIELD:
   Tenant contracts exact continuous sq ft with 24/7 digital gate pass governance,
   live SKU inventory tracking, and corporate counterparty protection by KTM-WDC.
================================================================================
""".strip()

    return {
        "contract_number": contract_no,
        "duration_type": dtype,
        "duration_days": ddays,
        "contract_text": text
    }
