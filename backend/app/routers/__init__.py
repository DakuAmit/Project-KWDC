from app.routers.auth import router as auth_router
from app.routers.portal import router as portal_router
from app.routers.admin import router as admin_router
from app.routers.driver import router as driver_router
from app.routers.property import router as property_router
from app.routers.equipment import router as equipment_router
from app.routers.security import router as security_router
from app.routers.warehouse import router as warehouse_router
from app.routers.dispatch import router as dispatch_router
from app.routers.pickup import router as pickup_router
from app.routers.inventory import router as inventory_router
from app.routers.invoice import router as invoice_router
from app.routers.payment import router as payment_router
from app.routers.ai import router as ai_router
from app.routers.websocket import router as websocket_router

__all__ = [
    "auth_router",
    "portal_router",
    "admin_router",
    "driver_router",
    "property_router",
    "equipment_router",
    "security_router",
    "warehouse_router",
    "dispatch_router",
    "pickup_router",
    "inventory_router",
    "invoice_router",
    "payment_router",
    "ai_router",
    "websocket_router",
]
