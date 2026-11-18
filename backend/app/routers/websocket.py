from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.tracking_manager import tracking_manager

router = APIRouter(tags=["Realtime Telemetry"])

@router.websocket("/ws/tracking/{dispatch_id}")
async def websocket_tracking_endpoint(websocket: WebSocket, dispatch_id: int):
    await tracking_manager.connect(dispatch_id, websocket)
    try:
        while True:
            # Drivers or clients stream JSON coordinates: {"latitude": ..., "longitude": ...}
            data = await websocket.receive_json()
            await tracking_manager.broadcast_location(dispatch_id, data)
    except WebSocketDisconnect:
        tracking_manager.disconnect(dispatch_id, websocket)
    except Exception:
        tracking_manager.disconnect(dispatch_id, websocket)
