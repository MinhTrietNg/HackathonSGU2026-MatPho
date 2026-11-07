"""
WebSocket Connection & Room Manager for Mắt Phố Realtime Telemetry
Points 5, 6, 7: Heartbeat with fps, AI_VERIFYING with sign/confidence/steps, FIRE_ALERT_SUPPRESSED, Two-Tier Escalation
"""

import json
import logging
from typing import Dict, Set, Optional, List, Any
from fastapi import WebSocket

logger = logging.getLogger("backend.services.websocket_manager")


class WebSocketConnectionManager:
    """Manages active WebSocket connections and room-based pub/sub broadcasting."""

    def __init__(self):
        # socket -> set of rooms
        self.active_connections: Dict[WebSocket, Set[str]] = {}
        # room -> set of sockets
        self.rooms: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, rooms: Optional[List[str]] = None):
        """Accept incoming WebSocket connection and register rooms."""
        await websocket.accept()
        self.active_connections[websocket] = set()
        if rooms:
            for r in rooms:
                self.join_room(websocket, r)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Disconnect WebSocket and remove from all rooms."""
        if websocket in self.active_connections:
            for room in list(self.active_connections[websocket]):
                if room in self.rooms:
                    self.rooms[room].discard(websocket)
                    if not self.rooms[room]:
                        del self.rooms[room]
            del self.active_connections[websocket]
        logger.info(f"WebSocket disconnected. Remaining connections: {len(self.active_connections)}")

    def join_room(self, websocket: WebSocket, room: str):
        """Add connection to a specific broadcast room."""
        if websocket not in self.active_connections:
            return
        self.active_connections[websocket].add(room)
        if room not in self.rooms:
            self.rooms[room] = set()
        self.rooms[room].add(websocket)

    def leave_room(self, websocket: WebSocket, room: str):
        """Remove connection from a specific room."""
        if websocket in self.active_connections:
            self.active_connections[websocket].discard(room)
        if room in self.rooms:
            self.rooms[room].discard(websocket)

    async def broadcast_to_room(self, room: str, message: Dict[str, Any]):
        """Deliver JSON message to all active WebSockets in a room."""
        if room not in self.rooms:
            return

        dead_sockets = []
        payload_text = json.dumps(message, ensure_ascii=False)
        for ws in list(self.rooms[room]):
            try:
                await ws.send_text(payload_text)
            except Exception as e:
                logger.warning(f"Error sending message to websocket in room {room}: {e}")
                dead_sockets.append(ws)

        for ws in dead_sockets:
            self.disconnect(ws)

    # ==========================================================================
    # DOMAIN BROADCAST HELPERS
    # ==========================================================================

    async def broadcast_camera_heartbeat(
        self,
        cam_id: str,
        group_id: Optional[str] = None,
        status: str = "ONLINE",
        ai_status: str = "SCANNING",
        fps: int = 25,
    ):
        """Broadcast live camera heartbeat with FPS telemetry."""
        msg = {
            "type": "CAMERA_HEARTBEAT",
            "cam_id": cam_id,
            "status": status,
            "ai_status": ai_status,
            "fps": fps,
        }
        await self.broadcast_to_room(f"camera_{cam_id}", msg)
        if group_id:
            await self.broadcast_to_room(f"group_{group_id}", msg)

    async def broadcast_ai_verifying(
        self,
        cam_id: str,
        sign: str,
        confidence: float,
        message: str,
        steps: List[Dict[str, Any]],
        group_id: Optional[str] = None,
    ):
        """Broadcast AI verification telemetry (amber indicator on UI)."""
        msg = {
            "type": "AI_VERIFYING",
            "cam_id": cam_id,
            "sign": sign,
            "confidence": confidence,
            "message": message,
            "steps": steps,
        }
        await self.broadcast_to_room(f"camera_{cam_id}", msg)
        if group_id:
            await self.broadcast_to_room(f"group_{group_id}", msg)

    async def broadcast_fire_alert_suppressed(
        self,
        cam_id: str,
        alert_id: str,
        summary: str,
        detail: str,
        group_id: Optional[str] = None,
    ):
        """Broadcast false-alarm suppression info (Toast E4 without siren)."""
        msg = {
            "type": "FIRE_ALERT_SUPPRESSED",
            "alert_id": alert_id,
            "cam_id": cam_id,
            "summary": summary,
            "detail": detail,
        }
        await self.broadcast_to_room(f"camera_{cam_id}", msg)
        if group_id:
            await self.broadcast_to_room(f"group_{group_id}", msg)

    async def broadcast_fire_alert(
        self,
        group_id: str,
        alert_data: Optional[Dict[str, Any]] = None,
        alert_payload: Optional[Dict[str, Any]] = None,
        escalation_level: int = 0,
    ):
        """
        Two-Tier Fire Alert Broadcaster:
        - escalation_level == 0 (Level 0 / Tier 1): Only group leaders/managers and camera room.
        - escalation_level >= 1 (Level 1 / Tier 2): Broadcast to the ENTIRE group room.
        """
        data = alert_data or alert_payload or {}
        msg = {
            "type": "FIRE_ALERT",
            **data,
            "escalation_level": escalation_level,
        }
        if escalation_level == 0:
            await self.broadcast_to_room(f"group_{group_id}_leaders", msg)
            cam_id = data.get("cam_id")
            if cam_id:
                await self.broadcast_to_room(f"camera_{cam_id}", msg)
        else:
            await self.broadcast_to_room(f"group_{group_id}", msg)

    async def broadcast_fire_alert_updated(
        self,
        group_id: str,
        alert_id: str,
        status: str,
        escalation_level: int = 1,
        resolved_by_name: Optional[str] = None,
        resolved_at: Optional[str] = None,
    ):
        """Broadcast alert resolution / cancellation to silence siren across clients."""
        msg = {
            "type": "FIRE_ALERT_UPDATED",
            "alert_id": alert_id,
            "status": status,
            "escalation_level": escalation_level,
            "resolved_by_name": resolved_by_name,
            "resolved_at": resolved_at,
        }
        await self.broadcast_to_room(f"group_{group_id}", msg)


_ws_manager_instance: Optional[WebSocketConnectionManager] = None


def get_websocket_manager() -> WebSocketConnectionManager:
    global _ws_manager_instance
    if _ws_manager_instance is None:
        _ws_manager_instance = WebSocketConnectionManager()
    return _ws_manager_instance


# Alias
get_ws_manager = get_websocket_manager
