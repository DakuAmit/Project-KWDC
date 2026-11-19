import os
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Group
from reportlab.lib import colors

UML_ENTITIES = [
    {
        "id": "entity_1_property_owner",
        "actor": "Warehouse Property Owner",
        "subject": "Commercial Real Estate & Storage Capacity Governance",
        "items": [
            ("Register Commercial Facility", "include", "Configure Open Yard vs Closed Godown"),
            ("Configure Cold Storage Chamber", "extend", "Set Temp (-25°C to 8°C & Humidity)"),
            ("Declare Infrastructure & Safeguards", "include", "Log Road Access, Police, Damkal & Hospital"),
            ("Manage Multi-Tenant Leases", "include", "Partition Space (1 WHS ↔ N Clients)"),
            ("Review & Approve Space Inquiries", "extend", "Issue IRD Schedule 13 (13% VAT) Invoice"),
            ("Contract On-Site Security & Machinery", "extend", "Request Forklift & Licensed Guard Detail"),
            ("Audit Occupancy & Rental Cashflow", None, None)
        ]
    },
    {
        "id": "entity_2_client_shipper",
        "actor": "Enterprise Client (Shipper)",
        "subject": "Logistics Staging & Multi-Modal Freight Execution",
        "items": [
            ("Discover Verified Warehouses", "include", "Filter by Road, Cold Temp & Emergency Sites"),
            ("Lease Partitioned Warehouse Space", "include", "Multi-Warehouse Staging (1 Client ↔ N WHS)"),
            ("Manage QR Pallet Batch Inventory", "extend", "Schedule Outbound Loading Dock Dispatch"),
            ("Book Point-to-Point Freight (No WHS)", "include", "Configure Pickup & Multi-Stop Delivery"),
            ("Monitor Live Transit Telemetry", "include", "Continuous GPS Transit Telemetry"),
            ("Settle IRD 13% VAT Invoices", "extend", "Download Cryptographic Tax PDF Receipt")
        ]
    },
    {
        "id": "entity_3_commercial_driver",
        "actor": "Commercial Driver",
        "subject": "Transit Execution & Telemetry Operations",
        "items": [
            ("Register Vehicle & Bluebook KYC", None, None),
            ("View & Accept Dispatch Orders", None, None),
            ("Warehouse Gate Check-in", "include", "Scan Loading Bay Entry QR Pass"),
            ("Execute Point-to-Point Transit", "include", "Stream Continuous GPS Telemetry"),
            ("Report En-Route Disruptions", "extend", "Alert Dispatch of Landslide / Police Delay"),
            ("Capture Proof of Delivery (POD)", "include", "Upload Cargo Photo & Consignee Signature"),
            ("Audit Driver Wallet & Trip Earnings", None, None)
        ]
    },
    {
        "id": "entity_4_equipment_owner",
        "actor": "Heavy Equipment Owner",
        "subject": "Material Handling Fleet & Machinery Leasing",
        "items": [
            ("Register Heavy Equipment Fleet", "include", "Specify Tonnage & Reach (Forklift/Crane)"),
            ("Configure Rental Rates & Damage Escrow", None, None),
            ("Toggle Machine Availability State", "include", "Set Available / Leased / Maintenance"),
            ("Accept Machinery Booking Requests", "include", "Assign Certified Machine Operator"),
            ("Log Job Demobilization & Inspection", "extend", "Release Escrow & Log Operating Hours"),
            ("Audit Machine Cashflow & Disbursements", None, None)
        ]
    },
    {
        "id": "entity_5_security_agency",
        "actor": "Licensed Security Agency",
        "subject": "Perimeter Guarding & Incident Command",
        "items": [
            ("Register Agency & Government License", None, None),
            ("Manage Guard Personnel Roster (Badge/Rank)", None, None),
            ("Deploy Guards to Warehouse Posts", "include", "Configure Day / Night Shift Schedules"),
            ("Log Security Incidents (Theft/Fire/Intrusion)", "extend", "Escalate & Notify Local Nepal Police Post"),
            ("Generate Monthly Station Guarding Invoices", None, None)
        ]
    }
]

