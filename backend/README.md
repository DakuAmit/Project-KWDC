# KTM-WDC (Kathmandu Warehousing & Distribution Center) - Python Edition

> **Enterprise Commercial Logistics, Warehousing & Fleet Telemetry Platform for Nepal.**  
> Built with modern **Python 3.12+ (FastAPI, SQLAlchemy 2.0, Pydantic v2, ReportLab, WebSockets)**.

---

## Architecture & System Overview

KTM-WDC unites Nepal's commercial logistics infrastructure across 5 key pillars:
1. **Commercial Warehousing & Cold Storage**: Space discovery, online reservations, ambient/cold storage (-4°C to 6°C), and Kataho Nepal location grid integration.
2. **Freight Dispatch & Live Telemetry**: Multi-stop routing, distance tariff calculation with admin margin tiers (10%, 12%, 15%), and sub-second live GPS tracking via native ASGI WebSockets (`/ws/tracking/{id}`).
3. **Heavy Machinery & Equipment Leasing**: Mobile cranes, forklifts, certified operators, and daily/hourly rental bookings.
4. **Licensed Security Agency Management**: 24/7 guard postings, shift scheduling, and real-time incident reporting with police escalation.
5. **Statutory Tax & Financial Engine**: Official Nepal Inland Revenue Department (IRD) Schedule 13 compliant 13% VAT tax invoicing, PDF generation with verification QR codes, and multi-gateway digital settlement (eSewa, Khalti, Stripe, NepalPay).

---

## Quickstart (Run in 1 Minute)

### 1. Install Dependencies
```bash
cd kwdc-python
pip install -r requirements.txt
```

### 2. Launch the Application
```bash
python run.py
```
*The database and all demo accounts are automatically initialized and seeded on first run.*

Visit **`http://127.0.0.1:8000`** in your browser.  
Interactive OpenAPI / Swagger documentation is available at **`http://127.0.0.1:8000/docs`**.

---

## Pre-Seeded Demo Credentials

All seeded accounts share the master password:  
**`KwdcNew2026!`**

| Portal Role | Demo Email Address | Password | Primary Route |
| :--- | :--- | :--- | :--- |
| **Platform Administrator** | `admin.access@kwdc.test` | `KwdcNew2026!` | `/admin` |
| **Enterprise Client / Shipper** | `client.access@kwdc.test` | `KwdcNew2026!` | `/client/dashboard` |
| **Commercial Driver** | `driver.access@kwdc.test` | `KwdcNew2026!` | `/driver/dashboard` |
| **Warehouse / Property Owner** | `property.access@kwdc.test` | `KwdcNew2026!` | `/property-owner/dashboard` |
| **Heavy Equipment Owner** | `equipment.access@kwdc.test` | `KwdcNew2026!` | `/equipment-owner/dashboard` |
| **Licensed Security Agency** | `security.access@kwdc.test` | `KwdcNew2026!` | `/security/dashboard` |

---

## Automated Testing Suite

Execute the test suite to verify routing, auth, pricing, and PDF generation:
```bash
pytest tests/
```
