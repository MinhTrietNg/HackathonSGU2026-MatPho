"""
WebSocket Connection & Room Manager for Mắt Phố Realtime Telemetry
Points 5, 6, 7: Heartbeat with fps, AI_VERIFYING with sign/confidence/steps, FIRE_ALERT_SUPPRESSED, Two-Tier Escalation
"""

import json
import time
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
        # edge_id -> { "public_hls_base_url": str, "cameras": List[str], "last_seen": float }
        self.edge_registry: Dict[str, Dict[str, Any]] = {}
        # request_id -> asyncio.Future (for duplex RPC like PROBE_CAMERA -> PROBE_RESULT)
        self.pending_edge_requests: Dict[str, Any] = {}

    async def request_from_edge(
        self,
        edge_id: str,
        message: Dict[str, Any],
        timeout_s: float = 4.5,
    ) -> Optional[Dict[str, Any]]:
        """Send a request with request_id to Edge Node and await its response over WebSocket."""
        import asyncio
        import uuid
        req_id = message.get("request_id") or f"req_{uuid.uuid4().hex[:10]}"
        message["request_id"] = req_id
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self.pending_edge_requests[req_id] = fut
        try:
            sent = await self.send_to_edge(edge_id, message)
            if not sent:
                return None
            return await asyncio.wait_for(fut, timeout=timeout_s)
        except Exception:
            return None
        finally:
            self.pending_edge_requests.pop(req_id, None)

    def resolve_edge_response(self, request_id: str, data: Dict[str, Any]) -> bool:
        """Complete a pending future when Edge Node returns PROBE_RESULT or command response."""
        fut = self.pending_edge_requests.get(request_id)
        if fut and not fut.done():
            fut.set_result(data)
            return True
        return False

    def register_edge_node(
        self,
        edge_id: str,
        public_hls_base_url: Optional[str] = None,
        cameras: Optional[List[str]] = None,
    ):
        """Update active Edge Node metadata from WebSocket handshake or heartbeat."""
        now = time.time()
        record = self.edge_registry.get(edge_id, {})
        if public_hls_base_url:
            record["public_hls_base_url"] = public_hls_base_url.rstrip("/")
        if cameras is not None:
            record["cameras"] = cameras
        record["last_seen"] = now
        self.edge_registry[edge_id] = record
        logger.info(
            f"Edge node registered: {edge_id} (HLS Gateway: {record.get('public_hls_base_url')}, {len(record.get('cameras', []))} cameras)"
        )

    def get_edge_public_hls_url(self, edge_id: str) -> Optional[str]:
        """Return the public HLS base URL of an active Edge node."""
        node = self.edge_registry.get(edge_id)
        if node and node.get("public_hls_base_url"):
            return node["public_hls_base_url"]
        return None

    def get_edge_for_camera(self, cam_id: str) -> Optional[str]:
        """Find the edge_id managing this cam_id."""
        for edge_id, node in self.edge_registry.items():
            if cam_id in node.get("cameras", []):
                return edge_id
        return None

    async def send_to_edge(self, edge_id: str, message: Dict[str, Any]) -> bool:
        """Send command JSON message to a connected Edge node via its dedicated room."""
        room = f"edge_{edge_id}"
        if room in self.rooms and len(self.rooms[room]) > 0:
            await self.broadcast_to_room(room, message)
            return True
        return False

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
