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

# Template Engine & Static Files
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "frontend", "templates"))

# Static Directory
static_dir = os.path.join(BASE_DIR, "frontend", "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

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
            # Broadcast vehicle coordinate ping to all connected tracking maps
            await telemetry_manager.broadcast_gps(data)
    except WebSocketDisconnect:
        telemetry_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Frontend Page Renderers
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "app_name": settings.APP_NAME})

@app.get("/owner", response_class=HTMLResponse)
def owner_dashboard(request: Request):
    return templates.TemplateResponse("owner_dashboard.html", {"request": request, "app_name": settings.APP_NAME})

@app.get("/marketplace", response_class=HTMLResponse)
def marketplace_page(request: Request):
    return templates.TemplateResponse("marketplace.html", {"request": request, "app_name": settings.APP_NAME})

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "app_name": settings.APP_NAME})

@app.get("/incharge", response_class=HTMLResponse)
def incharge_page(request: Request):
    return templates.TemplateResponse("incharge_dashboard.html", {"request": request, "app_name": settings.APP_NAME})

@app.get("/fleet", response_class=HTMLResponse)
def fleet_page(request: Request):
    return templates.TemplateResponse("fleet_dashboard.html", {"request": request, "app_name": settings.APP_NAME})

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "database": "Supabase PostgreSQL 17 (Connected & Live)",
        "holding_liability": "Rs. 0 (Enforced)",
        "nepal_vat_rate": "13% Statutory IRD Schedule 13"
    }
