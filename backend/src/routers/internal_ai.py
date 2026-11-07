"""
Internal AI Webhooks Router for Edge AI & FireWatch Engine (Phase 6)
"""

import time
import asyncio
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status

from ..core.security import verify_internal_secret
from ..core.exceptions import NotFoundException
from ..core.formatters import format_iso_utc
from ..models.fire_alert import (
    AIFireEventPayload,
    AIVerifyingPayload,
    AISuppressedPayload,
)
from ..services.repositories.alert_repo import get_alert_repository
from ..services.repositories.camera_repo import get_camera_repository
from ..services.repositories.group_repo import get_group_repository
from ..services.repositories.user_repo import get_user_repository
from ..services.websocket_manager import get_websocket_manager
from ..services.fcm_service import get_fcm_service
from ..services.escalation_service import get_escalation_service

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
    Webhook endpoint for Edge AI Service to push fire detection results.
    1. Saves event into Cloud Firestore (debounced 90s) & uploads snapshot to Storage.
    2. Starts Redis Two-Tier Escalation Timer (ADR 0011).
    3. Broadcasts Level 0 WebSocket alert to Leaders & Managers.
    4. Dispatches Level 0 FCM Data Message simultaneously.
    """
    alert_repo = get_alert_repository()
    group_repo = get_group_repository()
    user_repo = get_user_repository()

    if not payload.cam_id or str(payload.cam_id).strip().lower() in ("null", "none", ""):
        raise NotFoundException("Mã camera (cam_id) không hợp lệ hoặc không tồn tại.", code="CAMERA_NOT_FOUND")

    alert_record = alert_repo.save_fire_incident(
        cam_id=payload.cam_id,
        class_name=payload.class_name,
        confidence=payload.confidence,
        bbox=payload.bbox,
        image_data=payload.image_base64,
    )
    group_id = alert_record.group_id
    cam_name = alert_record.cam_name
    location_name = alert_record.location_name or alert_record.subgroup_name
    still_url = alert_record.still_url or alert_record.fire_image_url

    # 2. Start Redis Two-Tier Escalation Timer (ADR 0011) ONLY if newly opened alert
    status_str = alert_record.status.value if hasattr(alert_record.status, "value") else str(alert_record.status)
    esc_svc = get_escalation_service()
    is_new_timer = False
    if status_str == "NEW":
        if not esc_svc.is_timer_active(alert_record.alert_id):
            esc_svc.start_timer(
                alert_id=alert_record.alert_id,
                group_id=group_id,
                alert_data=alert_record.model_dump() if hasattr(alert_record, "model_dump") else {},
                ttl_seconds=60,
            )
            is_new_timer = True

    # 3 & 4. Concurrent Broadcast: WebSocket Level 0 & FCM Push (Escalation Level 0: Leaders & Managers)
    ws = get_websocket_manager()
    fcm = get_fcm_service()

    ws_broadcast_coro = ws.broadcast_fire_alert(
        group_id=group_id,
        alert_payload={
            "alert_id": alert_record.alert_id,
            "cam_id": payload.cam_id,
            "cam_name": cam_name,
            "location_name": location_name,
            "sign": alert_record.sign.value if hasattr(alert_record.sign, "value") else str(alert_record.sign),
            "confidence": payload.confidence,
            "still_url": still_url,
            "bbox": payload.bbox,
            "summary": alert_record.summary,
            "detail": alert_record.detail,
            "verification": alert_record.verification.value if hasattr(alert_record.verification, "value") else str(alert_record.verification),
            "detected_at": format_iso_utc(alert_record.detected_at) or (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"),
        },
        escalation_level=0,
    )

    async def dispatch_fcm_async():
        # Only dispatch FCM push for new incident creation to avoid alert fatigue
        if not is_new_timer:
            return
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

    # Dispatch both simultaneously for <500ms latency
    await asyncio.gather(ws_broadcast_coro, dispatch_fcm_async(), return_exceptions=True)

    return {
        "status": "accepted",
        "alert_id": alert_record.alert_id,
        "escalation_level": 0,
    }
