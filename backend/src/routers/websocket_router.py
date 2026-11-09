"""
WebSocket Realtime Gateway Router for Mắt Phố (Figma E2a–E2c, F1, F2)
Phase 5: WebSocket Realtime Hub, Two-Tier Isolation & Outbound Edge Duplex Channel
"""

import os
import json
import asyncio
import time
import base64
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from firebase_admin import auth

from ..core.config import settings
from ..models.common import UserRole
from ..services.websocket_manager import get_websocket_manager
from ..services.repositories.user_repo import get_user_repo
from ..services.repositories.group_repo import get_group_repo
from ..services.repositories.camera_repo import get_camera_repo

logger = logging.getLogger("backend.routers.websocket")

router = APIRouter(tags=["WebSocket"])

INTERNAL_API_SECRET_KEY = os.getenv("INTERNAL_API_SECRET_KEY", "secure_internal_key_for_ai_and_worker_communication")


def _extract_user_id_from_token(raw_token: str) -> Optional[str]:
    """Resolves user_id from Bearer token, Firebase Custom Token JWT, or dev token."""
    if not raw_token:
        return None

    # 1. Direct Dev Token
    if raw_token.startswith("usr_"):
        return raw_token

    # 2. Mock token prefix
    if raw_token.startswith("mock_custom_token_"):
        without_prefix = raw_token[len("mock_custom_token_"):]
        return without_prefix.rsplit("_", 1)[0]

    if raw_token == "demo_token":
        return "usr_leader_matpho_01"

    # 3. Firebase ID Token Verification
    try:
        decoded = auth.verify_id_token(raw_token)
        return decoded.get("uid")
    except Exception:
        pass

    # 4. Fallback decode JWT payload (Custom Token or development bearer)
    if raw_token.startswith("eyJ"):
        try:
            parts = raw_token.split(".")
            if len(parts) >= 2:
                payload_b64 = parts[1]
                padding = len(payload_b64) % 4
                if padding:
                    payload_b64 += "=" * (4 - padding)
                payload_data = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
                return payload_data.get("uid") or payload_data.get("user_id") or payload_data.get("sub")
        except Exception as ex:
            logger.debug(f"Failed to decode WebSocket JWT payload: {ex}")

    return None


