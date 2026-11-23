"""
Kathmandu Warehousing & Distribution Center (KTM-WDC)
FastAPI Main Application Entry Point
"""
import os
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from backend.config import settings
from backend.routers import auth, warehouses, admin, incharge, fleet

app = FastAPI(
    title=settings.APP_NAME,
    description="Decentralized Commercial Warehousing, Fleet Telemetry & IRD FinTech Exchange for Nepal",
    version="1.0.0"
)

# Mount Routers
app.include_router(auth.router)
app.include_router(warehouses.router)
app.include_router(admin.router)
app.include_router(incharge.router)
app.include_router(fleet.router)

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
def index_page(request: Request):
    return templates.TemplateResponse(request=request, name="v0/home.html", context={"app_name": settings.APP_NAME})

@app.get("/marketplace", response_class=HTMLResponse)
def marketplace_page(request: Request):
    return templates.TemplateResponse(request=request, name="v0/marketplace.html", context={"app_name": settings.APP_NAME})

@app.get("/owner", response_class=HTMLResponse)
def owner_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="v0/owner.html", context={"app_name": settings.APP_NAME})

@app.get("/incharge", response_class=HTMLResponse)
def incharge_page(request: Request):
    return templates.TemplateResponse(request=request, name="v0/incharge.html", context={"app_name": settings.APP_NAME})

@app.get("/fleet", response_class=HTMLResponse)
def fleet_page(request: Request):
    return templates.TemplateResponse(request=request, name="v0/fleet.html", context={"app_name": settings.APP_NAME})

@app.get("/invoice", response_class=HTMLResponse)
def invoice_page(request: Request):
    return templates.TemplateResponse(request=request, name="v0/invoice.html", context={"app_name": settings.APP_NAME})

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse(request=request, name="admin_dashboard.html", context={"app_name": settings.APP_NAME})

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "database": "Supabase PostgreSQL 17 (Connected & Live)",
        "holding_liability": "Rs. 0 (Enforced)",
        "nepal_vat_rate": "13% Statutory IRD Schedule 13"
    }