def create_reportlab_uml_diagram(actor_name, subject_name, items, width=504):
    """
    Constructs a native vector ReportLab Drawing flowable for PDF embedding.
    """
    n = len(items)
    row_height = 28
    header_h = 22
    margin_top = 10
    margin_bottom = 10
    subj_h = header_h + (n * row_height) + 16
    total_h = subj_h + margin_top + margin_bottom
    
    d = Drawing(width, total_h)
    
    # 1. Subject Boundary Box
    subj_x = 125
    subj_y = margin_bottom
    subj_w = width - subj_x - 5
    
    # Outer container
    d.add(Rect(subj_x, subj_y, subj_w, subj_h, fillColor=colors.white, strokeColor=colors.HexColor('#CBD5E1'), strokeWidth=1, rx=4, ry=4))
    # Header bar
    d.add(Rect(subj_x, subj_y + subj_h - header_h, subj_w, header_h, fillColor=colors.HexColor('#F8FAFC'), strokeColor=colors.HexColor('#CBD5E1'), strokeWidth=1, rx=4, ry=4))
    # Header text
    d.add(String(subj_x + 10, subj_y + subj_h - 15, subject_name, fontName='Helvetica', fontSize=8, fillColor=colors.HexColor('#334155')))
    
    # 2. Actor Box
    actor_w = 98
    actor_h = 36
    actor_x = 6
    actor_y = subj_y + (subj_h / 2) - (actor_h / 2)
    actor_center_y = actor_y + (actor_h / 2)
    d.add(Rect(actor_x, actor_y, actor_w, actor_h, fillColor=colors.white, strokeColor=colors.HexColor('#94A3B8'), strokeWidth=1, rx=3, ry=3))
    
    # Actor multi-line string
    words = actor_name.split()
    if len(words) > 2:
        l1 = ' '.join(words[:2])
        l2 = ' '.join(words[2:])
        d.add(String(actor_x + (actor_w / 2), actor_y + 20, l1, fontName='Helvetica-Bold', fontSize=7.5, textAnchor='middle', fillColor=colors.HexColor('#0F172A')))
        d.add(String(actor_x + (actor_w / 2), actor_y + 9, l2, fontName='Helvetica-Bold', fontSize=7.5, textAnchor='middle', fillColor=colors.HexColor('#0F172A')))
    else:
        d.add(String(actor_x + (actor_w / 2), actor_y + 13, actor_name, fontName='Helvetica-Bold', fontSize=8, textAnchor='middle', fillColor=colors.HexColor('#0F172A')))
        
    bus_x = 116

    # 3. Use Case Rows
    for i, item in enumerate(items):
        title = item[0]
        rel = item[1] if len(item) > 1 else None
        target = item[2] if len(item) > 2 else None
        
        # Calculate Y for this row (top down)
        row_center_y = (subj_y + subj_h - header_h - 12) - (i * row_height) - (row_height / 2)
        uc_h = 18
        row_y = row_center_y - (uc_h / 2)
        
        # Connector lines from Actor to bus to Use Case
        d.add(Line(actor_x + actor_w, actor_center_y, bus_x, actor_center_y, strokeColor=colors.HexColor('#64748B'), strokeWidth=0.75))
        d.add(Line(bus_x, actor_center_y, bus_x, row_center_y, strokeColor=colors.HexColor('#64748B'), strokeWidth=0.75))
        d.add(Line(bus_x, row_center_y, subj_x + 12, row_center_y, strokeColor=colors.HexColor('#64748B'), strokeWidth=0.75))
        
        # Primary use case oval
        uc_w = 145 if rel else 225
        uc_x = subj_x + 12
        d.add(Rect(uc_x, row_y, uc_w, uc_h, fillColor=colors.white, strokeColor=colors.HexColor('#93C5FD'), strokeWidth=1, rx=9, ry=9))
        d.add(String(uc_x + (uc_w / 2), row_y + 5.5, title, fontName='Helvetica', fontSize=6.5, textAnchor='middle', fillColor=colors.HexColor('#0F172A')))
        
        # Relational extension / inclusion
        if rel and target:
            target_w = 140
            target_x = subj_x + subj_w - target_w - 8
            line_start_x = uc_x + uc_w
            
            # Dashed line
            d.add(Line(line_start_x, row_center_y, target_x, row_center_y, strokeColor=colors.HexColor('#94A3B8'), strokeWidth=0.75, strokeDashArray=[2.5, 2]))
            
            # Pill badge
            pill_w = 30
            pill_h = 10
            pill_x = line_start_x + ((target_x - line_start_x - pill_w) / 2)
            d.add(Rect(pill_x, row_center_y - (pill_h / 2), pill_w, pill_h, fillColor=colors.white, strokeColor=colors.HexColor('#CBD5E1'), strokeWidth=0.5, rx=2, ry=2))
            d.add(String(pill_x + (pill_w / 2), row_center_y - 2.5, rel, fontName='Helvetica-Oblique', fontSize=5.5, textAnchor='middle', fillColor=colors.HexColor('#64748B')))
            
            # Target oval
            d.add(Rect(target_x, row_y, target_w, uc_h, fillColor=colors.white, strokeColor=colors.HexColor('#93C5FD'), strokeWidth=1, rx=9, ry=9))
            d.add(String(target_x + (target_w / 2), row_y + 5.5, target, fontName='Helvetica', fontSize=6.2, textAnchor='middle', fillColor=colors.HexColor('#0F172A')))
            
    return d

