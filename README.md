# KTM-WDC (Kathmandu Warehousing & Distribution Center)

Enterprise Commercial Logistics, Warehousing, Freight Telemetry & Heavy Equipment Platform for Nepal.

---

## Decoupled Architecture

The repository is organized into distinct **Frontend** and **Backend** directories, configured for one-click deployment to **Vercel**:

```
Project-KWDC/
├── backend/                    # Python FastAPI Engine & Database Services
│   ├── app/
│   │   ├── core/               # Database, bcrypt, JWT authentication
│   │   ├── models/             # SQLAlchemy 2.0 ORM models
│   │   ├── schemas/            # Pydantic v2 validation models
│   │   ├── services/           # IRD VAT billing, ReportLab PDF, AI, QR, Payment
│   │   ├── routers/            # Modular FastAPI endpoints
│   │   └── main.py             # FastAPI ASGI application
│   ├── seeders/
│   │   └── seed_data.py        # Demo dataset auto-seeder
│   ├── tests/
│   │   └── test_api.py         # Pytest verification suite
│   └── run.py                  # Local backend server runner
│
├── frontend/                   # Decoupled Modern Client Application
│   ├── index.html              # Landing page
│   ├── login.html              # Login with 1-click demo role auto-fill & JWT auth
│   ├── register.html           # Shipper registration
│   ├── dashboard.html          # Dynamic multi-role cockpit (Admin, Client, Driver, etc.)
│   ├── warehouses.html         # Space discovery, cold storage filters, and bookings
│   ├── dispatch.html           # Freight dispatches with live 13% IRD VAT calculation
│   ├── tracking.html           # Leaflet.js live driver GPS map & ASGI telemetry
│   ├── invoices.html           # 13% IRD VAT Tax invoices & eSewa/Khalti checkout
│   ├── privacy.html            # Legal compliance
│   ├── terms.html              # Terms of service
│   ├── css/                    # Apple Cupertino Frosted Glassmorphism styles
│   ├── js/                     # Centralized API service (api.js), Leaflet maps
│   └── package.json
│
├── api/
│   └── index.py                # Vercel Serverless Function entrypoint
├── vercel.json                 # Vercel deployment configuration
└── requirements.txt            # Root dependencies for Vercel Python runtime
```

---

## Vercel Deployment

Deploy directly to Vercel via the CLI or GitHub integration:

```bash
vercel
```

The bundled `vercel.json` automatically:
1. Builds `api/index.py` with `@vercel/python` (handling all `/api/*`, `/docs`, `/openapi.json`).
2. Builds `frontend/**` with `@vercel/static` (handling global static edge delivery).
3. Routes clean URLs (`/login`, `/register`, `/dashboard`, `/warehouses`, `/dispatch`, `/tracking`, `/invoices`).

---

## Local Development

### 1. Run the Python Backend
```bash
cd backend
python run.py
```
- API & Docs: **`http://127.0.0.1:8000/docs`**

### 2. Run the Frontend
You can open `frontend/index.html` in any browser or serve it:
```bash
cd frontend
python -m http.server 3000
```
- Frontend UI: **`http://127.0.0.1:3000`**

---

## Pre-Seeded Demo Credentials

All seeded accounts share the master password: **`KwdcNew2026!`**

| Portal Role | Demo Email Address | Password |
| :--- | :--- | :--- |
| **Platform Administrator** | `admin.access@kwdc.test` | `KwdcNew2026!` |
| **Enterprise Client / Shipper** | `client.access@kwdc.test` | `KwdcNew2026!` |
| **Commercial Driver** | `driver.access@kwdc.test` | `KwdcNew2026!` |
| **Warehouse / Property Owner** | `property.access@kwdc.test` | `KwdcNew2026!` |
| **Heavy Equipment Owner** | `equipment.access@kwdc.test` | `KwdcNew2026!` |
| **Licensed Security Agency** | `security.access@kwdc.test` | `KwdcNew2026!` |
