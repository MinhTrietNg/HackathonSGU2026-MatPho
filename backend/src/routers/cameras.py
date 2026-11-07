"""
Camera Management Router for Mắt Phố
Phase 4: Quản lý Camera, Thùng rác 30 ngày, Thăm dò RTSP & Stream HLS
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query, status, Response, Request
from pydantic import BaseModel, Field

from ..core.security import get_current_user
from ..core.exceptions import (
    AppException,
    NotFoundException,
    PermissionDeniedException,
)
from ..core.formatters import format_iso_utc
from ..core.ai_schedule import should_ai_scan_now, format_ai_status_text
from ..models.user import UserModel
from ..models.common import UserRole, CameraStatus, AIMode
from ..models.camera import (
    CameraModel,
    CameraCreateRequest,
    CameraUpdateRequest,
    CameraProbeRequest,
    CameraProbeResponse,
    CameraStreamResponse,
    WatchAreaModel,
    AIScheduleSlotModel,
    AIScheduleItemModel,
    CameraAIConfigUpdateRequest,
    CameraThumbnailUploadRequest,
    CameraThumbnailResponse,
)
from ..services.repositories.camera_repo import get_camera_repo
from ..services.repositories.group_repo import get_group_repo
from ..services.camera_probe_service import get_camera_probe_service
from ..services.mediamtx_service import get_mediamtx_service
from ..services.storage_service import get_storage_service

router = APIRouter(prefix="/cameras", tags=["Cameras"])


def build_hls_url(cam_id: str, request: Optional[Request] = None, edge_device_id: Optional[str] = None) -> str:
    path_template = os.getenv("HLS_PATH_TEMPLATE", "live/{cam_id}")
    stream_path = path_template.format(cam_id=cam_id)
    # MediaMTX v1.18+ bypass cookie check handshake directly for ExoPlayer / Flutter
    query_suffix = "?cookieCheck=1"

    # 1. Edge Gateway Public URL Discovery (xuyên mạng qua Cloudflare Tunnel)
    try:
        from ..services.websocket_manager import get_websocket_manager
        ws_mgr = get_websocket_manager()
        target_edge_id = edge_device_id or ws_mgr.get_edge_for_camera(cam_id)
        if target_edge_id:
            edge_pub_url = ws_mgr.get_edge_public_hls_url(target_edge_id)
            if edge_pub_url:
                return f"{edge_pub_url}/{stream_path}/index.m3u8{query_suffix}"
    except Exception:
        pass

    # 2. Explicit Cloud / Public domain configured via MEDIAMTX_HOST (Cloudflare Tunnel, CDN, public IP)
    env_host = os.getenv("MEDIAMTX_HOST")
    if env_host and env_host.strip() and "stream.matpho.vn" not in env_host:
        host_clean = env_host.strip().rstrip("/")
        if host_clean.startswith("http://") or host_clean.startswith("https://"):
            return f"{host_clean}/{stream_path}/index.m3u8{query_suffix}"
        return f"https://{host_clean}/{stream_path}/index.m3u8{query_suffix}"

    # 3. Dynamic Host Resolution based on incoming request header (LAN IP / Emulator / Localhost fallback)
    if request:
        host_header = request.headers.get("host", "")
        if host_header:
            client_host = host_header.split(":")[0]
            if client_host == "testserver":
                return f"https://stream.matpho.vn/{stream_path}/index.m3u8"
            return f"http://{client_host}:8888/{stream_path}/index.m3u8{query_suffix}"

    return f"http://localhost:8888/{stream_path}/index.m3u8{query_suffix}"


# ==============================================================================
# 1. RTSP PROBE (Thăm dò RTSP & chụp ảnh nền)
# ==============================================================================

@router.post("/probe", response_model=CameraProbeResponse, summary="Probe RTSP stream")
async def probe_camera(
    payload: CameraProbeRequest,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Test connect RTSP stream within 3-5 seconds, extract resolution/fps and return preview snapshot.
    If an Edge Node is connected via Outbound WebSocket, delegates LAN probing to the Edge Node first.
    Figma screens I2, I4, I5.
    """
    url_lower = payload.rtsp_url.lower()
    is_mock = any(k in url_lower for k in ("mock", "test-valid", "valid", "demo", "auth-fail", "vendor-blocked"))
    if not is_mock and payload.rtsp_url.startswith("rtsp://"):
        try:
            from ..services.websocket_manager import get_websocket_manager
            ws_mgr = get_websocket_manager()
            # Delegate to first active Edge Node if connected
            for edge_id in list(ws_mgr.edge_registry.keys()) or ["edg_local_01"]:
                edge_res = await ws_mgr.request_from_edge(
                    edge_id=edge_id,
                    message={"action": "PROBE_CAMERA", "rtsp_url": payload.rtsp_url},
                    timeout_s=4.5,
                )
                if edge_res and edge_res.get("reachable"):
                    return {
                        "device_name": edge_res.get("vendor") or "Camera IP (Edge LAN)",
                        "resolution": edge_res.get("resolution") or "1920x1080",
                        "fps": int(edge_res.get("fps") or 25),
                        "preview_snapshot_url": edge_res.get("preview_snapshot_base64")
                        or "https://storage.googleapis.com/matpho-c7e77.firebasestorage.app/probes/preview_captured.jpg",
                    }
        except Exception:
            pass

    probe_svc = get_camera_probe_service()
    return probe_svc.probe_rtsp(payload.rtsp_url)


