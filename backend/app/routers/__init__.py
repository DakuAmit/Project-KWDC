from app.routers.auth import router as auth_router
from app.routers.portal import router as portal_router
from app.routers.admin import router as admin_router, api_router as admin_api_router
from app.routers.driver import router as driver_router
from app.routers.property import router as property_router, api_router as property_api_router
from app.routers.equipment import router as equipment_router
from app.routers.security import router as security_router
from app.routers.warehouse import router as warehouse_router, api_router as warehouse_api_router
from app.routers.dispatch import router as dispatch_router, api_router as dispatch_api_router
from app.routers.pickup import router as pickup_router
from app.routers.inventory import router as inventory_router
from app.routers.invoice import router as invoice_router, api_router as invoice_api_router
from app.routers.payment import router as payment_router
from app.routers.ai import router as ai_router, api_router as ai_api_router
from app.routers.websocket import router as websocket_router

__all__ = [
    "auth_router",
    "portal_router",
    "admin_router",
    "admin_api_router",
    "driver_router",
    "property_router",
    "property_api_router",
    "equipment_router",
    "security_router",
    "warehouse_router",
    "warehouse_api_router",
    "dispatch_router",
    "dispatch_api_router",
    "pickup_router",
    "inventory_router",
    "invoice_router",
    "invoice_api_router",
    "payment_router",
    "ai_router",
    "ai_api_router",
    "websocket_router",
]
