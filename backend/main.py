"""
Kathmandu Warehousing & Distribution Center (KTM-WDC)
FastAPI Main Application Entry Point
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from backend.config import settings
from backend.database import init_db_if_needed, get_db_info, get_db
from backend.routers import auth, warehouses, admin, incharge, fleet, insurance, maps, uploads, equipment, security
from backend.services.overdue_monitor import run_overdue_sweep
from backend.services.sms_service import get_sms_provider_mode

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Safe startup initialization without circular imports
    init_db_if_needed()
    yield

app = FastAPI(
    title=settings.APP_NAME,
    description="Decentralized Commercial Warehousing, Fleet Telemetry & IRD FinTech Exchange for Nepal",
    version="1.0.0",
    lifespan=lifespan
)

# Mount Routers
app.include_router(auth.router)
app.include_router(warehouses.router)
app.include_router(admin.router)
app.include_router(incharge.router)
app.include_router(fleet.router)
app.include_router(insurance.router)
app.include_router(maps.router)
app.include_router(uploads.router)
app.include_router(equipment.router)
app.include_router(security.router)

# Ensure DB schema extensions & seed accounts run on serverless / TestClient imports too
init_db_if_needed()

# Template Engine & Static Files with Robust Vercel Paths
current_dir = os.path.dirname(os.path.abspath(__file__)) # .../backend
BASE_DIR = os.path.dirname(current_dir) # .../project-warehouse

template_candidates = [
    os.path.join(BASE_DIR, "frontend", "templates"),
    os.path.join(os.getcwd(), "frontend", "templates"),
    os.path.join(os.path.dirname(os.getcwd()), "frontend", "templates"),
]
template_dir = next((d for d in template_candidates if os.path.isdir(d)), template_candidates[0])
templates = Jinja2Templates(directory=template_dir)

# Static Directory (Safe for Serverless)
static_candidates = [
    os.path.join(BASE_DIR, "frontend", "static"),
    os.path.join(os.getcwd(), "frontend", "static"),
]
static_dir = next((d for d in static_candidates if os.path.isdir(d)), static_candidates[0])
try:
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
except Exception as e:
    print("Static files mount warning (harmless on serverless):", e)

# ---------------------------------------------------------------------------
# WebSocket Telemetry Stream Manager
# ---------------------------------------------------------------------------
class TelemetryManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_gps(self, data: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                pass

telemetry_manager = TelemetryManager()

@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    await telemetry_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await telemetry_manager.broadcast_gps(data)
    except WebSocketDisconnect:
        telemetry_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Frontend Page Renderers (Native v0 Design System & Executive Admin)
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
@app.get("/signin", response_class=HTMLResponse)
@app.get("/register", response_class=HTMLResponse)
@app.get("/signup", response_class=HTMLResponse)
def index_page(request: Request):
    return templates.TemplateResponse(request=request, name="v0/home.html", context={"app_name": settings.APP_NAME})

@app.get("/marketplace", response_class=HTMLResponse)
@app.get("/client", response_class=HTMLResponse)
def client_dashboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="client_dashboard.html", context={"app_name": settings.APP_NAME})

@app.get("/owner", response_class=HTMLResponse)
def owner_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="owner_dashboard.html", context={"app_name": settings.APP_NAME})

@app.get("/incharge", response_class=HTMLResponse)
def incharge_page(request: Request):
    return templates.TemplateResponse(request=request, name="incharge_dashboard.html", context={"app_name": settings.APP_NAME})

@app.get("/fleet", response_class=HTMLResponse)
def fleet_page(request: Request):
    return templates.TemplateResponse(request=request, name="fleet_dashboard.html", context={"app_name": settings.APP_NAME})

@app.get("/driver", response_class=HTMLResponse)
def driver_page(request: Request):
    return templates.TemplateResponse(request=request, name="driver_run.html", context={"app_name": settings.APP_NAME})

@app.get("/equipment", response_class=HTMLResponse)
def equipment_page(request: Request):
    return templates.TemplateResponse(request=request, name="equipment_dashboard.html", context={"app_name": settings.APP_NAME})

@app.get("/invoice", response_class=HTMLResponse)
def invoice_page(request: Request):
    return templates.TemplateResponse(request=request, name="v0/invoice.html", context={"app_name": settings.APP_NAME})

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse(request=request, name="admin_dashboard.html", context={"app_name": settings.APP_NAME})

@app.get("/security", response_class=HTMLResponse)
def security_page(request: Request):
    return templates.TemplateResponse(request=request, name="security_dashboard.html", context={"app_name": settings.APP_NAME})

@app.get("/api/cron/overdue-sweep")
def cron_overdue_sweep(
    authorization: str = Header(default=""),
    x_cron_secret: str = Header(default=""),
    db: Session = Depends(get_db)
):
    """Scheduled automation endpoint (Vercel Cron / external scheduler) for daily lien & holdover stock checks."""
    if settings.CRON_SECRET:
        provided = x_cron_secret.strip() or authorization.replace("Bearer ", "").strip()
        if provided != settings.CRON_SECRET:
            raise HTTPException(status_code=401, detail="Invalid cron authorization secret.")
    actions = run_overdue_sweep(db)
    return {
        "status": "completed",
        "actions_triggered": len(actions),
        "actions": actions,
    }

@app.get("/health")
def health_check():
    db_info = get_db_info()
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "database": db_info["label"],
        "database_engine": db_info["engine"],
        "is_sqlite_fallback": db_info["is_sqlite"],
        "allow_demo_shortcuts": settings.ALLOW_DEMO_SHORTCUTS,
        "sms_provider": get_sms_provider_mode(),
        "holding_liability": "Rs. 0 (Enforced)",
        "nepal_vat_rate": "13% Statutory IRD Schedule 13"
    }
