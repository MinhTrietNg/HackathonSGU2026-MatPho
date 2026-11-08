"""
Internal AI Webhooks Router for Edge AI & FireWatch Engine (Phase 6)
"""

import time
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, status

from ..core.security import verify_internal_secret
from ..core.exceptions import NotFoundException
from ..core.formatters import format_iso_utc
from ..core.ai_schedule import should_ai_scan_now
from ..models.fire_alert import (
    AIFireEventPayload,
    AISnapshotUploadPayload,
    AIVerifyingPayload,
    AISuppressedPayload,
    AlertStatus,
    AlertVerification,
)
from ..services.repositories.alert_repo import get_alert_repository
from ..services.repositories.camera_repo import get_camera_repository
from ..services.repositories.group_repo import get_group_repository
from ..services.repositories.user_repo import get_user_repository
from ..services.websocket_manager import get_websocket_manager
from ..services.fcm_service import get_fcm_service
from ..services.escalation_service import get_escalation_service

logger = logging.getLogger("backend.routers.internal_ai")

router = APIRouter(tags=["Internal AI"])


@router.post("/api/v1/internal/ai/verifying", status_code=status.HTTP_202_ACCEPTED)
@router.post("/internal/ai/verifying", status_code=status.HTTP_202_ACCEPTED)
async def receive_ai_verifying(
    payload: AIVerifyingPayload,
    authorized: bool = Depends(verify_internal_secret),
):
    """Webhook phát tín hiệu AI đang thẩm định sự cố (Màn hình E2a–E2c viền vàng)."""
    camera_repo = get_camera_repository()
    cam = camera_repo.get_camera(payload.cam_id)
    group_id = cam.group_id if cam else None
    ws = get_websocket_manager()
    await ws.broadcast_ai_verifying(
        cam_id=payload.cam_id,
        sign=payload.sign,
        confidence=payload.confidence,
        message=payload.message,
        steps=payload.steps,
        group_id=group_id,
    )
    return {"status": "accepted", "cam_id": payload.cam_id}


@router.post("/api/v1/internal/ai/suppressed", status_code=status.HTTP_202_ACCEPTED)
@router.post("/internal/ai/suppressed", status_code=status.HTTP_202_ACCEPTED)
async def receive_ai_suppressed(
    payload: AISuppressedPayload,
    authorized: bool = Depends(verify_internal_secret),
):
    """Webhook phát tín hiệu AI kết luận không phải cháy (Toast E4 xám không còi hú)."""
    camera_repo = get_camera_repository()
    cam = camera_repo.get_camera(payload.cam_id)
    group_id = cam.group_id if cam else None
    ws = get_websocket_manager()
    await ws.broadcast_fire_alert_suppressed(
        cam_id=payload.cam_id,
        alert_id=payload.alert_id or f"alt_supp_{int(time.time())}",
        summary=payload.summary,
        detail=payload.detail,
        group_id=group_id,
    )
    return {"status": "accepted", "cam_id": payload.cam_id}


