import os
import sys
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

sys.path.insert(0, os.path.dirname(__file__))
from generate_uml_diagrams import create_reportlab_uml_diagram, UML_ENTITIES

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and render 'Page X of Y' in footer.
    """
    def __init__(self, *args, **kwargs):
        super(NumberedCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super(NumberedCanvas, self).showPage()
        super(NumberedCanvas, self).save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 755, "KTM-WDC Commercial Logistics & Warehousing Platform | System Architecture & Use Cases")
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.75)
            self.line(54, 747, 558, 747)

        # Footer
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.75)
        self.line(54, 45, 558, 45)
        
        self.drawString(54, 32, "Confidential & Proprietary • KTM-WDC Nepal 2026 • Compliant with Nepal VAT Act 2052")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 32, page_str)
        self.restoreState()


def build_pdf(filename="KTM-WDC_Entity_Use_Cases.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Custom Palette
    c_primary = colors.HexColor("#F97316")   # Brand Orange
    c_navy = colors.HexColor("#0F172A")      # Dark Slate/Navy
    c_slate = colors.HexColor("#334155")     # Body Slate
    c_muted = colors.HexColor("#64748B")     # Muted text
    c_bg_light = colors.HexColor("#F8FAFC")  # Light gray
    c_border = colors.HexColor("#E2E8F0")    # Border gray
    c_green = colors.HexColor("#166534")     # Success green

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=c_navy,
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=16,
        textColor=c_primary,
        spaceAfter=15
    )

    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=13,
        textColor=c_muted,
        spaceAfter=18
    )

    h1_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=19,
        textColor=c_navy,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'SubSectionHeading',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=c_primary,
        spaceBefore=10,
        spaceAfter=6,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13.5,
        textColor=c_slate,
        spaceAfter=6
    )

    bullet_style = ParagraphStyle(
        'BulletText',
        parent=body_style,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=4
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=c_slate
    )

    callout_style = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=c_navy
    )

    story = []

    # ---------------------------------------------------------
    # COVER / HEADER BANNER
    # ---------------------------------------------------------
    story.append(Paragraph("KTM-WDC Commercial Logistics & Warehousing", title_style))
    story.append(Paragraph("Complete UML Use Case & Ecosystem Architectural Specification for All 5 Entities", subtitle_style))
    story.append(Paragraph("<b>Version:</b> 2.4 Enterprise Production &nbsp;|&nbsp; <b>Territory:</b> Federal Democratic Republic of Nepal &nbsp;|&nbsp; <b>Compliance:</b> Inland Revenue Dept (IRD Schedule 13 - 13% VAT)", meta_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_primary, spaceBefore=0, spaceAfter=14))

    # ---------------------------------------------------------
    # ARCHITECTURAL RULES & FOUNDATIONAL PRINCIPLES
    # ---------------------------------------------------------
    story.append(Paragraph("1. Core Architectural Pillars & Relational Modeling", h1_style))
    story.append(Paragraph(
        "KTM-WDC is engineered specifically to resolve the logistical, geographic, regulatory, and multi-tenant challenges of Nepal's commercial distribution corridors. The architecture enforces three non-negotiable operational models:",
        body_style
    ))

    # Rule Callout Box: 1:M and M:N
    rule_text = """
    <b>Pillar 1: Multi-Tenancy & Partitioned Space (1 Warehouse ↔ Multiple Clients & Vice Versa)</b><br/>
    • <b>1 Warehouse to Multiple Clients (Partitioning):</b> A commercial warehouse of e.g. 20,000 sqft can lease partitioned portions to multiple distinct clients simultaneously (e.g., Client A leases 4,000 sqft ambient, Client B leases 6,000 sqft cold store, and 10,000 sqft remains open for new leases).<br/>
    • <b>1 Client to Multiple Warehouses (Distributed Storage):</b> A single client enterprise can hold active storage leases across multiple facilities concurrently (e.g. 3,000 sqft in Kathmandu Valley Depot, 5,000 sqft in Birgunj Dry Port, and 2,000 sqft in Bhairahawa SEZ).
    """
    callout_data = [[Paragraph(rule_text, callout_style)]]
    callout_table = Table(callout_data, colWidths=[504])
    callout_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#FFF7ED")),
        ('BOX', (0, 0), (-1, -1), 1, c_primary),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(callout_table)
    story.append(Spacer(1, 10))

    # Rule Callout Box: Conditional Client Workflow
    workflow_text = """
    <b>Pillar 2: Adaptive Client Fulfillment (Warehouse-Leased vs. Stand-Alone Point-to-Point)</b><br/>
    • <b>Client With Leased Warehouse:</b> Manages inventory, audits QR pallet stocks, schedules direct dispatch from warehouse dock bays, and contracts on-site machinery.<br/>
    • <b>Client Without Leased Warehouse (Ad-Hoc Shipper):</b> Fully empowered to use point-to-point vehicle booking (pickup & delivery), multi-stop routing, live GPS telemetry, and 13% IRD VAT invoicing with zero warehouse lease requirements.
    """
    wf_data = [[Paragraph(workflow_text, callout_style)]]
    wf_table = Table(wf_data, colWidths=[504])
    wf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F0FDF4")),
        ('BOX', (0, 0), (-1, -1), 1, c_green),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(wf_table)
    story.append(Spacer(1, 10))

    # Space & Temperature Matrix Callout
    facility_text = """
    <b>Pillar 3: Atmospheric Controls & Comprehensive Facility Categorization</b><br/>
    • <b>Storage Atmosphere Categories:</b> Open Yard Free Space (heavy cargo/containers), Closed Covered Godown (FMCG/electronics), and Cold Storage Chambers.<br/>
    • <b>Configurable Cold Storage Ranges:</b> Deep Freeze (-25°C to -18°C), Chilled Cold Store (0°C to 4°C), Cool Pharmaceutical Storage (2°C to 8°C), Ambient Controlled (15°C to 25°C).<br/>
    • <b>Essential Nearby Safeguards:</b> Tracked proximity to Police Station, Emergency Hospital, Fire Brigade (Damkal), Fuel Pump, and Commercial Banks.<br/>
    • <b>On-Site Infrastructure:</b> 20ft/40ft container access roads, 24/7 CCTV surveillance, Licensed Security Guards, loading docks, and 3-phase generator backups.
    """
    fac_data = [[Paragraph(facility_text, callout_style)]]
    fac_table = Table(fac_data, colWidths=[504])
    fac_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#3B82F6")),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(fac_table)
    story.append(Spacer(1, 14))

    # ---------------------------------------------------------
    # ENTITY 1: WAREHOUSE PROPERTY OWNER
    # ---------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("2. Entity 1: Warehouse Property Owner (Commercial Real Estate)", h1_style))
    story.append(Paragraph(
        "<b>Role Definition:</b> Owners of commercial real estate who monetize storage space by listing verified facilities, configuring safety parameters, and leasing capacity to multiple enterprise shippers.",
        body_style
    ))
    story.append(Spacer(1, 4))
    story.append(create_reportlab_uml_diagram(
        UML_ENTITIES[0]["actor"],
        UML_ENTITIES[0]["subject"],
        UML_ENTITIES[0]["items"]
    ))
    story.append(Spacer(1, 10))

    po_use_cases = [
        ("UC-PO-01", "Register Commercial Facility", "Enter facility name, physical address, Kataho geocode, and geographic GPS coordinates."),
        ("UC-PO-02", "Configure Storage Type", "Specify storage classification: Open Free Space (Yard) vs. Closed Covered Godown vs. Multi-Story Warehouse vs. Cold Store."),
        ("UC-PO-03", "Configure Cold Storage Ranges", "If cold storage enabled, define precise temperature thresholds (e.g. -20°C to +4°C) and optional humidity control (% RH)."),
        ("UC-PO-04", "Declare Available Infrastructure", "Register access road width (e.g. 30ft container pitch), CCTV camera count, loading dock bays, and three-phase power backup."),
        ("UC-PO-05", "Record Nearby Essential Facilities", "Record verified distances to nearest Police Station, Hospital, Fire Brigade (Damkal), Fuel Station, and Bank/ATM."),
        ("UC-PO-06", "Set Pricing & Allocation Model", "Configure price per sqft/month, minimum lease period (months), and allowable partition increments."),
        ("UC-PO-07", "Review Lease Inquiries", "Inspect incoming space reservations from multiple clients requesting portions of available square footage."),
        ("UC-PO-08", "Approve / Reject Space Lease", "Approve reservation, deducting reserved square footage from available balance and automatically triggering an IRD 13% VAT invoice."),
        ("UC-PO-09", "Monitor Space Occupancy Rate", "Real-time visual gauge of total capacity vs. leased sqft vs. unreserved free space across multi-tenant partitions."),
        ("UC-PO-10", "Contract Licensed Security", "Request and assign licensed security agencies and guard rosters to facility gate and perimeter posts."),
        ("UC-PO-11", "Request Heavy Machinery", "Book material handling equipment (e.g. 3-ton forklift) with operator for client dock loading operations."),
        ("UC-PO-12", "Track Rental Cashflow & Payouts", "Audit collected rental proceeds, view platform commission withholdings, and request bank disbursements.")
    ]

    t_data = [[Paragraph("<b>Use Case ID</b>", table_header_style), Paragraph("<b>Use Case Title</b>", table_header_style), Paragraph("<b>Operational Scope & Description</b>", table_header_style)]]
    for uid, title, desc in po_use_cases:
        t_data.append([Paragraph(uid, table_cell_style), Paragraph(f"<b>{title}</b>", table_cell_style), Paragraph(desc, table_cell_style)])

    po_table = Table(t_data, colWidths=[65, 130, 309])
    po_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_navy),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_bg_light]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(po_table)
    story.append(Spacer(1, 14))

    # ---------------------------------------------------------
    # ENTITY 2: ENTERPRISE CLIENT (SHIPPER / CONSIGNEE)
    # ---------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("3. Entity 2: Enterprise Client (Shipper & Consignee)", h1_style))
    story.append(Paragraph(
        "<b>Role Definition:</b> Enterprise businesses, importers, manufacturers, and trading houses moving commercial goods across Nepal. The platform adaptively serves both warehouse-holding clients and stand-alone logistics shippers.",
        body_style
    ))
    story.append(Spacer(1, 4))
    story.append(create_reportlab_uml_diagram(
        UML_ENTITIES[1]["actor"],
        UML_ENTITIES[1]["subject"],
        UML_ENTITIES[1]["items"]
    ))
    story.append(Spacer(1, 10))

    cl_use_cases = [
        ("UC-CL-01", "Filter Facilities by Proximity & Cold Storage", "Search commercial facilities by Kataho code, city, access road type, temperature range, and nearby emergency facilities."),
        ("UC-CL-02", "Reserve Partitioned Space (Multi-Tenant)", "Lease specific sqft in a facility without requiring full-building takeover (e.g. lease 3,500 sqft in a 15,000 sqft warehouse)."),
        ("UC-CL-03", "Multi-Warehouse Portfolio Management", "Inspect and oversee stock distributed across multiple regional warehouses under a unified client corporate account."),
        ("UC-CL-04", "Direct Point-to-Point Vehicle Booking", "<b>(Non-Warehouse Clients)</b> Book cargo pickup and drop-off transport directly from supplier to retailer without holding warehouse leases."),
        ("UC-CL-05", "Multi-Stop Route Construction", "Configure multi-drop deliveries with specific recipient names, contact numbers, and delivery instructions."),
        ("UC-CL-06", "Dynamic Pricing & VAT Calculation", "Calculate real-time freight pricing enforced by statutory distance margin tiers (10%, 12%, 15%) and 13% Nepal VAT."),
        ("UC-CL-07", "Warehouse Dock Freight Dispatch", "<b>(Warehouse Clients)</b> Schedule outbound cargo dispatch originating directly from their leased warehouse loading bays."),
        ("UC-CL-08", "Consult AI Logistics Copilot (Gemini)", "Obtain sub-second route recommendations, vehicle type selection, and cargo-handling advice for difficult road corridors."),
        ("UC-CL-09", "Live Highway GPS Telemetry", "Monitor truck positions, transit speed, and estimated time of arrival (ETA) via live interactive telemetry maps."),
        ("UC-CL-10", "QR Batch & Pallet Box Inventory", "<b>(Warehouse Clients)</b> Scan, audit, and track inward/outward movement of SKU batches, carton numbers, and expiration dates."),
        ("UC-CL-11", "Book Material Handling Machinery", "Request on-site forklifts, pallet jacks, or cranes with certified operators for cargo destuffing."),
        ("UC-CL-12", "Audit IRD Schedule 13 Tax Invoices", "Inspect official tax invoices detailing Taxable Subtotal, 13% Value Added Tax, and Grand Total."),
        ("UC-CL-13", "Digital Payment Settlement", "Settle tax invoices instantly via eSewa, Khalti, NepalPay QR, or upload signed bank transfer vouchers."),
        ("UC-CL-14", "Download Cryptographic Tax PDF", "Generate and download official IRD-compliant PDF tax receipts embedded with verifiable QR validation tokens.")
    ]

    t_cl_data = [[Paragraph("<b>Use Case ID</b>", table_header_style), Paragraph("<b>Use Case Title</b>", table_header_style), Paragraph("<b>Operational Scope & Description</b>", table_header_style)]]
    for uid, title, desc in cl_use_cases:
        t_cl_data.append([Paragraph(uid, table_cell_style), Paragraph(f"<b>{title}</b>", table_cell_style), Paragraph(desc, table_cell_style)])

    cl_table = Table(t_cl_data, colWidths=[65, 130, 309])
    cl_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_navy),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_bg_light]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(cl_table)
    story.append(Spacer(1, 14))

    # ---------------------------------------------------------
    # ENTITY 3: COMMERCIAL DRIVER
    # ---------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("4. Entity 3: Commercial Driver (Transit Execution & Telemetry)", h1_style))
    story.append(Paragraph(
        "<b>Role Definition:</b> Licensed commercial vehicle operators (pickups, 2-ton, 5-ton, and container trucks) fulfilling point-to-point and warehouse-dock delivery trips across Nepal.",
        body_style
    ))
    story.append(Spacer(1, 4))
    story.append(create_reportlab_uml_diagram(
        UML_ENTITIES[2]["actor"],
        UML_ENTITIES[2]["subject"],
        UML_ENTITIES[2]["items"]
    ))
    story.append(Spacer(1, 10))

    dr_use_cases = [
        ("UC-DR-01", "Vehicle Registration & Bluebook KYC", "Upload driving license, government vehicle bluebook, and vehicle category (pickup, mini-truck, heavy container)."),
        ("UC-DR-02", "Configure Driver Tariff Rates", "Submit daily rate tiers or accept standard regional tariff schedules based on vehicle capacity."),
        ("UC-DR-03", "View & Accept Dispatch Orders", "Inspect available trip requests (pickup address, drop-off stops, total distance, cargo weight, and guaranteed net fare)."),
        ("UC-DR-04", "Warehouse Gate Inward Check-in", "Scan warehouse entry QR code upon arrival at designated storage depot for cargo loading."),
        ("UC-DR-05", "Real-Time Milestone Updates", "Progress trip state sequentially: <i>Assigned → Picked Up → On the Way → Arrived at Stop → Delivered</i>."),
        ("UC-DR-06", "Continuous GPS Telemetry Transmission", "Stream real-time geographic coordinates to central telemetry hub via mobile web/PWA location service."),
        ("UC-DR-07", "Multi-Stop Drop-Off Execution", "Navigate delivery stops in sequential order, verifying consignee identity and recording drop-off timestamps."),
        ("UC-DR-08", "Proof of Delivery (POD) Capture", "Capture mandatory delivery cargo photo and recipient digital signature on glass before clearing stop."),
        ("UC-DR-09", "Report En-Route Disruption", "Signal breakdown, landslide road blockage (e.g. Mugling-Narayanghat corridor), or police inspection delay to dispatcher."),
        ("UC-DR-10", "Driver Wallet & Net Earnings Audit", "View completed delivery ledger, fuel allowance allocations, and net fare balance available for bank payout.")
    ]

    t_dr_data = [[Paragraph("<b>Use Case ID</b>", table_header_style), Paragraph("<b>Use Case Title</b>", table_header_style), Paragraph("<b>Operational Scope & Description</b>", table_header_style)]]
    for uid, title, desc in dr_use_cases:
        t_dr_data.append([Paragraph(uid, table_cell_style), Paragraph(f"<b>{title}</b>", table_cell_style), Paragraph(desc, table_cell_style)])

    dr_table = Table(t_dr_data, colWidths=[65, 130, 309])
    dr_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_navy),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_bg_light]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(dr_table)
    story.append(Spacer(1, 14))

    # ---------------------------------------------------------
    # ENTITY 4: HEAVY EQUIPMENT OWNER & OPERATOR
    # ---------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("5. Entity 4: Heavy Equipment Owner (Machinery Fleet & Leasing)", h1_style))
    story.append(Paragraph(
        "<b>Role Definition:</b> Owners of specialized material handling machinery (forklifts, cranes, pallet jacks, stackers, front loaders) who service warehouse docks and project staging sites.",
        body_style
    ))
    story.append(Spacer(1, 4))
    story.append(create_reportlab_uml_diagram(
        UML_ENTITIES[3]["actor"],
        UML_ENTITIES[3]["subject"],
        UML_ENTITIES[3]["items"]
    ))
    story.append(Spacer(1, 10))

    eq_use_cases = [
        ("UC-EQ-01", "Register Heavy Equipment Fleet", "Register machine name, equipment category (forklift, crane, pallet jack, loader), model year, and serial number."),
        ("UC-EQ-02", "Specify Technical Specifications", "Define lifting capacity (tons), maximum mast reach (meters), fuel/electric type, and tire type (solid/pneumatic)."),
        ("UC-EQ-03", "Configure Rental Rates & Deposit", "Set daily rate, weekly discount rate, monthly rate, and mandatory security deposit for loss/damage protection."),
        ("UC-EQ-04", "Equipment Operational State Toggle", "Update machine live status: <i>Available for Hire, Currently Leased on Job, or Under Scheduled Maintenance</i>."),
        ("UC-EQ-05", "Review Machinery Booking Requests", "Inspect booking requests from clients or warehouse property owners specifying duration, cargo type, and site location."),
        ("UC-EQ-06", "Assign Certified Machine Operator", "Assign a certified operator with valid heavy machinery driving license to accompany equipment to work site."),
        ("UC-EQ-07", "Log Job Completion & Inspection", "Record hours operated, verify machine condition upon demobilization, and release security deposit escrow."),
        ("UC-EQ-08", "Disbursement & Maintenance Records", "Track net rental proceeds deposited into bank account and schedule preventive maintenance logs.")
    ]

    t_eq_data = [[Paragraph("<b>Use Case ID</b>", table_header_style), Paragraph("<b>Use Case Title</b>", table_header_style), Paragraph("<b>Operational Scope & Description</b>", table_header_style)]]
    for uid, title, desc in eq_use_cases:
        t_eq_data.append([Paragraph(uid, table_cell_style), Paragraph(f"<b>{title}</b>", table_cell_style), Paragraph(desc, table_cell_style)])

    eq_table = Table(t_eq_data, colWidths=[65, 130, 309])
    eq_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_navy),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_bg_light]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(eq_table)
    story.append(Spacer(1, 14))

    # ---------------------------------------------------------
    # ENTITY 5: LICENSED SECURITY AGENCY
    # ---------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("6. Entity 5: Licensed Security Agency (Perimeter Guarding & Escort)", h1_style))
    story.append(Paragraph(
        "<b>Role Definition:</b> Government-licensed private security firms providing armed and unarmed security guards, perimeter patrols, and emergency response for high-value warehouse godowns and transit cargo.",
        body_style
    ))
    story.append(Spacer(1, 4))
    story.append(create_reportlab_uml_diagram(
        UML_ENTITIES[4]["actor"],
        UML_ENTITIES[4]["subject"],
        UML_ENTITIES[4]["items"]
    ))
    story.append(Spacer(1, 10))

    sec_use_cases = [
        ("UC-SC-01", "Agency Accreditation & License KYC", "Submit Ministry of Home Affairs security operational license, company registration, and official PAN/VAT certificate."),
        ("UC-SC-02", "Enroll Security Personnel Roster", "Maintain database of certified security guards with citizenship number, badge ID, emergency contact, and rank."),
        ("UC-SC-03", "Deploy Guards to Warehouse Posts", "Assign guard details to specific commercial warehouses (gate security, loading dock monitoring, roving perimeter patrol)."),
        ("UC-SC-04", "Manage Guard Shift Rosters", "Schedule 12-hour day and night shift rotations, recording daily attendance and guard replacement logs."),
        ("UC-SC-05", "Real-Time Incident Reporting", "Log on-site incidents immediately: unauthorized dock intrusion, cargo theft attempt, fire hazard, or physical damage."),
        ("UC-SC-06", "Emergency Police Station Escalation", "Record automated and manual escalation logs dispatching emergency notification to nearest local Nepal Police station."),
        ("UC-SC-07", "Audit CCTV Feeds & Barrier Checks", "Verify integrity of perimeter CCTV surveillance cameras, visitor gate pass logs, and vehicle seal checks."),
        ("UC-SC-08", "Station Guarding Invoicing & Payouts", "Generate monthly guarding service invoices, audit client security payments, and distribute staff remuneration.")
    ]

    t_sec_data = [[Paragraph("<b>Use Case ID</b>", table_header_style), Paragraph("<b>Use Case Title</b>", table_header_style), Paragraph("<b>Operational Scope & Description</b>", table_header_style)]]
    for uid, title, desc in sec_use_cases:
        t_sec_data.append([Paragraph(uid, table_cell_style), Paragraph(f"<b>{title}</b>", table_cell_style), Paragraph(desc, table_cell_style)])

    sec_table = Table(t_sec_data, colWidths=[65, 130, 309])
    sec_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_navy),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_bg_light]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(sec_table)
    story.append(Spacer(1, 14))

    # ---------------------------------------------------------
    # CROSS-ENTITY TRACEABILITY & INTEGRATION MATRIX
    # ---------------------------------------------------------
    story.append(KeepTogether([
        Paragraph("7. Cross-Entity Transactional Traceability Matrix", h1_style),
        Paragraph(
            "The following matrix maps how primary business workflows cross operational boundaries across the 5 entities and the Super Administrator.",
            body_style
        )
    ]))

    matrix_rows = [
        ("Commercial Facility Listing", "Creates facility, sets cold/ambient temp & Kataho", "Discovers in catalog & leases partitioned sqft", "Accesses loading bay on pickup", "Parks machinery on-site", "Guards perimeter", "Audits & approves listing (`warehouses`)"),
        ("Multi-Tenant Space Reservation", "Approves space lease & partitions sqft", "Reserves space & receives IRD VAT invoice", "Receives dispatch cargo at dock", "Supplies forklift to destuff", "Verifies inward pass", "Audits capacity & VAT (`warehouse_requests`)"),
        ("Ad-Hoc Freight Dispatch (No WHS)", "N/A (Direct shipper origin)", "Books point-to-point trip & pays fare", "Accepts order, streams GPS & uploads POD", "N/A", "N/A", "Calculates margin & tracks trip (`dispatch_orders`)"),
        ("Material Handling Lease", "Coordinates dock space", "Hires forklift/crane with operator", "Unloads cargo via machine", "Assigns certified operator & equipment", "Logs machine entry", "Escrows deposit & audits (`equipment_jobs`)"),
        ("Perimeter Security & Incidents", "Contracts guard post", "Monitors cargo safety guarantees", "Checks in at security gate", "Equipment escorted through gate", "Logs incident & notifies police", "Resolves incident report (`security_incidents`)"),
        ("13% IRD VAT Settlement", "Receives rental payout", "Settles invoice via eSewa / Khalti", "Receives net trip fare", "Receives machine hire payout", "Receives guarding fee", "Audits Schedule 13 compliance (`invoices`)")
    ]

    t_mat_data = [[
        Paragraph("<b>Business Workflow</b>", table_header_style),
        Paragraph("<b>Property Owner</b>", table_header_style),
        Paragraph("<b>Client (Shipper)</b>", table_header_style),
        Paragraph("<b>Driver</b>", table_header_style),
        Paragraph("<b>Equipment Owner</b>", table_header_style),
        Paragraph("<b>Security Agency</b>", table_header_style),
        Paragraph("<b>SuperAdmin</b>", table_header_style)
    ]]

    for wflow, po_act, cl_act, dr_act, eq_act, sec_act, adm_act in matrix_rows:
        t_mat_data.append([
            Paragraph(f"<b>{wflow}</b>", table_cell_style),
            Paragraph(po_act, table_cell_style),
            Paragraph(cl_act, table_cell_style),
            Paragraph(dr_act, table_cell_style),
            Paragraph(eq_act, table_cell_style),
            Paragraph(sec_act, table_cell_style),
            Paragraph(adm_act, table_cell_style),
        ])

    matrix_table = Table(t_mat_data, colWidths=[74, 71, 71, 71, 71, 71, 75])
    matrix_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_navy),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_bg_light]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(matrix_table)
    story.append(Spacer(1, 20))

    # Closing signoff block
    signoff_text = """
    <b>Approved for System Implementation:</b> KTM-WDC Commercial Logistics & Warehousing Architecture Committee.<br/>
    <b>Technical Blueprint Reference:</b> FastAPI 2.0.0 / SQLAlchemy 2.0 / Pydantic v2 / Supabase PostgreSQL / IRD Nepal VAT Compliance.
    """
    story.append(Paragraph(signoff_text, meta_style))

    # Build Document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"✅ PDF successfully generated at: {filename}")

if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "KTM-WDC_Entity_Use_Cases.pdf"
    build_pdf(out_path)
