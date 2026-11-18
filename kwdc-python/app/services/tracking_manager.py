from typing import Dict, List
from fastapi import WebSocket
import json

class TrackingConnectionManager:
    def __init__(self):
        # Maps dispatch_id -> list of active client/driver WebSockets
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, dispatch_id: int, websocket: WebSocket):
        await websocket.accept()
        if dispatch_id not in self.active_connections:
            self.active_connections[dispatch_id] = []
        self.active_connections[dispatch_id].append(websocket)

    def disconnect(self, dispatch_id: int, websocket: WebSocket):
        if dispatch_id in self.active_connections:
            if websocket in self.active_connections[dispatch_id]:
                self.active_connections[dispatch_id].remove(websocket)
            if not self.active_connections[dispatch_id]:
                del self.active_connections[dispatch_id]

    async def broadcast_location(self, dispatch_id: int, location_data: dict):
        if dispatch_id in self.active_connections:
            message = json.dumps(location_data)
            for connection in self.active_connections[dispatch_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    pass

tracking_manager = TrackingConnectionManager()