@router.post("/internal/ai/fire-events", status_code=status.HTTP_202_ACCEPTED)
@router.post("/api/v1/internal/ai/fire-events", status_code=status.HTTP_202_ACCEPTED)
@router.post("/api/v1/alerts/events", status_code=status.HTTP_202_ACCEPTED)
async def receive_ai_fire_events(
    payload: AIFireEventPayload,
    authorized: bool = Depends(verify_internal_secret),
):
    """
    Phase 1 Fast Signal Webhook (<30ms):
    Receives lightweight fire signal JSON (~0.6KB) from Edge AI / EAG.
    1. Upserts event into Cloud Firestore (indexed by event_id or debounced 90s).
    2. If SUPPRESSED or REJECTED: cancels Redis escalation timer and notifies Frontend.
    3. If active fire: starts Redis Two-Tier Escalation Timer (ADR 0011) and broadcasts Level 0 alert.
    4. If snapshot_base64 is present, queues Phase 2 background storage upload.
    """
    alert_repo = get_alert_repository()
    group_repo = get_group_repository()
    user_repo = get_user_repository()
    camera_repo = get_camera_repository()
    esc_svc = get_escalation_service()
    ws = get_websocket_manager()
    fcm = get_fcm_service()

    target_cam_id = payload.cam_id or payload.camera_id
    if not target_cam_id or str(target_cam_id).strip().lower() in ("null", "none", ""):
        raise NotFoundException("Mã camera (cam_id / camera_id) không hợp lệ hoặc bị thiếu.", code="CAMERA_NOT_FOUND")

    cam_obj = camera_repo.get_camera(target_cam_id)
    if cam_obj:
        mode_val = cam_obj.ai_mode.value if hasattr(cam_obj.ai_mode, "value") else str(cam_obj.ai_mode or "ALWAYS")
        if not cam_obj.is_ai_enabled or not should_ai_scan_now(mode_val, cam_obj.ai_schedules):
            return {
                "status": "ignored_by_ai_schedule",
                "cam_id": target_cam_id,
                "ai_mode": mode_val,
                "reason": "Camera AI đang tắt hoặc đang trong khung giờ nghỉ theo lịch (H7-H15).",
            }

    # Ingest signal into Firestore (fast upsert)
    if not cam_obj:
        # Camera chưa đăng ký: FireWatch/edge đang quét một cam_id backend không biết
        # (cam_01 mặc định, camera chỉ khai ở edge). Ghi rõ để không phải đoán từ "404".
        logger.warning(
            "Fire event %s rejected: camera %r is not registered (edge cam ids must match "
            "backend cam ids; check edge CLOUD_BACKEND_WS_URL sync)",
            payload.event_id, target_cam_id,
        )
        raise NotFoundException(
            f"Không tìm thấy camera tương ứng ({target_cam_id}). Camera phải được tạo trong "
            "app để backend đồng bộ xuống edge.",
            code="CAMERA_NOT_FOUND",
        )

    alert_record, is_new, ghep = alert_repo.upsert_fire_incident_signal(payload)
    tai_bung = bool(ghep.get("tai_bung"))
    group_id = alert_record.group_id
    cam_name = alert_record.cam_name
    location_name = alert_record.location_name or alert_record.subgroup_name
    status_str = alert_record.status.value if hasattr(alert_record.status, "value") else str(alert_record.status)
    verification_str = alert_record.verification.value if hasattr(alert_record.verification, "value") else str(alert_record.verification)

    # Check if this event was suppressed or rejected
    is_suppressed = (
        status_str == AlertStatus.SUPPRESSED.value
        or verification_str == AlertVerification.SUPPRESSED.value
        or (payload.verifier and payload.verifier.status == "REJECTED")
    )

    if is_suppressed:
        esc_svc.cancel_timer(alert_record.alert_id)
        await ws.broadcast_fire_alert_suppressed(
            cam_id=target_cam_id,
            alert_id=alert_record.alert_id,
            summary=alert_record.summary,
            detail=alert_record.detail,
            group_id=group_id,
        )
        return {
            "status": "accepted",
            "alert_id": alert_record.alert_id,
            "event_id": payload.event_id or alert_record.event_id,
            "verification": "SUPPRESSED",
            "type": payload.type,
        }

    is_new_timer = False
    if is_new or tai_bung:
        # tai_bung: FireWatch opened a new event_id on a camera whose alert is still open
        # (restart, fire flared up again): same alert_id, re-alert the app; FCM stays
        # deduplicated per alert by the Redis keys below.
        if tai_bung:
            logger.info("Fire event %s merged into open alert %s (re-alert)", payload.event_id, alert_record.alert_id)
        if not esc_svc.is_timer_active(alert_record.alert_id):
            esc_svc.start_timer(
                alert_id=alert_record.alert_id,
                group_id=group_id,
                alert_data=alert_record.model_dump() if hasattr(alert_record, "model_dump") else {},
                ttl_seconds=60,
            )
            is_new_timer = True

        ws_broadcast_coro = ws.broadcast_fire_alert(
            group_id=group_id,
            alert_payload={
                "alert_id": alert_record.alert_id,
                "event_id": payload.event_id or alert_record.event_id,
                "cam_id": target_cam_id,
                "cam_name": cam_name,
                "location_name": location_name,
                "sign": alert_record.sign.value if hasattr(alert_record.sign, "value") else str(alert_record.sign),
                "confidence": payload.confidence,
                "still_url": alert_record.still_url or alert_record.fire_image_url,
                "bbox": payload.bbox,
                "boxes": [b.model_dump() for b in payload.boxes] if payload.boxes else [],
                "frame_w": payload.frame_w,
                "frame_h": payload.frame_h,
                "summary": alert_record.summary,
                "detail": alert_record.detail,
                "verification": verification_str,
                "detected_at": format_iso_utc(alert_record.detected_at) or (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"),
            },
            escalation_level=0,
        )

        async def dispatch_fcm_async():
            if not is_new_timer:
                return
            # Anti-spam: Strict FCM Level 0 deduplication per incident and camera cooldown (90s)
            r = getattr(esc_svc, "_redis", None)
            fcm_incident_key = f"fcm:sent:{alert_record.alert_id}:level_0"
            fcm_camera_cooldown_key = f"fcm:cooldown:camera:{target_cam_id}"

            if r:
                try:
                    if r.exists(fcm_incident_key) or r.exists(fcm_camera_cooldown_key):
                        return
                    r.set(fcm_incident_key, "1", ex=3600)
                    r.set(fcm_camera_cooldown_key, "1", ex=90)
                except Exception:
                    pass

            members = group_repo.list_members(group_id)
            leader_tokens = []
            for m in members:
                if m.role in ("LEADER", "MEMBER_MANAGER"):
                    u = user_repo.get_user_by_id(m.user_id)
                    if u and u.fcm_tokens:
                        leader_tokens.extend(u.fcm_tokens)

            if leader_tokens:
                await asyncio.to_thread(
                    fcm.send_fire_alert_push,
                    fcm_tokens=leader_tokens,
                    alert_id=alert_record.alert_id,
                    escalation_level=0,
                )

        await asyncio.gather(ws_broadcast_coro, dispatch_fcm_async(), return_exceptions=True)
    else:
        # Incident updated: notify subscribers via WebSocket
        await ws.broadcast_fire_alert_updated(
            group_id=group_id,
            alert_id=alert_record.alert_id,
            status=status_str,
            escalation_level=0,
            alert_payload={
                "event_id": payload.event_id or alert_record.event_id,
                "cam_id": target_cam_id,
                "verification": verification_str,
                "vlm": payload.vlm.model_dump() if payload.vlm else None,
                "verifier": payload.verifier.model_dump() if payload.verifier else None,
                "boxes": [b.model_dump() for b in payload.boxes] if payload.boxes else [],
                "last_seen_ts": payload.last_seen_ts,
                "summary": alert_record.summary,
                "detail": alert_record.detail,
            },
        )

    # If snapshot_base64 is present directly in signal payload, upload in background thread
    raw_b64 = payload.snapshot_base64 or payload.image_base64
    if raw_b64 and not is_suppressed:
        box_dicts = [b.model_dump() for b in payload.boxes] if payload.boxes else []
        asyncio.create_task(
            asyncio.to_thread(
                alert_repo.attach_incident_snapshot,
                event_id=payload.event_id or alert_record.alert_id,
                cam_id=target_cam_id,
                snapshot_base64=raw_b64,
                frame_ts=payload.frame_ts or payload.last_seen_ts,
                boxes=box_dicts,
                frame_w=payload.frame_w or 1920,
                frame_h=payload.frame_h or 1080,
            )
        )

    return {
        "status": "accepted",
        "alert_id": alert_record.alert_id,
        "event_id": payload.event_id or alert_record.event_id,
        "escalation_level": 0,
        "type": payload.type,
        "verification": verification_str,
    }


@router.post("/internal/ai/fire-events/{event_id}/snapshot", status_code=status.HTTP_202_ACCEPTED)
@router.post("/api/v1/internal/ai/fire-events/{event_id}/snapshot", status_code=status.HTTP_202_ACCEPTED)
async def upload_ai_snapshot(
    event_id: str,
    payload: AISnapshotUploadPayload,
    authorized: bool = Depends(verify_internal_secret),
):
    """
    Phase 2 Background Upload Endpoint:
    EAG forwards the single clean JPEG snapshot (snapshot_base64 <= 200KB) to Cloud Backend.
    Backend stores it in Firebase Storage, marks snapshot_status="READY", and notifies Frontend via WS.
    """
    alert_repo = get_alert_repository()
    box_dicts = [b.model_dump() for b in payload.boxes] if payload.boxes else []

    updated_alert = alert_repo.attach_incident_snapshot(
        event_id=event_id,
        cam_id=payload.cam_id or payload.camera_id,
        snapshot_base64=payload.snapshot_base64,
        frame_ts=payload.frame_ts,
        boxes=box_dicts,
        frame_w=payload.frame_w or 1920,
        frame_h=payload.frame_h or 1080,
    )

    if not updated_alert:
        return {
            "status": "alert_not_found_or_ignored",
            "event_id": event_id,
            "message": "Incident alert not found or snapshot already ready",
        }

    ws = get_websocket_manager()
    await ws.broadcast_alert_snapshot_ready(
        group_id=updated_alert.group_id,
        alert_id=updated_alert.alert_id,
        event_id=event_id,
        cam_id=payload.cam_id or payload.camera_id,
        still_url=updated_alert.still_url or updated_alert.fire_image_url,
        boxes=box_dicts,
        frame_w=payload.frame_w or 1920,
        frame_h=payload.frame_h or 1080,
    )

    return {
        "status": "snapshot_uploaded",
        "alert_id": updated_alert.alert_id,
        "event_id": event_id,
        "still_url": updated_alert.still_url or updated_alert.fire_image_url,
    }


@router.get("/api/v1/internal/edge/cameras", summary="Internal camera sync for Edge Nodes")
@router.get("/internal/edge/cameras", summary="Internal camera sync for Edge Nodes")
def get_internal_edge_cameras(
    edge_device_id: Optional[str] = Query(None),
    authorized: bool = Depends(verify_internal_secret),
) -> Dict[str, Any]:
    """
    Return all active cameras configured for an Edge Node.
    Called by Edge Backend on startup and periodic polling to ensure zero camera drift.
    """
    camera_repo = get_camera_repository()
    edge_id = edge_device_id or "edg_local_01"
    cams = camera_repo.list_cameras_for_edge_node(edge_id)
    return {
        "status": "ok",
        "edge_device_id": edge_id,
        "cameras": [
            {
                "cam_id": c.cam_id,
                "cam_name": c.cam_name,
                "rtsp_url": c.rtsp_url,
                "watch_area": c.watch_area.model_dump() if c.watch_area else None,
                "is_active": c.is_active,
                "is_ai_enabled": c.is_ai_enabled,
                "ai_mode": c.ai_mode.value if hasattr(c.ai_mode, "value") else str(c.ai_mode or "ALWAYS"),
                "ai_schedules": [s.model_dump(by_alias=True) if hasattr(s, "model_dump") else s for s in (c.ai_schedule or [])],
            }
            for c in cams
        ],
    }
