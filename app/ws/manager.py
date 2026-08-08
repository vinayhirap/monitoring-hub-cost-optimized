# app/ws/manager.py
from fastapi import WebSocket
from typing import Dict, List
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {
            "overview": [],
            "alerts": [],
            "metrics": [],
        }

    async def connect(self, websocket: WebSocket, channel: str = "overview"):
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        self.active_connections[channel].append(websocket)
        logger.info(f"WS connected: channel={channel}")

    def disconnect(self, websocket: WebSocket, channel: str = "overview"):
        if channel in self.active_connections:
            try:
                self.active_connections[channel].remove(websocket)
            except ValueError:
                pass
        logger.info(f"WS disconnected: channel={channel}")

    async def broadcast(self, channel: str, data: dict):
        if channel not in self.active_connections:
            return
        dead = []
        message = json.dumps(data)
        for ws in self.active_connections[channel]:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self.active_connections[channel].remove(ws)
            except ValueError:
                pass

    async def broadcast_all(self, data: dict):
        for channel in self.active_connections:
            await self.broadcast(channel, data)

    def connection_count(self) -> dict:
        return {ch: len(conns) for ch, conns in self.active_connections.items()}


ws_manager = ConnectionManager()