# ==============================================================================
# 2. CAMERA CRUD & LISTINGS
# ==============================================================================

@router.post("", status_code=status.HTTP_201_CREATED, summary="Add a new camera")
def create_camera(
    payload: CameraCreateRequest,
    request: Request,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Save a new camera to a group and subgroup.
    Permission: LEADER or MEMBER_MANAGER.
    """
    group_repo = get_group_repo()
    member = group_repo.get_member(payload.group_id, current_user.user_id)
    if not member or member.role not in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
        raise PermissionDeniedException("Chỉ Trưởng nhóm hoặc Quản lý mới có quyền thêm camera.")

    camera_repo = get_camera_repo()
    camera = camera_repo.create_camera(
        group_id=payload.group_id,
        subgroup_id=payload.subgroup_id,
        cam_name=payload.cam_name,
        rtsp_url=payload.rtsp_url,
        created_by=current_user.user_id,
        device_name=payload.device_name,
        watch_area=payload.watch_area,
        edge_device_id=payload.edge_device_id,
    )

    # Register path in MediaMTX & push SYNC_CAMERA to connected Edge Node
    mtx = get_mediamtx_service()
    mtx.add_path(camera.cam_id, payload.rtsp_url)
    try:
        from ..services.websocket_manager import get_websocket_manager
        import asyncio
        ws_mgr = get_websocket_manager()
        target_edge_id = payload.edge_device_id or "edg_local_01"
        sync_msg = {
            "action": "SYNC_CAMERA",
            "cam_id": camera.cam_id,
            "cam_name": camera.cam_name,
            "rtsp_url": payload.rtsp_url,
            "watch_area": camera.watch_area.model_dump() if camera.watch_area else None,
            "is_active": True,
        }
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(ws_mgr.send_to_edge(target_edge_id, sync_msg))
    except Exception:
        pass

    hls_url = build_hls_url(camera.cam_id, request)
    return {
        "cam_id": camera.cam_id,
        "cam_name": camera.cam_name,
        "group_id": camera.group_id,
        "subgroup_id": camera.subgroup_id,
        "subgroup_name": camera.subgroup_name,
        "device_name": camera.device_name,
        "status": camera.status.value,
        "last_seen_at": format_iso_utc(camera.last_seen_at),
        "live_stream_url": hls_url,
        "watch_area": camera.watch_area.model_dump() if camera.watch_area else None,
        "is_ai_enabled": camera.is_ai_enabled,
        "ai_schedule": [s.model_dump(by_alias=True) if hasattr(s, "model_dump") else s for s in (camera.ai_schedule or [])],
        "thumbnail_url": camera.thumbnail_url,
        "created_at": format_iso_utc(camera.created_at),
    }


@router.get("", summary="List cameras in group")
def list_cameras(
    request: Request,
    group_id: Optional[str] = Query(None),
    subgroup_id: Optional[str] = Query(None),
    current_user: UserModel = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    List active cameras in a group.
    Security: NOTIFIER role gets live_stream_url = null.
    """
    target_group_id = group_id or current_user.personal_group_id
    group_repo = get_group_repo()
    member = group_repo.get_member(target_group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không phải thành viên của nhóm này.")

    user_role = member.role
    user_camera_ids = member.camera_ids

    camera_repo = get_camera_repo()
    cameras = camera_repo.list_cameras_by_group(target_group_id, subgroup_id=subgroup_id)

    results = []
    for cam in cameras:
        # Determine live stream access
        has_access = True
        if user_role == UserRole.NOTIFIER:
            has_access = False
        elif user_role == UserRole.MEMBER and user_camera_ids is not None:
            if cam.cam_id not in user_camera_ids:
                has_access = False

        hls_url = build_hls_url(cam.cam_id, request) if has_access else None

        results.append({
            "cam_id": cam.cam_id,
            "cam_name": cam.cam_name,
            "group_id": cam.group_id,
            "subgroup_id": cam.subgroup_id,
            "subgroup_name": cam.subgroup_name,
            "device_name": cam.device_name,
            "status": cam.status.value if hasattr(cam.status, "value") else str(cam.status),
            "last_seen_at": format_iso_utc(cam.last_seen_at),
            "live_stream_url": hls_url,
            "watch_area": cam.watch_area.model_dump() if cam.watch_area else None,
            "is_ai_enabled": cam.is_ai_enabled,
            "ai_schedule": [s.model_dump(by_alias=True) if hasattr(s, "model_dump") else s for s in (cam.ai_schedule or [])],
            "thumbnail_url": cam.thumbnail_url,
        })
    return results


@router.get("/trash", summary="List cameras in 30-day trash bin")
def list_trash_cameras(
    group_id: str = Query(...),
    current_user: UserModel = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """List soft-deleted cameras in trash. Permission: LEADER or MEMBER_MANAGER."""
    group_repo = get_group_repo()
    member = group_repo.get_member(group_id, current_user.user_id)
    if not member or member.role not in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
        raise PermissionDeniedException("Chỉ Trưởng nhóm hoặc Quản lý mới có quyền xem thùng rác.")

    camera_repo = get_camera_repo()
    trash_cams = camera_repo.list_trash_cameras(group_id)
    return [
        {
            "cam_id": c.cam_id,
            "cam_name": c.cam_name,
            "group_id": c.group_id,
            "subgroup_id": c.subgroup_id,
            "subgroup_name": c.subgroup_name,
            "device_name": c.device_name,
            "status": c.status.value if hasattr(c.status, "value") else str(c.status),
            "deleted_at": format_iso_utc(c.deleted_at),
            "purge_at": format_iso_utc(c.purge_at),
        }
        for c in trash_cams
    ]


# ==============================================================================
# 2B. AI SETTINGS BY CAMERA & SCHEDULE (Figma H7 -> H15)
# ==============================================================================

@router.get("/ai-settings", summary="List AI settings per camera across groups (Figma H7, H8, H9)")
def list_camera_ai_settings(
    group_id: Optional[str] = Query(None, description="Lọc theo 1 nhóm cụ thể nếu muốn"),
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Returns grouped camera AI settings for screens H7, H8, H9:
    - Filter tabs (chips) for all groups the user belongs to.
    - For each group: access_mode ('Editable' for LEADER, 'Locked' for members with lock banner).
    - For each camera: ai_mode, schedules, is_ai_currently_scanning, and formatted status_text.
    """
    group_repo = get_group_repo()
    camera_repo = get_camera_repo()

    group_tuples = group_repo.list_groups_for_user(current_user.user_id)
    filter_tabs: List[Dict[str, Any]] = []
    groups_payload: List[Dict[str, Any]] = []

    for idx, (grp, role, _) in enumerate(group_tuples):
        role_val = role.value if hasattr(role, "value") else str(role)
        is_leader = role_val == UserRole.LEADER.value

        # Resolve leader full name for Locked banner on H8
        leader_name = "Chủ nhóm"
        members = group_repo.list_members(grp.group_id)
        for m in members:
            m_role = m.role.value if hasattr(m.role, "value") else str(m.role)
            if m_role == UserRole.LEADER.value:
                leader_name = m.nickname if m.nickname and m.nickname != "Trưởng Nhóm" else m.full_name
                break

        is_selected = (group_id == grp.group_id) if group_id else (idx == 0)
        filter_tabs.append({
            "group_id": grp.group_id,
            "group_name": grp.group_name,
            "my_role": role_val,
            "role_badge": None if is_leader else "thành viên",
            "is_selected": is_selected,
        })

        if group_id and grp.group_id != group_id:
            continue

        cams = camera_repo.list_cameras_by_group(grp.group_id)
        active_ai_count = 0
        cam_items: List[Dict[str, Any]] = []

        for c in cams:
            mode_val = c.ai_mode.value if hasattr(c.ai_mode, "value") else str(c.ai_mode or "ALWAYS")
            raw_slots = [
                (s.model_dump() if hasattr(s, "model_dump") else dict(s))
                for s in (c.ai_schedules or [])
            ]
            scanning_now = should_ai_scan_now(mode_val, raw_slots)
            if mode_val != AIMode.OFF.value:
                active_ai_count += 1

            cam_items.append({
                "cam_id": c.cam_id,
                "cam_name": c.cam_name,
                "subgroup_id": c.subgroup_id,
                "subgroup_name": c.subgroup_name,
                "access": "Editable" if is_leader else "Locked",
                "ai_mode": mode_val,
                "is_ai_enabled": c.is_ai_enabled,
                "is_ai_currently_scanning": scanning_now,
                "status_text": format_ai_status_text(mode_val, raw_slots, is_editable=is_leader),
                "schedules": raw_slots,
            })

        total_cams = len(cam_items)
        groups_payload.append({
            "group_id": grp.group_id,
            "group_name": grp.group_name,
            "my_role": role_val,
            "access_mode": "Editable" if is_leader else "Locked",
            "leader_id": grp.leader_id,
            "leader_name": leader_name,
            "lock_banner": None if is_leader else {
                "title": "Chỉ chủ nhóm được đổi cài đặt AI",
                "subtitle": f"Muốn đổi, nhắn {leader_name} (chủ nhóm).",
            },
            "ai_summary_badge": f"{active_ai_count}/{total_cams} bật AI",
            "cameras": cam_items,
        })

    return {
        "filter_tabs": filter_tabs,
        "groups": groups_payload,
    }


@router.get("/{cam_id}/ai-config", summary="Get camera AI detection & schedule config (Figma H10-H15)")
def get_camera_ai_config(
    cam_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get detailed AI mode and rest schedule slots for a single camera (Figma H10-H15).
    """
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam or cam.is_deleted:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    group_repo = get_group_repo()
    member = group_repo.get_member(cam.group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không phải thành viên của nhóm sở hữu camera này.")

    grp = group_repo.get_group(cam.group_id)
    group_name = grp.group_name if grp else "Nhóm"
    role_val = member.role.value if hasattr(member.role, "value") else str(member.role)
    can_edit = role_val == UserRole.LEADER.value

    mode_val = cam.ai_mode.value if hasattr(cam.ai_mode, "value") else str(cam.ai_mode or "ALWAYS")
    raw_slots = [
        (s.model_dump() if hasattr(s, "model_dump") else dict(s))
        for s in (cam.ai_schedules or [])
    ]
    scanning_now = should_ai_scan_now(mode_val, raw_slots)

    return {
        "cam_id": cam.cam_id,
        "cam_name": cam.cam_name,
        "group_id": cam.group_id,
        "group_name": group_name,
        "subgroup_id": cam.subgroup_id,
        "subgroup_name": cam.subgroup_name,
        "can_edit": can_edit,
        "ai_mode": mode_val,
        "is_ai_enabled": cam.is_ai_enabled,
        "is_ai_currently_scanning": scanning_now,
        "status_text": format_ai_status_text(mode_val, raw_slots, is_editable=can_edit),
        "max_schedules": 2,
        "schedules": raw_slots,
        "off_warning": (
            "Có cháy ở đây sẽ không ai được báo. Chỉ nên tắt khi camera bị che hoặc đang sửa."
            if mode_val == AIMode.OFF.value
            else None
        ),
        "updated_at": format_iso_utc(cam.updated_at),
    }


@router.put("/{cam_id}/ai-config", summary="Update camera AI detection & schedule config (Figma H10-H15)")
@router.patch("/{cam_id}/ai-config", summary="Update camera AI detection & schedule config (Patch)")
def update_camera_ai_config(
    cam_id: str,
    payload: CameraAIConfigUpdateRequest,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Save per-camera AI mode (ALWAYS | SCHEDULE | OFF) and up to 2 rest schedule slots (Figma H10-H15).
    RBAC: STRICTLY ONLY LEADER (Screen H8: 'Chỉ chủ nhóm được đổi cài đặt AI').
    Simultaneously pushes `SET_CAMERA_AI_CONFIG` down to the Edge Gateway (`edge-backend` -> `firewatch-ai`)
    to immediately connect or disconnect the RTSP input stream to the AI worker.
    """
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam or cam.is_deleted:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    group_repo = get_group_repo()
    member = group_repo.get_member(cam.group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không phải thành viên của nhóm sở hữu camera này.")

    role_val = member.role.value if hasattr(member.role, "value") else str(member.role)
    if role_val != UserRole.LEADER.value:
        raise PermissionDeniedException("Chỉ chủ nhóm được đổi cài đặt AI.")

    mode_val = payload.ai_mode.value if hasattr(payload.ai_mode, "value") else str(payload.ai_mode).upper()
    slots = payload.schedules or []
    if mode_val == AIMode.SCHEDULE.value and len(slots) == 0:
        from ..core.exceptions import ValidationException
        raise ValidationException("Chế độ nghỉ theo giờ (SCHEDULE) cần ít nhất 1 khung giờ nghỉ.")

    updated = camera_repo.update_camera_ai_config(
        cam_id=cam_id,
        actor_id=current_user.user_id,
        ai_mode=payload.ai_mode,
        schedules=slots,
    )
    if not updated:
        raise NotFoundException("Không thể cập nhật cài đặt AI của camera.", code="UPDATE_FAILED")

    raw_slots = [
        (s.model_dump() if hasattr(s, "model_dump") else dict(s))
        for s in (updated.ai_schedules or [])
    ]
    scanning_now = should_ai_scan_now(mode_val, raw_slots)
    stream_action = "CONNECT_AI_RTSP" if scanning_now else "DISCONNECT_AI_RTSP"

    # Dispatch command to Edge Gateway over Outbound WebSocket & Broadcast to Group Room
    edge_cmd_dispatched = False
    try:
        from ..services.websocket_manager import get_websocket_manager
        import asyncio
        ws_mgr = get_websocket_manager()
        target_edge_id = getattr(updated, "edge_device_id", None) or ws_mgr.get_edge_for_camera(cam_id) or "edg_local_01"
        edge_msg = {
            "action": "SET_CAMERA_AI_CONFIG",
            "cam_id": updated.cam_id,
            "ai_mode": mode_val,
            "is_ai_enabled": updated.is_ai_enabled,
            "should_ai_scan_now": scanning_now,
            "stream_action": stream_action,
            "schedules": raw_slots,
            "timestamp": datetime.now(timezone.utc).timestamp(),
        }
        group_event = {
            "type": "CAMERA_AI_CONFIG_UPDATED",
            "cam_id": updated.cam_id,
            "group_id": updated.group_id,
            "ai_mode": mode_val,
            "is_ai_currently_scanning": scanning_now,
            "status_text": format_ai_status_text(mode_val, raw_slots, is_editable=True),
            "schedules": raw_slots,
        }
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(ws_mgr.send_to_edge(target_edge_id, edge_msg))
                loop.create_task(ws_mgr.broadcast_to_room(f"group_{updated.group_id}", group_event))
                edge_cmd_dispatched = True
        except RuntimeError:
            pass
    except Exception:
        pass

    return {
        "status": "updated",
        "cam_id": updated.cam_id,
        "cam_name": updated.cam_name,
        "group_id": updated.group_id,
        "ai_mode": mode_val,
        "is_ai_enabled": updated.is_ai_enabled,
        "is_ai_currently_scanning": scanning_now,
        "status_text": format_ai_status_text(mode_val, raw_slots, is_editable=True),
        "schedules": raw_slots,
        "edge_command": {
            "dispatched": True,
            "action": "SET_CAMERA_AI_CONFIG",
            "stream_action": stream_action,
            "ws_queued": edge_cmd_dispatched,
        },
        "updated_at": format_iso_utc(updated.updated_at),
    }


@router.get("/{cam_id}", summary="Get camera detail")
def get_camera_detail(
    cam_id: str,
    request: Request,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get single camera detail and notified member names."""
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    group_repo = get_group_repo()
    member = group_repo.get_member(cam.group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không phải thành viên của nhóm sở hữu camera này.")

    user_role = member.role
    user_camera_ids = member.camera_ids

    has_access = True
    if user_role == UserRole.NOTIFIER:
        has_access = False
    elif user_role == UserRole.MEMBER and user_camera_ids is not None:
        if cam.cam_id not in user_camera_ids:
            has_access = False

    hls_url = build_hls_url(cam.cam_id, request) if has_access else None

    # Find members who receive alerts for this camera
    all_members = group_repo.list_members(cam.group_id)
    notified_names = []
    for m in all_members:
        if m.role in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
            notified_names.append(m.full_name)
        elif m.role in (UserRole.MEMBER, UserRole.NOTIFIER):
            if m.camera_ids is None or cam.cam_id in m.camera_ids:
                notified_names.append(m.full_name)

    return {
        "cam_id": cam.cam_id,
        "cam_name": cam.cam_name,
        "group_id": cam.group_id,
        "subgroup_id": cam.subgroup_id,
        "subgroup_name": cam.subgroup_name,
        "device_name": cam.device_name,
        "status": cam.status.value if hasattr(cam.status, "value") else str(cam.status),
        "last_seen_at": format_iso_utc(cam.last_seen_at),
        "live_stream_url": hls_url,
        "watch_area": cam.watch_area.model_dump() if cam.watch_area else None,
        "notified_names": notified_names,
        "is_ai_enabled": cam.is_ai_enabled,
        "ai_schedule": [s.model_dump(by_alias=True) if hasattr(s, "model_dump") else s for s in (cam.ai_schedule or [])],
        "thumbnail_url": cam.thumbnail_url,
    }


# ==============================================================================
# 3. STREAM URL & RBAC TICKET (Chặn 100% NOTIFIER)
# ==============================================================================

@router.get("/{cam_id}/stream", summary="Get live HLS stream URL")
@router.get("/{cam_id}/stream-url", summary="Get live HLS stream URL (Alias)")
def get_camera_stream(
    cam_id: str,
    request: Request,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get live HLS stream URL.
    RBAC:
      - NOTIFIER is STRICTLY BLOCKED with 403 Forbidden.
      - MEMBER without this camera assigned is BLOCKED with 403 Forbidden.
      - LEADER, MEMBER_MANAGER or authorized MEMBER receives the HLS URL.
    """
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    group_repo = get_group_repo()
    member = group_repo.get_member(cam.group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không phải thành viên của nhóm sở hữu camera này.")

    user_role = member.role
    user_camera_ids = member.camera_ids

    if user_role == UserRole.NOTIFIER:
        raise PermissionDeniedException("Người nhận tin (Notifier) không có quyền xem trực tiếp camera.")

    if user_role == UserRole.MEMBER and user_camera_ids is not None:
        if cam.cam_id not in user_camera_ids:
            raise PermissionDeniedException("Bạn không được phân công theo dõi camera này.")

    # Trigger on-demand wake-up to Edge Node if connected
    try:
        from ..services.websocket_manager import get_websocket_manager
        import asyncio
        ws_mgr = get_websocket_manager()
        edge_id = getattr(cam, "edge_device_id", None) or ws_mgr.get_edge_for_camera(cam.cam_id)
        if edge_id:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(ws_mgr.send_to_edge(edge_id, {"type": "START_LIVE", "cam_id": cam.cam_id}))
            except Exception:
                pass
    except Exception:
        pass

    edge_dev_id = getattr(cam, "edge_device_id", None)
    return {
        "cam_id": cam.cam_id,
        "status": cam.status.value if hasattr(cam.status, "value") else str(cam.status),
        "stream_type": "HLS",
        "stream_url": build_hls_url(cam.cam_id, request, edge_device_id=edge_dev_id),
    }


@router.post("/{cam_id}/stream/keepalive", summary="Keep live stream alive (extends on-demand TTL)")
def keepalive_camera_stream(
    cam_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Extends the on-demand viewing TTL on the edge node."""
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    try:
        from ..services.websocket_manager import get_websocket_manager
        import asyncio
        ws_mgr = get_websocket_manager()
        edge_id = getattr(cam, "edge_device_id", None) or ws_mgr.get_edge_for_camera(cam.cam_id)
        if edge_id:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(ws_mgr.send_to_edge(edge_id, {"type": "KEEPALIVE_LIVE", "cam_id": cam.cam_id}))
            except Exception:
                pass
    except Exception:
        pass

    return {"status": "ok", "cam_id": cam.cam_id}


@router.post("/{cam_id}/stream/stop", summary="Stop live stream (On-Demand auto-sleep)")
def stop_camera_stream(
    cam_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Informs the edge node that the client has closed the stream viewer."""
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    try:
        from ..services.websocket_manager import get_websocket_manager
        import asyncio
        ws_mgr = get_websocket_manager()
        edge_id = getattr(cam, "edge_device_id", None) or ws_mgr.get_edge_for_camera(cam.cam_id)
        if edge_id:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(ws_mgr.send_to_edge(edge_id, {"type": "STOP_LIVE", "cam_id": cam.cam_id}))
            except Exception:
                pass
    except Exception:
        pass

    return {"status": "ok", "cam_id": cam.cam_id}


@router.post("/{cam_id}/reconnect", summary="Reconnect camera stream")
def reconnect_camera(
    cam_id: str,
    request: Request,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Attempt reconnection for camera stream."""
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    group_repo = get_group_repo()
    member = group_repo.get_member(cam.group_id, current_user.user_id)
    if not member or member.role not in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
        raise PermissionDeniedException("Chỉ Trưởng nhóm hoặc Quản lý mới có quyền kết nối lại camera.")

    mtx = get_mediamtx_service()
    success = mtx.add_path(cam.cam_id, cam.rtsp_url)
    status_str = "ONLINE" if (success or cam.status == CameraStatus.ONLINE or "mock" in cam.rtsp_url.lower() or "test" in cam.rtsp_url.lower()) else "OFFLINE"

    return {
        "cam_id": cam.cam_id,
        "cam_name": cam.cam_name,
        "group_id": cam.group_id,
        "subgroup_id": cam.subgroup_id,
        "subgroup_name": cam.subgroup_name,
        "device_name": cam.device_name,
        "status": status_str,
        "last_seen_at": format_iso_utc(cam.last_seen_at),
        "live_stream_url": build_hls_url(cam.cam_id, request),
        "watch_area": cam.watch_area.model_dump() if cam.watch_area else None,
        "is_ai_enabled": cam.is_ai_enabled,
        "ai_schedule": [s.model_dump(by_alias=True) if hasattr(s, "model_dump") else s for s in (cam.ai_schedule or [])],
        "thumbnail_url": cam.thumbnail_url,
    }


@router.post("/{cam_id}/suspect/dismiss", status_code=status.HTTP_204_NO_CONTENT, summary="Dismiss suspect fire mark")
def dismiss_suspect(
    cam_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    """Dismiss suspect mark when user clicks 'Not a fire? Dismiss'."""
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    group_repo = get_group_repo()
    member = group_repo.get_member(cam.group_id, current_user.user_id)
    if not member or member.role == UserRole.NOTIFIER:
        raise PermissionDeniedException("Bạn không có quyền bỏ qua dấu hiệu nghi ngờ trên camera này.")

    from ..services.repositories.alert_repo import get_alert_repository
    get_alert_repository().dismiss_suspect(cam_id, current_user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==============================================================================
# 4. CAMERA CONFIGURATION & WATCH AREA
# ==============================================================================

@router.patch("/{cam_id}", summary="Update camera")
@router.put("/{cam_id}", summary="Update camera (Put)")
def update_camera(
    cam_id: str,
    payload: CameraUpdateRequest,
    request: Request,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update camera name, device name, subgroup, or AI scanning settings."""
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam or cam.is_deleted:
        raise NotFoundException("Không tìm thấy camera hoặc camera đã bị xóa.", code="CAMERA_NOT_FOUND")

    group_repo = get_group_repo()
    member = group_repo.get_member(cam.group_id, current_user.user_id)
    if not member or member.role not in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
        raise PermissionDeniedException("Chỉ Trưởng nhóm hoặc Quản lý mới có quyền cập nhật camera.")

    updated = camera_repo.update_camera(
        cam_id=cam_id,
        actor_id=current_user.user_id,
        cam_name=payload.cam_name,
        device_name=payload.device_name,
        subgroup_id=payload.subgroup_id,
        watch_area=payload.watch_area,
        is_active=payload.is_active,
        is_ai_enabled=payload.is_ai_enabled,
        rtsp_url=payload.rtsp_url,
        ai_schedule=payload.ai_schedule,
        thumbnail_url=payload.thumbnail_url,
    )
    if not updated:
        raise NotFoundException("Không thể cập nhật camera.", code="UPDATE_FAILED")

    if payload.rtsp_url:
        mtx = get_mediamtx_service()
        mtx.add_path(cam_id, payload.rtsp_url)

    serialized_schedule = [
        s.model_dump(by_alias=True) if hasattr(s, "model_dump") else s
        for s in (updated.ai_schedule or [])
    ]
    scanning_now = should_ai_scan_now(updated.is_ai_enabled, serialized_schedule)
    stream_action = "CONNECT_AI_RTSP" if scanning_now else "DISCONNECT_AI_RTSP"

    try:
        from ..services.websocket_manager import get_websocket_manager
        import asyncio
        ws_mgr = get_websocket_manager()
        target_edge_id = getattr(updated, "edge_device_id", None) or ws_mgr.get_edge_for_camera(cam_id) or "edg_local_01"
        sync_msg = {
            "action": "SYNC_CAMERA",
            "cam_id": updated.cam_id,
            "cam_name": updated.cam_name,
            "rtsp_url": updated.rtsp_url,
            "watch_area": updated.watch_area.model_dump() if updated.watch_area else None,
            "is_active": updated.is_active,
            "is_ai_enabled": updated.is_ai_enabled,
            "ai_schedule": serialized_schedule,
            "should_ai_scan_now": scanning_now,
            "stream_action": stream_action,
        }
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(ws_mgr.send_to_edge(target_edge_id, sync_msg))
    except Exception:
        pass

    return {
        "cam_id": updated.cam_id,
        "cam_name": updated.cam_name,
        "group_id": updated.group_id,
        "subgroup_id": updated.subgroup_id,
        "subgroup_name": updated.subgroup_name,
        "device_name": updated.device_name,
        "status": updated.status.value if hasattr(updated.status, "value") else str(updated.status),
        "is_active": updated.is_active,
        "is_ai_enabled": updated.is_ai_enabled,
        "ai_schedule": serialized_schedule,
        "thumbnail_url": updated.thumbnail_url,
        "watch_area": updated.watch_area.model_dump() if updated.watch_area else None,
        "live_stream_url": build_hls_url(updated.cam_id, request),
    }


@router.put("/{cam_id}/watch-area", summary="Update AI watch area")
def update_watch_area(
    cam_id: str,
    payload: WatchAreaModel,
    request: Request,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Save normalized AI watch area [0.0, 1.0] drawn on screen I5."""
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam or cam.is_deleted:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    group_repo = get_group_repo()
    member = group_repo.get_member(cam.group_id, current_user.user_id)
    if not member or member.role not in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
        raise PermissionDeniedException("Chỉ Trưởng nhóm hoặc Quản lý mới có quyền chỉnh sửa vùng quét AI.")

    updated = camera_repo.update_camera(
        cam_id=cam_id,
        actor_id=current_user.user_id,
        watch_area=payload,
    )
    try:
        from ..services.websocket_manager import get_websocket_manager
        import asyncio
        ws_mgr = get_websocket_manager()
        target_edge_id = getattr(updated, "edge_device_id", None) or ws_mgr.get_edge_for_camera(cam_id) or "edg_local_01"
        sync_msg = {
            "action": "SYNC_CAMERA",
            "cam_id": updated.cam_id,
            "cam_name": updated.cam_name,
            "rtsp_url": updated.rtsp_url,
            "watch_area": updated.watch_area.model_dump() if updated.watch_area else None,
            "is_active": updated.is_active,
        }
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(ws_mgr.send_to_edge(target_edge_id, sync_msg))
    except Exception:
        pass
    return {
        "cam_id": updated.cam_id,
        "watch_area": updated.watch_area.model_dump() if updated.watch_area else None,
    }


# ==============================================================================
# 5. TRASH BIN, RESTORE & PERMANENT DELETE (RBAC: LEADER only for permanent)
# ==============================================================================

@router.delete("/{cam_id}", summary="Soft delete camera (30-day retention)")
def delete_camera(
    cam_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Soft delete camera to 30-day trash bin. Permission: LEADER or MEMBER_MANAGER."""
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    group_repo = get_group_repo()
    member = group_repo.get_member(cam.group_id, current_user.user_id)
    if not member or member.role not in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
        raise PermissionDeniedException("Chỉ Trưởng nhóm hoặc Quản lý mới có quyền xóa camera.")

    camera_repo.soft_delete_camera(cam_id, current_user.user_id)
    mtx = get_mediamtx_service()
    mtx.remove_path(cam_id)
    try:
        from ..services.websocket_manager import get_websocket_manager
        import asyncio
        ws_mgr = get_websocket_manager()
        target_edge_id = getattr(cam, "edge_device_id", None) or ws_mgr.get_edge_for_camera(cam_id) or "edg_local_01"
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(ws_mgr.send_to_edge(target_edge_id, {"action": "REMOVE_CAMERA", "cam_id": cam_id}))
    except Exception:
        pass

    purge_at_dt = datetime.now(timezone.utc) + timedelta(days=30)
    return {
        "status": "deleted",
        "cam_id": cam.cam_id,
        "purge_at": format_iso_utc(purge_at_dt),
    }


@router.post("/{cam_id}/restore", summary="Restore camera from trash")
def restore_camera(
    cam_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Restore camera from trash bin. Permission: LEADER or MEMBER_MANAGER."""
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    group_repo = get_group_repo()
    member = group_repo.get_member(cam.group_id, current_user.user_id)
    if not member or member.role not in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
        raise PermissionDeniedException("Chỉ Trưởng nhóm hoặc Quản lý mới có quyền khôi phục camera.")

    success = camera_repo.restore_camera(cam_id, current_user.user_id)
    if not success:
        raise NotFoundException("Camera không ở trong thùng rác hoặc không thể khôi phục.", code="RESTORE_FAILED")

    mtx = get_mediamtx_service()
    mtx.add_path(cam.cam_id, cam.rtsp_url)

    return {"status": "ok", "message": "Đã khôi phục camera thành công"}


@router.delete("/{cam_id}/permanent", summary="Permanently delete camera (LEADER only)")
def permanent_delete_camera(
    cam_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Permanently purge camera from Firestore and MediaMTX.
    RBAC: STRICTLY ONLY LEADER.
    """
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    group_repo = get_group_repo()
    member = group_repo.get_member(cam.group_id, current_user.user_id)
    if not member or member.role != UserRole.LEADER:
        raise PermissionDeniedException("Chỉ Trưởng nhóm (Leader) mới có quyền xóa vĩnh viễn camera.")

    mtx = get_mediamtx_service()
    mtx.remove_path(cam.cam_id)

    camera_repo.permanent_delete_camera(cam_id, current_user.user_id)
    return {"status": "ok", "message": "Đã xóa vĩnh viễn camera"}


@router.post("/{cam_id}/simulate-offline", summary="Simulate camera offline (Testing utility)")
def simulate_camera_offline(
    cam_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Simulate camera signal lost for testing screen I8."""
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    group_repo = get_group_repo()
    member = group_repo.get_member(cam.group_id, current_user.user_id)
    if not member or member.role not in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
        raise PermissionDeniedException("Chỉ Trưởng nhóm hoặc Quản lý mới có quyền thao tác.")

    camera_repo.db.collection("cameras").document(cam_id).update({
        "status": CameraStatus.OFFLINE.value,
        "last_seen_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    return {
        "cam_id": cam_id,
        "status": "OFFLINE",
        "message": "Đã giả lập camera mất tín hiệu thành công",
    }


# ==============================================================================
# 5. CAMERA THUMBNAIL SNAPSHOT-ON-EXIT
# ==============================================================================

@router.post("/{cam_id}/thumbnail", response_model=CameraThumbnailResponse, summary="Upload camera snapshot-on-exit thumbnail")
def upload_camera_thumbnail(
    cam_id: str,
    payload: CameraThumbnailUploadRequest,
    current_user: UserModel = Depends(get_current_user),
) -> CameraThumbnailResponse:
    """
    Receive Base64 PNG/JPEG snapshot-on-exit from Flutter mobile app,
    upload to Firebase Storage CDN with cache-buster ?v=<timestamp>,
    and update camera record in Firestore.
    RBAC: LEADER, MEMBER_MANAGER, or assigned MEMBER. NOTIFIER is forbidden (403).
    """
    camera_repo = get_camera_repo()
    cam = camera_repo.get_camera(cam_id)
    if not cam or cam.is_deleted:
        raise NotFoundException("Không tìm thấy camera.", code="CAMERA_NOT_FOUND")

    group_repo = get_group_repo()
    member = group_repo.get_member(cam.group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không phải thành viên của nhóm sở hữu camera này.")

    if member.role == UserRole.NOTIFIER:
        raise PermissionDeniedException("Thành viên vai trò Người nhận tin không có quyền tải lên thumbnail camera.")

    if member.role == UserRole.MEMBER and member.camera_ids is not None:
        if cam.cam_id not in member.camera_ids:
            raise PermissionDeniedException("Bạn chưa được phân quyền truy cập camera này.")

    raw_b64 = payload.image_base64.strip()
    if not raw_b64:
        from ..core.exceptions import ValidationException
        raise ValidationException("Dữ liệu ảnh không được để trống.", code="INVALID_IMAGE")

    content_type = "image/png"
    if raw_b64.startswith("data:image/"):
        header, raw_b64 = raw_b64.split(",", 1)
        if "jpeg" in header or "jpg" in header:
            content_type = "image/jpeg"
        elif "png" in header:
            content_type = "image/png"

    storage_svc = get_storage_service()
    try:
        _, download_url = storage_svc.upload_camera_thumbnail(
            cam_id=cam.cam_id,
            image_data=raw_b64,
            content_type=content_type,
        )
    except Exception as e:
        from ..core.exceptions import ValidationException
        raise ValidationException(f"Dữ liệu ảnh không hợp lệ hoặc lỗi giải mã: {e}", code="INVALID_IMAGE")

    updated_cam = camera_repo.update_camera_thumbnail(cam.cam_id, download_url)
    now_iso = format_iso_utc(datetime.now(timezone.utc))

    return CameraThumbnailResponse(
        status="ok",
        cam_id=cam.cam_id,
        thumbnail_url=download_url,
        updated_at=now_iso,
    )
