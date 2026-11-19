import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.core.database import Base, engine
from seeders.seed_data import seed_database
from app.routers import (
    auth_router,
    portal_router,
    admin_router,
    admin_api_router,
    driver_router,
    property_router,
    equipment_router,
    security_router,
    warehouse_router,
    warehouse_api_router,
    dispatch_router,
    dispatch_api_router,
    pickup_router,
    inventory_router,
    invoice_router,
    invoice_api_router,
    payment_router,
    ai_router,
    ai_api_router,
    websocket_router
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fast, non-blocking startup for serverless
    try:
        from seeders.seed_data import ensure_superadmin
        from app.core.database import SessionLocal
        if settings.ADMIN_EMAIL:
            db = SessionLocal()
            try:
                ensure_superadmin(db)
            finally:
                db.close()
    except Exception as e:
        print(f"Startup synchronization note: {e}")
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Enterprise Commercial Logistics, Warehousing, Freight Telemetry & Heavy Equipment Platform for Nepal",
    version="2.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    # Also mount subdirectories for compatibility with asset paths in HTML
    for subdir in ["css", "js", "build", "images", "flags"]:
        sub_path = os.path.join(static_dir, subdir)
        if os.path.exists(sub_path):
            app.mount(f"/{subdir}", StaticFiles(directory=sub_path), name=subdir)

# Register All Application Routers
app.include_router(auth_router)
app.include_router(portal_router)
app.include_router(admin_router)
app.include_router(admin_api_router)
app.include_router(driver_router)
app.include_router(property_router)
app.include_router(equipment_router)
app.include_router(security_router)
app.include_router(warehouse_router)
app.include_router(warehouse_api_router)
app.include_router(dispatch_router)
app.include_router(dispatch_api_router)
app.include_router(pickup_router)
app.include_router(inventory_router)
app.include_router(invoice_router)
app.include_router(invoice_api_router)
app.include_router(payment_router)
app.include_router(ai_router)
app.include_router(ai_api_router)
app.include_router(websocket_router)

from sqlalchemy.orm import Session
from fastapi import Depends
from app.core.database import get_db

@app.get("/api/health")
def api_health(db: Session = Depends(get_db)):
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
            "environment": settings.ENVIRONMENT
        }
    except Exception as e:
        return {
            "status": "degraded",
            "database_error": str(e)
        }

from app.core.templates import templates

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    return templates.TemplateResponse(
        request=request,
        name="welcome.html",
        context={"user": None, "error": "Requested resource was not found."},
        status_code=404
    )
