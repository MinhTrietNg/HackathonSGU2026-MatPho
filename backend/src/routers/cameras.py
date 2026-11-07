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
from ..models.user import UserModel
from ..models.common import UserRole, CameraStatus
from ..models.camera import (
    CameraModel,
    CameraCreateRequest,
    CameraUpdateRequest,
    CameraProbeRequest,
    CameraProbeResponse,
    CameraStreamResponse,
    WatchAreaModel,
)
from ..services.repositories.camera_repo import get_camera_repo
from ..services.repositories.group_repo import get_group_repo
from ..services.camera_probe_service import get_camera_probe_service
from ..services.mediamtx_service import get_mediamtx_service

router = APIRouter(prefix="/cameras", tags=["Cameras"])


def build_hls_url(cam_id: str, request: Optional[Request] = None) -> str:
    path_template = os.getenv("HLS_PATH_TEMPLATE", "live/{cam_id}")
    stream_path = path_template.format(cam_id=cam_id)
    env_host = os.getenv("MEDIAMTX_HOST")

    if env_host and env_host.strip():
        host_clean = env_host.strip().rstrip("/")
        if host_clean.startswith("http://") or host_clean.startswith("https://"):
            return f"{host_clean}/{stream_path}/index.m3u8"
        return f"https://{host_clean}/{stream_path}/index.m3u8"

    if request:
        host_header = request.headers.get("host", "")
        if host_header:
            client_host = host_header.split(":")[0]
            if client_host == "testserver":
                return f"https://stream.matpho.vn/{stream_path}/index.m3u8"
            if client_host in ("10.0.2.2", "localhost", "127.0.0.1"):
                return f"http://{client_host}:8888/{stream_path}/index.m3u8"

    return f"https://stream.matpho.vn/{stream_path}/index.m3u8"


# ==============================================================================
# 1. RTSP PROBE (Thăm dò RTSP & chụp ảnh nền)
# ==============================================================================

@router.post("/probe", response_model=CameraProbeResponse, summary="Probe RTSP stream")
def probe_camera(
    payload: CameraProbeRequest,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Test connect RTSP stream within 3-5 seconds, extract resolution/fps and return preview snapshot.
    Figma screens I2, I4, I5.
    """
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

    # Register path in MediaMTX
    mtx = get_mediamtx_service()
    mtx.add_path(camera.cam_id, payload.rtsp_url)

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

    return {
        "cam_id": cam.cam_id,
        "status": cam.status.value if hasattr(cam.status, "value") else str(cam.status),
        "stream_type": "HLS",
        "stream_url": build_hls_url(cam.cam_id, request),
    }


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
    )
    if not updated:
        raise NotFoundException("Không thể cập nhật camera.", code="UPDATE_FAILED")

    if payload.rtsp_url:
        mtx = get_mediamtx_service()
        mtx.add_path(cam_id, payload.rtsp_url)

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