def generate_svg_files(output_dir="frontend/images/uml"):
    """
    Renders standalone responsive SVG files for each entity diagram.
    """
    os.makedirs(output_dir, exist_ok=True)
    width = 920
    
    for entity in UML_ENTITIES:
        actor = entity["actor"]
        subject = entity["subject"]
        items = entity["items"]
        eid = entity["id"]
        
        n = len(items)
        row_height = 44
        header_h = 36
        subj_h = header_h + (n * row_height) + 24
        height = subj_h + 40
        
        subj_x = 220
        subj_y = 20
        subj_w = width - subj_x - 20
        
        actor_w = 170
        actor_h = 56
        actor_x = 20
        actor_y = subj_y + (subj_h / 2) - (actor_h / 2)
        actor_center_y = actor_y + (actor_h / 2)
        bus_x = 200
        
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" style="background:#ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#64748b"/>
    </marker>
  </defs>

  <!-- Subject Boundary Box -->
  <rect x="{subj_x}" y="{subj_y}" width="{subj_w}" height="{subj_h}" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.5" rx="6" ry="6"/>
  <rect x="{subj_x}" y="{subj_y}" width="{subj_w}" height="{header_h}" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1" rx="6" ry="6"/>
  <text x="{subj_x + 18}" y="{subj_y + 23}" font-size="13" font-weight="600" fill="#334155">{subject}</text>

  <!-- Actor Box -->
  <rect x="{actor_x}" y="{actor_y}" width="{actor_w}" height="{actor_h}" fill="#ffffff" stroke="#94a3b8" stroke-width="1.5" rx="6" ry="6"/>
  <text x="{actor_x + (actor_w/2)}" y="{actor_center_y + 5}" font-size="13" font-weight="700" fill="#0f172a" text-anchor="middle">{actor}</text>
'''
        for i, item in enumerate(items):
            title = item[0]
            rel = item[1] if len(item) > 1 else None
            target = item[2] if len(item) > 2 else None
            
            row_center_y = subj_y + header_h + 16 + (i * row_height) + (row_height / 2)
            uc_h = 32
            row_y = row_center_y - (uc_h / 2)
            
            # Bus routing
            svg += f'''
  <path d="M {actor_x + actor_w} {actor_center_y} L {bus_x} {actor_center_y} L {bus_x} {row_center_y} L {subj_x + 22} {row_center_y}" fill="none" stroke="#64748b" stroke-width="1.2"/>
'''
            uc_w = 260 if rel else 380
            uc_x = subj_x + 22
            svg += f'''
  <rect x="{uc_x}" y="{row_y}" width="{uc_w}" height="{uc_h}" fill="#ffffff" stroke="#93c5fd" stroke-width="1.5" rx="16" ry="16"/>
  <text x="{uc_x + (uc_w/2)}" y="{row_center_y + 4}" font-size="11.5" font-weight="500" fill="#0f172a" text-anchor="middle">{title}</text>
'''
            if rel and target:
                target_w = 250
                target_x = subj_x + subj_w - target_w - 20
                line_start_x = uc_x + uc_w
                
                pill_w = 56
                pill_h = 20
                pill_x = line_start_x + ((target_x - line_start_x - pill_w) / 2)
                pill_y = row_center_y - (pill_h / 2)
                
                svg += f'''
  <line x1="{line_start_x}" y1="{row_center_y}" x2="{target_x}" y2="{row_center_y}" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4, 3" marker-end="url(#arrow)"/>
  <rect x="{pill_x}" y="{pill_y}" width="{pill_w}" height="{pill_h}" fill="#ffffff" stroke="#cbd5e1" stroke-width="1" rx="4" ry="4"/>
  <text x="{pill_x + (pill_w/2)}" y="{row_center_y + 4}" font-size="10" font-style="italic" fill="#64748b" text-anchor="middle">{rel}</text>
  
  <rect x="{target_x}" y="{row_y}" width="{target_w}" height="{uc_h}" fill="#ffffff" stroke="#93c5fd" stroke-width="1.5" rx="16" ry="16"/>
  <text x="{target_x + (target_w/2)}" y="{row_center_y + 4}" font-size="11" font-weight="500" fill="#0f172a" text-anchor="middle">{target}</text>
'''

        svg += '\n</svg>'
        out_file = os.path.join(output_dir, f"{eid}.svg")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"Generated SVG: {out_file}")

if __name__ == "__main__":
    generate_svg_files()
