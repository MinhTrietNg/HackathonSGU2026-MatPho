"""
Fire Alerts & Emergency Incidents Router for Mắt Phố (Phase 6 - Rows F & G)
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, Query

from ..core.exceptions import (
    PermissionDeniedException,
    NotFoundException,
)
from ..core.security import get_current_user, get_optional_current_user, verify_emergency_token
from ..core.formatters import format_iso_utc, normalize_bbox
from ..services.repositories.alert_repo import get_alert_repository
from ..services.repositories.group_repo import get_group_repository
from ..services.repositories.user_repo import get_user_repository
from ..services.websocket_manager import get_websocket_manager
from ..services.fcm_service import get_fcm_service
from ..services.escalation_service import get_escalation_service
from ..models.user import UserModel
from ..models.common import UserRole, AlertStatus
from ..models.fire_alert import FireAlertModel, ResolveAlertRequest

router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts"])


def resolve_alert_detected_at(a: FireAlertModel) -> Any:
    if a.detected_at:
        return a.detected_at
    if a.steps:
        for s in a.steps:
            kind = s.get("kind") if isinstance(s, dict) else getattr(s, "kind", None)
            if kind == "DETECTED":
                return s.get("at") if isinstance(s, dict) else getattr(s, "at", None)
    if a.created_at:
        return a.created_at
    return datetime.now(timezone.utc)


def serialize_alert(a: FireAlertModel, address: str) -> dict:
    steps_map = {}
    for s in a.steps:
        kind = s.kind if hasattr(s, "kind") else s.get("kind")
        at = s.at if hasattr(s, "at") else s.get("at")
        steps_map[kind] = format_iso_utc(at)

    snapshots_dto = []
    for snap in a.timeline_snapshots:
        image_url = snap.image_url if hasattr(snap, "image_url") else snap.get("image_url")
        bbox = snap.bbox if hasattr(snap, "bbox") else snap.get("bbox", [])
        timestamp = snap.timestamp if hasattr(snap, "timestamp") else snap.get("timestamp")
        snapshots_dto.append({
            "url": image_url,
            "bbox": normalize_bbox(bbox),
            "timestamp": format_iso_utc(timestamp),
        })

    return {
        "alert_id": a.alert_id,
        "cam_id": a.cam_id,
        "cam_name": a.cam_name,
        "location_name": a.location_name or a.subgroup_name,
        "address": address,
        "status": a.status.value if hasattr(a.status, "value") else str(a.status),
        "sign": a.sign.value if hasattr(a.sign, "value") else str(a.sign),
        "confidence": round(a.confidence or 0.0, 2),
        "check_count": a.check_count,
        "verification": a.verification.value if hasattr(a.verification, "value") else str(a.verification),
        "summary": a.summary,
        "detail": a.detail,
        "call_script": a.call_script,
        "still_url": a.still_url or a.fire_image_url,
        "detected_at": format_iso_utc(resolve_alert_detected_at(a)),
        "called_114_at": format_iso_utc(a.called_114_at),
        "resolved_at": format_iso_utc(a.resolved_at),
        "resolved_by": a.resolved_by,
        "resolved_by_name": getattr(a, "resolved_by_name", None) or a.resolved_by,
        "resolution_note": a.resolution_note,
        "steps": steps_map,
        "timeline_snapshots": snapshots_dto,
    }


@router.get("")
async def list_alerts(
    group_id: Optional[str] = Query(None),
    filter: Optional[str] = Query("all", pattern="^(all|fire|dismissed|false_alarm)$"),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
):
    alert_repo = get_alert_repository()
    group_repo = get_group_repository()

    if group_id:
        member = group_repo.get_member(group_id, current_user.user_id)
        if not member:
            raise PermissionDeniedException("Bạn không thuộc nhóm này.")
        target_group_ids = [group_id]
    else:
        target_group_ids = [g.group_id for g, _, _ in group_repo.list_groups_for_user(current_user.user_id)]

    all_alerts = []
    for gid in target_group_ids:
        all_alerts.extend(alert_repo.list_alerts_by_group(gid, limit=100))

    # Apply filter
    filtered = []
    for a in all_alerts:
        status_val = a.status.value if hasattr(a.status, "value") else str(a.status)
        ver_val = a.verification.value if hasattr(a.verification, "value") else str(a.verification)
        if filter == "fire":
            if ver_val in ("SUPPRESSED", "CONFIRMED_NOT_FIRE") or status_val in ("SUPPRESSED", "DISMISSED", "FALSE_ALARM"):
                continue
            if status_val not in ("NEW", "CONFIRMED", "RESOLVED") and ver_val != "CONFIRMED_FIRE":
                continue
        elif filter == "dismissed" and status_val not in ("SUPPRESSED", "DISMISSED") and ver_val not in ("SUPPRESSED", "CONFIRMED_NOT_FIRE"):
            continue
        elif filter == "false_alarm" and status_val not in ("FALSE_ALARM", "DISMISSED") and ver_val != "CONFIRMED_NOT_FIRE":
            continue
        filtered.append(a)

    # Sort descending
    filtered.sort(
        key=lambda x: str(x.created_at) if x.created_at else "",
        reverse=True,
    )

    # Cursor pagination
    if cursor:
        filtered = [
            a for a in filtered
            if (format_iso_utc(a.created_at) or "") < cursor
        ]

    items = filtered[:limit]
    next_cursor = None
    if len(filtered) > limit:
        last = items[-1]
        next_cursor = format_iso_utc(last.created_at)

    items_dto = []
    for a in items:
        items_dto.append({
            "alert_id": a.alert_id,
            "cam_id": a.cam_id,
            "cam_name": a.cam_name,
            "location_name": a.location_name or a.subgroup_name,
            "status": a.status.value if hasattr(a.status, "value") else str(a.status),
            "sign": a.sign.value if hasattr(a.sign, "value") else str(a.sign),
            "confidence": round(a.confidence or 0.0, 2),
            "verification": a.verification.value if hasattr(a.verification, "value") else str(a.verification),
            "summary": a.summary,
            "detail": a.detail,
            "still_url": a.still_url or a.fire_image_url,
            "detected_at": format_iso_utc(resolve_alert_detected_at(a)),
            "called_114_at": format_iso_utc(a.called_114_at),
            "resolved_at": format_iso_utc(a.resolved_at),
            "resolved_by_name": getattr(a, "resolved_by_name", None) or a.resolved_by,
        })

    return {
        "items": items_dto,
        "next_cursor": next_cursor,
    }


@router.get("/{alert_id}")
async def get_alert_detail(
    alert_id: str,
    emergency_token: Optional[str] = Query(None),
    current_user: Optional[UserModel] = Depends(get_optional_current_user),
):
    alert_repo = get_alert_repository()
    group_repo = get_group_repository()

    a = alert_repo.get_alert(alert_id)
    if not a:
        raise NotFoundException("Không tìm thấy sự cố báo động.")

    # Check emergency zero-friction bypass token
    is_emergency_valid = False
    if emergency_token and verify_emergency_token(alert_id, emergency_token):
        is_emergency_valid = True

    if not is_emergency_valid:
        if not current_user:
            raise PermissionDeniedException("Cần đăng nhập hoặc cung cấp emergency_token hợp lệ để xem sự cố.")
        member = group_repo.get_member(a.group_id, current_user.user_id)
        if not member:
            raise PermissionDeniedException("Bạn không thuộc nhóm xảy ra sự cố này.")

    # Get group address
    group = group_repo.get_group(a.group_id)
    address = group.address if group else "Hiện trường sự cố"

    return serialize_alert(a, address)


@router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    payload: ResolveAlertRequest,
    current_user: UserModel = Depends(get_current_user),
):
    alert_repo = get_alert_repository()
    group_repo = get_group_repository()
    user_repo = get_user_repository()

    a = alert_repo.get_alert(alert_id)
    if not a:
        raise NotFoundException("Không tìm thấy sự cố báo động.")

    # Check permission: must be member and NOTIFIER cannot resolve
    member = group_repo.get_member(a.group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không thuộc nhóm xảy ra sự cố.")
    if member.role == UserRole.NOTIFIER:
        raise PermissionDeniedException("Người nhận tin (Notifier) không có quyền đóng sự cố.")

    alert_repo.resolve_fire_incident(
        alert_id=alert_id,
        resolved_by=current_user.user_id,
        resolution_note=payload.resolution_note,
    )

    # ADR 0011: Cancel Redis Escalation Timer
    esc_svc = get_escalation_service()
    esc_svc.cancel_timer(alert_id)

    # Broadcast WebSocket update
    now_utc_str = format_iso_utc(datetime.now(timezone.utc))
    ws = get_websocket_manager()
    await ws.broadcast_fire_alert_updated(
        group_id=a.group_id,
        alert_id=alert_id,
        status="RESOLVED",
        escalation_level=1,
        resolved_by_name=current_user.full_name,
        resolved_at=now_utc_str,
    )

    # Broadcast FCM update
    fcm = get_fcm_service()
    members = group_repo.list_members(a.group_id)
    all_tokens = []
    for m in members:
        u = user_repo.get_user_by_id(m.user_id)
        if u and u.fcm_tokens:
            all_tokens.extend(u.fcm_tokens)

    if all_tokens:
        fcm.send_fire_alert_updated_push(
            fcm_tokens=all_tokens,
            alert_id=alert_id,
            status="RESOLVED",
            resolved_by_name=current_user.full_name,
        )

    updated_alert = alert_repo.get_alert(alert_id)
    group = group_repo.get_group(a.group_id)
    address = group.address if group else "Hiện trường sự cố"
    return serialize_alert(updated_alert, address) if updated_alert else {
        "alert_id": alert_id,
        "status": "RESOLVED",
        "resolved_by": current_user.full_name,
        "resolution_note": payload.resolution_note,
    }


@router.post("/{alert_id}/mark-false-alarm")
async def mark_false_alarm(
    alert_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    alert_repo = get_alert_repository()
    group_repo = get_group_repository()
    user_repo = get_user_repository()

    a = alert_repo.get_alert(alert_id)
    if not a:
        raise NotFoundException("Không tìm thấy sự cố báo động.")

    member = group_repo.get_member(a.group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không thuộc nhóm xảy ra sự cố.")
    if member.role == UserRole.NOTIFIER:
        raise PermissionDeniedException("Người nhận tin (Notifier) không có quyền báo nhầm.")

    alert_repo.mark_false_alarm_incident(alert_id, current_user.user_id)

    # ADR 0011: Cancel Redis Escalation Timer
    esc_svc = get_escalation_service()
    esc_svc.cancel_timer(alert_id)

    # Broadcast WebSocket update
    now_utc_str = format_iso_utc(datetime.now(timezone.utc))
    ws = get_websocket_manager()
    await ws.broadcast_fire_alert_updated(
        group_id=a.group_id,
        alert_id=alert_id,
        status="FALSE_ALARM",
        escalation_level=1,
        resolved_by_name=current_user.full_name,
        resolved_at=now_utc_str,
    )

    # Broadcast FCM update
    fcm = get_fcm_service()
    members = group_repo.list_members(a.group_id)
    all_tokens = []
    for m in members:
        u = user_repo.get_user_by_id(m.user_id)
        if u and u.fcm_tokens:
            all_tokens.extend(u.fcm_tokens)

    if all_tokens:
        fcm.send_fire_alert_updated_push(
            fcm_tokens=all_tokens,
            alert_id=alert_id,
            status="FALSE_ALARM",
            resolved_by_name=current_user.full_name,
        )

    updated_alert = alert_repo.get_alert(alert_id)
    group = group_repo.get_group(a.group_id)
    address = group.address if group else "Hiện trường sự cố"
    return serialize_alert(updated_alert, address) if updated_alert else {
        "alert_id": alert_id,
        "status": "FALSE_ALARM",
        "resolved_by": current_user.full_name,
    }


@router.get("/{alert_id}/escalation-status")
async def get_alert_escalation_status(
    alert_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    alert_repo = get_alert_repository()
    a = alert_repo.get_alert(alert_id)
    if not a:
        raise NotFoundException("Không tìm thấy sự cố báo động.")

    esc_svc = get_escalation_service()
    is_active = esc_svc.is_timer_active(alert_id)
    rem_seconds = esc_svc.get_remaining_seconds(alert_id)

    return {
        "alert_id": alert_id,
        "group_id": a.group_id,
        "status": a.status.value if hasattr(a.status, "value") else str(a.status),
        "timer_active": is_active,
        "remaining_seconds": rem_seconds,
        "escalation_level": a.escalation_level,
    }


@router.post("/{alert_id}/call-114")
async def call_114(
    alert_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    alert_repo = get_alert_repository()
    group_repo = get_group_repository()
    user_repo = get_user_repository()

    a = alert_repo.get_alert(alert_id)
    if not a:
        raise NotFoundException("Không tìm thấy sự cố báo động.")

    member = group_repo.get_member(a.group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không thuộc nhóm xảy ra sự cố.")

    # ADR 0011: Cancel Redis Escalation Timer
    esc_svc = get_escalation_service()
    esc_svc.cancel_timer(alert_id)

    alert_repo.call_114_incident(alert_id, current_user.user_id)
    group = group_repo.get_group(a.group_id)
    address = group.address if group else "Hiện trường cơ sở"
    call_script = f"Báo cháy khẩn cấp tại: {address}, khu vực {a.location_name or a.subgroup_name}."

    # 1. Broadcast WebSocket Escalation Level 1 to all members
    ws = get_websocket_manager()
    ws_broadcast = ws.broadcast_fire_alert(
        group_id=a.group_id,
        alert_payload={
            "alert_id": a.alert_id,
            "cam_id": a.cam_id,
            "cam_name": a.cam_name,
            "location_name": a.location_name or a.subgroup_name,
            "sign": a.sign.value if hasattr(a.sign, "value") else str(a.sign),
            "confidence": a.confidence,
            "still_url": a.still_url or a.fire_image_url,
            "detected_at": format_iso_utc(a.detected_at),
            "verification": a.verification.value if hasattr(a.verification, "value") else str(a.verification or "VERIFIED"),
            "summary": a.summary or f"Phát hiện {a.sign.value if hasattr(a.sign, 'value') else a.sign} tại {a.cam_name}",
            "detail": a.detail or f"Khẩn cấp: Đã gọi 114 báo cháy tại {address}",
        },
        escalation_level=1,
    )

    # 2. Dispatch FCM High Priority Push to ALL members (Cấp 2 Escalation)
    fcm = get_fcm_service()
    async def dispatch_fcm():
        members = group_repo.list_members(a.group_id)
        all_tokens = []
        for m in members:
            u = user_repo.get_user_by_id(m.user_id)
            if u and u.fcm_tokens:
                all_tokens.extend(u.fcm_tokens)
        if all_tokens:
            await asyncio.to_thread(
                fcm.send_fire_alert_push,
                fcm_tokens=all_tokens,
                alert_id=alert_id,
                escalation_level=1,
            )

    await asyncio.gather(ws_broadcast, dispatch_fcm(), return_exceptions=True)

    updated_alert = alert_repo.get_alert(alert_id)
    called_at = updated_alert.called_114_at if updated_alert and updated_alert.called_114_at else datetime.now(timezone.utc)

    return {
        "alert_id": alert_id,
        "status": "CONFIRMED",
        "called_114_at": format_iso_utc(called_at),
        "address": address,
        "address_to_read": call_script,
        "call_script": call_script,
        "message": "Đã ghi nhận cuộc gọi 114 khẩn cấp và kích hoạt còi hú toàn bộ thành viên",
    }


@router.post("/{alert_id}/report-real-fire")
async def report_real_fire(
    alert_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    alert_repo = get_alert_repository()
    group_repo = get_group_repository()
    user_repo = get_user_repository()

    a = alert_repo.get_alert(alert_id)
    if not a:
        raise NotFoundException("Không tìm thấy sự cố báo động.")

    member = group_repo.get_member(a.group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không thuộc nhóm xảy ra sự cố.")

    alert_repo.report_real_fire(alert_id, current_user.user_id)
    a = alert_repo.get_alert(alert_id) or a

    # ADR 0011: Cancel Redis Escalation Timer
    esc_svc = get_escalation_service()
    esc_svc.cancel_timer(alert_id)
    group = group_repo.get_group(a.group_id)
    address = group.address if group else "Hiện trường cơ sở"

    # 1. Broadcast WebSocket siren Level 1
    ws = get_websocket_manager()
    ws_broadcast = ws.broadcast_fire_alert(
        group_id=a.group_id,
        alert_payload={
            "alert_id": a.alert_id,
            "cam_id": a.cam_id,
            "cam_name": a.cam_name,
            "location_name": a.location_name or a.subgroup_name,
            "sign": a.sign.value if hasattr(a.sign, "value") else str(a.sign),
            "confidence": a.confidence,
            "still_url": a.still_url or a.fire_image_url,
            "detected_at": format_iso_utc(a.detected_at),
            "verification": a.verification.value if hasattr(a.verification, "value") else str(a.verification or "VERIFIED"),
            "summary": a.summary or f"Xác nhận cháy thực tế tại {a.cam_name}",
            "detail": a.detail or f"Người dùng đã xác nhận cháy thực tế tại khu vực {a.location_name or a.subgroup_name}",
        },
        escalation_level=1,
    )

    # 2. Dispatch FCM to ALL members
    fcm = get_fcm_service()
    async def dispatch_fcm():
        members = group_repo.list_members(a.group_id)
        all_tokens = []
        for m in members:
            u = user_repo.get_user_by_id(m.user_id)
            if u and u.fcm_tokens:
                all_tokens.extend(u.fcm_tokens)
        if all_tokens:
            await asyncio.to_thread(
                fcm.send_fire_alert_push,
                fcm_tokens=all_tokens,
                alert_id=alert_id,
                escalation_level=1,
            )

    await asyncio.gather(ws_broadcast, dispatch_fcm(), return_exceptions=True)

    return {
        "alert_id": alert_id,
        "status": "CONFIRMED",
        "address": address,
        "message": "Đã kích hoạt còi báo động khẩn cấp tới toàn bộ thành viên",
    }


@router.get("/{alert_id}/dispatch-info")
async def get_dispatch_info(
    alert_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    alert_repo = get_alert_repository()
    group_repo = get_group_repository()
    user_repo = get_user_repository()

    a = alert_repo.get_alert(alert_id)
    if not a:
        raise NotFoundException("Không tìm thấy sự cố báo động.")

    member = group_repo.get_member(a.group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không thuộc nhóm sở hữu sự cố này.")

    group = group_repo.get_group(a.group_id)
    address = group.address if group else "Hiện trường cơ sở"
    facility_name = group.group_name if group else "Cơ sở"
    call_script = f"Báo cháy khẩn cấp tại: {address}, khu vực {a.location_name or a.subgroup_name}."

    members = group_repo.list_members(a.group_id)
    contacts = []
    for m in members:
        if m.role in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
            u = user_repo.get_user_by_id(m.user_id)
            if u:
                contacts.append({
                    "user_id": u.user_id,
                    "full_name": u.full_name,
                    "phone_number": u.phone_number,
                    "role": m.role.value if hasattr(m.role, "value") else str(m.role),
                })

    return {
        "alert_id": a.alert_id,
        "facility_name": facility_name,
        "address": address,
        "location_name": a.location_name or a.subgroup_name,
        "cam_name": a.cam_name,
        "status": a.status.value if hasattr(a.status, "value") else str(a.status),
        "call_script": call_script,
        "emergency_contacts": contacts,
        "still_url": a.still_url or a.fire_image_url,
        "detected_at": format_iso_utc(a.detected_at),
        "called_114_at": format_iso_utc(a.called_114_at),
    }


@router.get("/{alert_id}/audit-logs")
async def get_alert_audit_logs(
    alert_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    alert_repo = get_alert_repository()
    group_repo = get_group_repository()
    user_repo = get_user_repository()

    a = alert_repo.get_alert(alert_id)
    if not a:
        raise NotFoundException("Không tìm thấy sự cố báo động.")

    member = group_repo.get_member(a.group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không thuộc nhóm sở hữu sự cố này.")

    target = f"alert:{alert_id}"
    logs = alert_repo.list_audit_logs_by_target(target)

    logs_dto = []
    for log in logs:
        actor_name = log.details.get("actor_name") if log.details else None
        if not actor_name and log.actor_id:
            u = user_repo.get_user_by_id(log.actor_id)
            actor_name = u.full_name if u else "Thành viên"
        elif not actor_name:
            actor_name = "Hệ thống"

        logs_dto.append({
            "log_id": log.log_id,
            "action": log.action.value if hasattr(log.action, "value") else str(log.action),
            "actor_id": log.actor_id,
            "actor_name": actor_name,
            "target_entity": log.target_entity,
            "details": log.details,
            "created_at": format_iso_utc(log.created_at),
        })

    return {
        "alert_id": alert_id,
        "items": logs_dto,
        "total": len(logs_dto),
    }
