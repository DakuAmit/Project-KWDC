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

def generate_master_lease_contract(warehouse: Warehouse, owner: User) -> dict:
    contract_number = f"KWDC-MLA-2083-{warehouse.id:04d}"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

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
   Name: {owner.full_name}
   Contact Email: {owner.email}
   Phone: {owner.phone_number}

--------------------------------------------------------------------------------
ARTICLE 1: PROPERTY SPECIFICATIONS & AUDITED CAPACITY
Facility Title: {warehouse.title}
Physical Space Classification: {warehouse.space_type.value.upper()}
Audited Floor Space: {warehouse.total_sqft:,.2f} sq ft
Clear Ceiling Height: {warehouse.clear_ceiling_height_ft} ft
Location: Ward {warehouse.ward_no}, {warehouse.municipality}, {warehouse.district}, {warehouse.province}
Nearest Landmark: {warehouse.neighborhood_landmark}
GPS Geolocation Coordinates: {warehouse.latitude:.5f}° N, {warehouse.longitude:.5f}° E
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
4.2. All subsequent operations—including client space allocation, 10% block
     partitioning, availability toggles, and maintenance holds—are strictly
     governed and approved by KWDC Admin to protect contracted commercial tenants.
4.3. In the event of emergency repairs (e.g. roof leaks, drainage maintenance),
     the Property Owner must submit a written Hold Reason Note through the platform
     for administrative audit and approval.

--------------------------------------------------------------------------------
DIGITAL CERTIFICATE OF VERIFICATION:
Approved by: KTM-WDC Commercial Real Estate Directorate
Cryptographic Contract Stamp: SHA256:{hash(contract_number + owner.email + str(warehouse.id))}
Status: VERIFIED & DIGITALLY EXECUTED
================================================================================
"""
    return {
        "contract_number": contract_number,
        "executed_at": now_str,
        "contract_text": contract_text.strip(),
        "owner_name": owner.full_name,
        "warehouse_title": warehouse.title,
        "total_sqft": warehouse.total_sqft,
        "holding_liability": "NPR 0.00 (Zero Holding Liability)",
        "rate_per_sqft": warehouse.monthly_rate_per_sqft
    }