@router.websocket("/ws")
@router.websocket("/api/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    Primary client WebSocket channel.
    Connects Flutter clients to group rooms, camera telemetry and two-tier fire alerts.
    """
    # Extract token from query or Authorization header
    auth_header = websocket.headers.get("authorization")
    raw_token = None
    if auth_header and auth_header.startswith("Bearer "):
        raw_token = auth_header.split(" ", 1)[1]
    elif token:
        raw_token = token

    user_id = _extract_user_id_from_token(raw_token) if raw_token else None

    if not user_id:
        logger.warning("Rejected WebSocket connection: missing or invalid authentication token.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_repo = get_user_repo()
    user = user_repo.get_user_by_id(user_id)
    if not user:
        logger.warning(f"Rejected WebSocket connection: user {user_id} not found in database.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    group_repo = get_group_repo()
    group_tuples = group_repo.list_groups_for_user(user.user_id)

    # Establish room subscriptions for the user
    rooms = [f"user_{user.user_id}"]
    for g, role, _ in group_tuples:
        rooms.append(f"group_{g.group_id}")
        role_val = role.value if hasattr(role, "value") else str(role)
        if role_val in ("LEADER", "MEMBER_MANAGER"):
            rooms.append(f"group_{g.group_id}_leaders")

    ws_manager = get_websocket_manager()
    await ws_manager.connect(websocket, rooms=rooms)

    # Send handshake acknowledgement
    try:
        await websocket.send_text(
            json.dumps({
                "type": "CONNECTED",
                "user_id": user.user_id,
                "rooms": rooms,
                "timestamp": time.time(),
            }, ensure_ascii=False)
        )
    except Exception as e:
        logger.warning(f"Error sending CONNECTED handshake: {e}")

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "timestamp": time.time()}))
            else:
                try:
                    payload = json.loads(data)
                    msg_type = payload.get("type")
                    if msg_type == "ping":
                        await websocket.send_text(json.dumps({"type": "pong", "timestamp": time.time()}))
                    elif msg_type == "ack":
                        alert_id = payload.get("alert_id")
                        await websocket.send_text(json.dumps({
                            "type": "ack_ok",
                            "alert_id": alert_id,
                            "timestamp": time.time(),
                        }))
                    elif msg_type in ("subscribe", "subscribe_camera"):
                        cam_id = payload.get("cam_id") or payload.get("room", "").replace("camera_", "")
                        if cam_id:
                            cam_repo = get_camera_repo()
                            cam = cam_repo.get_camera(cam_id)
                            permitted = False
                            if cam:
                                member = group_repo.get_member(cam.group_id, user.user_id)
                                if member:
                                    if member.role in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
                                        permitted = True
                                    elif member.role == UserRole.MEMBER and (member.camera_ids is None or cam.cam_id in member.camera_ids):
                                        permitted = True
                            if permitted:
                                target_room = f"camera_{cam_id}"
                                ws_manager.join_room(websocket, target_room)
                                await websocket.send_text(json.dumps({
                                    "type": "SUBSCRIBED",
                                    "room": target_room,
                                    "timestamp": time.time(),
                                }))
                            else:
                                await websocket.send_text(json.dumps({
                                    "type": "ERROR",
                                    "code": "PERMISSION_DENIED",
                                    "message": f"Bạn không có quyền theo dõi camera {cam_id}.",
                                    "timestamp": time.time(),
                                }))
                except Exception:
                    pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket client connection error: {e}")
        ws_manager.disconnect(websocket)


# ==============================================================================
# OUTBOUND EDGE REALTIME CHANNEL (ADR 0012)
# ==============================================================================

@router.websocket("/internal/edge/ws")
@router.websocket("/api/v1/internal/edge/ws")
async def edge_websocket_endpoint(
    websocket: WebSocket,
    edge_id: Optional[str] = Query(None),
    secret: Optional[str] = Query(None),
):
    """
    Dedicated Outbound WebSocket channel for On-Premise Edge Nodes (EdgeAI-MatPho).
    Authenticates via internal secret key and maintains duplex command channel.
    """
    req_secret = secret or websocket.headers.get("x-internal-secret")
    req_edge_id = edge_id or websocket.headers.get("x-edge-id", "edg_unknown")

    if not req_secret or req_secret != INTERNAL_API_SECRET_KEY:
        logger.warning(f"Rejected Edge WebSocket connection from {req_edge_id}: invalid secret.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    ws_manager = get_websocket_manager()
    room_name = f"edge_{req_edge_id}"
    await ws_manager.connect(websocket, rooms=[room_name, "edge_nodes"])
    logger.info(f"Edge Node connected successfully: {req_edge_id} in room {room_name}")

    try:
        await websocket.send_text(
            json.dumps({
                "type": "EDGE_CONNECTED_ACK",
                "edge_device_id": req_edge_id,
                "server_time": time.time(),
            }, ensure_ascii=False)
        )
        # Auto-sync registered cameras from Cloud to Edge Node upon connection
        camera_repo = get_camera_repo()
        edge_cameras = await asyncio.to_thread(
            camera_repo.list_cameras_for_edge_node, req_edge_id
        )
        for c in edge_cameras:
            sync_payload = {
                "action": "SYNC_CAMERA",
                "cam_id": c.cam_id,
                "cam_name": c.cam_name,
                "rtsp_url": c.rtsp_url,
                "watch_area": c.watch_area.model_dump() if c.watch_area else None,
                "is_active": c.is_active,
                "is_ai_enabled": c.is_ai_enabled,
                "ai_mode": c.ai_mode.value if hasattr(c.ai_mode, "value") else str(c.ai_mode or "ALWAYS"),
                "ai_schedules": [s.model_dump(by_alias=True) if hasattr(s, "model_dump") else s for s in (c.ai_schedule or [])],
            }
            await websocket.send_text(json.dumps(sync_payload, ensure_ascii=False))
        if edge_cameras:
            # Full list last: the edge drops cameras deleted while the link was down
            # (their REMOVE_CAMERA never arrived). Sent only after a successful query.
            await websocket.send_text(json.dumps({
                "action": "SYNC_COMPLETE",
                "cam_ids": [c.cam_id for c in edge_cameras],
            }))
            logger.info(f"Auto-synced {len(edge_cameras)} cameras to Edge Node {req_edge_id}")
    except Exception as e:
        logger.warning(f"Error sending EDGE_CONNECTED_ACK or SYNC_CAMERA: {e}")

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "timestamp": time.time()}))
            else:
                try:
                    payload = json.loads(data)
                    msg_type = payload.get("type")
                    if msg_type == "CAMERA_STATUS":
                        cam_id = payload.get("cam_id")
                        st = payload.get("status", "ONLINE")
                        fps = payload.get("fps", 25)
                        if cam_id:
                            await ws_manager.broadcast_camera_heartbeat(
                                cam_id=cam_id,
                                status=st,
                                fps=fps,
                            )
                    elif msg_type in ("EDGE_HEARTBEAT", "EDGE_GATEWAY_ANNOUNCE"):
                        pub_url = payload.get("public_hls_base_url")
                        cams = payload.get("cameras")
                        await asyncio.to_thread(
                            ws_manager.register_edge_node,
                            edge_id=req_edge_id,
                            public_hls_base_url=pub_url,
                            cameras=cams,
                        )
                        logger.debug(f"{msg_type} from Edge {req_edge_id}: {payload.get('active_streams')} active streams, gateway: {pub_url}")
                    elif msg_type == "PROBE_RESULT":
                        req_id = payload.get("request_id")
                        if req_id:
                            ws_manager.resolve_edge_response(req_id, payload.get("data") or payload)
                    elif msg_type == "CAMERA_AI_CONFIG_ACK":
                        cam_id = payload.get("cam_id")
                        logger.info(
                            f"Edge {req_edge_id} applied AI config for {cam_id}: "
                            f"ai_mode={payload.get('ai_mode')}, should_ai_scan_now={payload.get('should_ai_scan_now')}"
                        )
                except Exception as ex:
                    logger.debug(f"Edge message processing exception: {ex}")
    except WebSocketDisconnect:
        logger.info(f"Edge Node disconnected: {req_edge_id}")
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"Edge WebSocket error for {req_edge_id}: {e}")
        ws_manager.disconnect(websocket)
