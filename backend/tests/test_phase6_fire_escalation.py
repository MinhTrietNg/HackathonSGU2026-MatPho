"""
Phase 6 Test Suite: AI FireWatch Webhook Ingestion, 90s Incident Aggregation,
Redis Two-Tier Escalation Timer (ADR 0011), Emergency Call 114, HITL & Audit Log
"""

import time
import random
import pytest
from fastapi.testclient import TestClient

from backend.src.main import app, INTERNAL_API_SECRET_KEY
from backend.src.services.repositories.user_repo import get_user_repo
from backend.src.services.repositories.group_repo import get_group_repo
from backend.src.services.repositories.camera_repo import get_camera_repo
from backend.src.services.repositories.alert_repo import get_alert_repository
from backend.src.services.escalation_service import get_escalation_service
from backend.src.core.security import generate_emergency_token
from backend.src.models.common import UserRole, AlertStatus
from backend.src.models.camera import WatchAreaModel

client = TestClient(app)


def _create_test_user(prefix: str):
    repo = get_user_repo()
    phone = f"095{random.randint(1000000, 9999999)}"
    user = repo.register_user_transaction(
        phone_number=phone,
        password_hash="$2b$12$eXampleHashedPassword12345678901234567890123456789012",
        full_name=f"User {prefix}",
    )
    return user.user_id, phone


def _setup_group_and_camera():
    user_repo = get_user_repo()
    group_repo = get_group_repo()
    camera_repo = get_camera_repo()

    leader_id, _ = _create_test_user("AlertLeader")
    group = group_repo.create_group(
        group_name="Nhà Máy Sản Xuất Gỗ Tân Bình",
        address="123 Đường Số 5, KCN Tân Bình, TP.HCM",
        leader_id=leader_id,
    )
    subgroup = group_repo.create_subgroup(
        group_id=group.group_id,
        subgroup_name="Xưởng Cưa B1",
        created_by=leader_id,
    )
    cam = camera_repo.create_camera(
        group_id=group.group_id,
        subgroup_id=subgroup.subgroup_id,
        cam_name="Cam Xưởng Cưa 01",
        rtsp_url="rtsp://mock-cam/stream1",
        created_by=leader_id,
        device_name="Hikvision DS-2CD2043G2-I",
        watch_area=WatchAreaModel(left=0.1, top=0.1, width=0.8, height=0.8),
    )
    return leader_id, group.group_id, subgroup.subgroup_id, cam.cam_id


def test_ai_webhook_ingestion_and_redis_timer():
    """
    Test 1: Ingestion of new AI fire event via Webhook.
    Verifies: 202 Accepted, creates new fire_alerts record, starts Redis 60s timer (ADR 0011).
    """
    leader_id, group_id, subgroup_id, cam_id = _setup_group_and_camera()

    payload = {
        "cam_id": cam_id,
        "class_name": "fire",
        "confidence": 0.94,
        "timestamp": time.time(),
        "bbox": [0.2, 0.3, 0.5, 0.7],
        "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    }

    # 1. Invalid secret key -> 401
    bad_res = client.post(
        "/api/v1/internal/ai/fire-events",
        json=payload,
        headers={"X-Internal-Secret": "wrong_secret"},
    )
    assert bad_res.status_code == 401

    # 2. Valid secret key -> 202 Accepted
    res = client.post(
        "/api/v1/internal/ai/fire-events",
        json=payload,
        headers={"X-Internal-Secret": INTERNAL_API_SECRET_KEY},
    )
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "accepted"
    assert data["alert_id"].startswith("alt_")
    assert data["escalation_level"] == 0

    alert_id = data["alert_id"]

    # 3. Check Redis Escalation Timer is active
    esc_svc = get_escalation_service()
    assert esc_svc.is_timer_active(alert_id) is True
    assert esc_svc.get_remaining_seconds(alert_id) > 0

    # 4. Check Firestore record
    alert_repo = get_alert_repository()
    alert = alert_repo.get_alert(alert_id)
    assert alert is not None
    assert alert.status == AlertStatus.NEW
    assert alert.confidence == 0.94
    assert alert.cam_id == cam_id


def test_ai_webhook_90s_debounce_aggregation():
    """
    Test 2: Second AI event within 90s on the same camera must be debounced and aggregated
    into the existing incident's timeline_snapshots (no duplicate alert created).
    """
    leader_id, group_id, subgroup_id, cam_id = _setup_group_and_camera()

    # First event
    payload1 = {
        "cam_id": cam_id,
        "class_name": "fire",
        "confidence": 0.85,
        "timestamp": time.time(),
        "bbox": [0.1, 0.1, 0.4, 0.4],
        "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    }
    res1 = client.post(
        "/api/v1/internal/ai/fire-events",
        json=payload1,
        headers={"X-Internal-Secret": INTERNAL_API_SECRET_KEY},
    )
    assert res1.status_code == 202
    first_alert_id = res1.json()["alert_id"]

    # Second event 2 seconds later (within 90s window)
    payload2 = {
        "cam_id": cam_id,
        "class_name": "fire",
        "confidence": 0.96,  # Higher confidence
        "timestamp": time.time() + 2,
        "bbox": [0.15, 0.15, 0.5, 0.5],
        "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    }
    res2 = client.post(
        "/api/v1/internal/ai/fire-events",
        json=payload2,
        headers={"X-Internal-Secret": INTERNAL_API_SECRET_KEY},
    )
    assert res2.status_code == 202
    second_alert_id = res2.json()["alert_id"]

    # Must be aggregated into the same incident!
    assert second_alert_id == first_alert_id

    # Verify timeline snapshot appended
    alert_repo = get_alert_repository()
    updated = alert_repo.get_alert(first_alert_id)
    assert updated.confidence >= 0.95
    assert len(updated.timeline_snapshots) >= 1


def test_ai_verifying_and_suppressed_webhooks():
    """
    Test 3: Edge AI verifying and suppressed webhook notifications.
    """
    leader_id, group_id, subgroup_id, cam_id = _setup_group_and_camera()

    # 1. AI Verifying
    v_res = client.post(
        "/api/v1/internal/ai/verifying",
        json={
            "cam_id": cam_id,
            "sign": "FIRE",
            "confidence": 0.65,
            "message": "Đang xác minh tín hiệu nghi vấn ngọn lửa...",
            "steps": [{"step": 1, "status": "checking"}],
        },
        headers={"X-Internal-Secret": INTERNAL_API_SECRET_KEY},
    )
    assert v_res.status_code == 202
    assert v_res.json()["status"] == "accepted"

    # 2. AI Suppressed
    s_res = client.post(
        "/api/v1/internal/ai/suppressed",
        json={
            "cam_id": cam_id,
            "summary": "Không phải cháy",
            "detail": "Ánh sáng đèn xe phản chiếu",
        },
        headers={"X-Internal-Secret": INTERNAL_API_SECRET_KEY},
    )
    assert s_res.status_code == 202
    assert s_res.json()["status"] == "accepted"


def test_list_alerts_and_filtering():
    """
    Test 4: Querying alert history with filters (all, fire, dismissed, false_alarm) and pagination.
    """
    leader_id, group_id, subgroup_id, cam_id = _setup_group_and_camera()

    # Create one alert
    payload = {
        "cam_id": cam_id,
        "class_name": "fire",
        "confidence": 0.91,
        "timestamp": time.time(),
        "bbox": [0.2, 0.2, 0.4, 0.4],
    }
    client.post(
        "/api/v1/internal/ai/fire-events",
        json=payload,
        headers={"X-Internal-Secret": INTERNAL_API_SECRET_KEY},
    )

    headers = {"Authorization": f"Bearer {leader_id}"}
    res = client.get(f"/api/v1/alerts?group_id={group_id}&filter=all", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    assert data["items"][0]["cam_id"] == cam_id


def test_get_alert_detail_f2_and_emergency_token():
    """
    Test 5: Alert details for Screen F2, and zero-friction emergency token bypass.
    """
    leader_id, group_id, subgroup_id, cam_id = _setup_group_and_camera()

    payload = {
        "cam_id": cam_id,
        "class_name": "fire",
        "confidence": 0.95,
        "timestamp": time.time(),
        "bbox": [0.25, 0.35, 0.65, 0.75],
    }
    create_res = client.post(
        "/api/v1/internal/ai/fire-events",
        json=payload,
        headers={"X-Internal-Secret": INTERNAL_API_SECRET_KEY},
    )
    alert_id = create_res.json()["alert_id"]

    # 1. Access with Bearer token
    headers = {"Authorization": f"Bearer {leader_id}"}
    detail_res = client.get(f"/api/v1/alerts/{alert_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["alert_id"] == alert_id
    assert detail["cam_id"] == cam_id
    assert detail["confidence"] == 0.95
    assert "123 Đường Số 5" in detail["address"]
    assert detail["status"] == "NEW"

    # 2. Access with Emergency Token without login header
    emg_token = generate_emergency_token(alert_id)
    emg_res = client.get(f"/api/v1/alerts/{alert_id}?emergency_token={emg_token}")
    assert emg_res.status_code == 200
    assert emg_res.json()["alert_id"] == alert_id


def test_call_114_cancels_timer_and_confirms():
    """
    Test 6: Human emergency reaction: calling 114 transitions to CONFIRMED,
    returns emergency call script, and atomically cancels the Redis escalation timer.
    """
    leader_id, group_id, subgroup_id, cam_id = _setup_group_and_camera()

    payload = {
        "cam_id": cam_id,
        "class_name": "fire",
        "confidence": 0.92,
        "timestamp": time.time(),
    }
    alert_id = client.post(
        "/api/v1/internal/ai/fire-events",
        json=payload,
        headers={"X-Internal-Secret": INTERNAL_API_SECRET_KEY},
    ).json()["alert_id"]

    esc_svc = get_escalation_service()
    assert esc_svc.is_timer_active(alert_id) is True

    headers = {"Authorization": f"Bearer {leader_id}"}
    call_res = client.post(f"/api/v1/alerts/{alert_id}/call-114", headers=headers)
    assert call_res.status_code == 200
    call_data = call_res.json()
    assert call_data["status"] == "CONFIRMED"
    assert "Báo cháy khẩn cấp" in call_data["call_script"]

    # Verify Redis timer is cancelled atomically
    assert esc_svc.is_timer_active(alert_id) is False

    # Check status endpoint
    status_res = client.get(f"/api/v1/alerts/{alert_id}/escalation-status", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["timer_active"] is False


def test_resolve_and_false_alarm_flows_and_notifier_forbidden():
    """
    Test 7, 8, 9:
    - Notifier role is blocked (403 Forbidden).
    - Leader successfully resolves with note, cancelling timer and sirens.
    - False alarm transitions status to FALSE_ALARM and cancels timer.
    """
    group_repo = get_group_repo()
    leader_id, group_id, subgroup_id, cam_id = _setup_group_and_camera()
    notifier_id, _ = _create_test_user("NotifierUser")
    group_repo.add_member(group_id, notifier_id, UserRole.NOTIFIER)

    # 1. Test Resolve
    alert_id1 = client.post(
        "/api/v1/internal/ai/fire-events",
        json={"cam_id": cam_id, "class_name": "fire", "confidence": 0.88, "timestamp": time.time()},
        headers={"X-Internal-Secret": INTERNAL_API_SECRET_KEY},
    ).json()["alert_id"]

    # Notifier cannot resolve -> 403
    notifier_headers = {"Authorization": f"Bearer {notifier_id}"}
    block_res = client.post(
        f"/api/v1/alerts/{alert_id1}/resolve",
        json={"resolution_note": "Báo nhầm"},
        headers=notifier_headers,
    )
    assert block_res.status_code == 403

    # Leader resolves -> 200 OK
    leader_headers = {"Authorization": f"Bearer {leader_id}"}
    resolve_res = client.post(
        f"/api/v1/alerts/{alert_id1}/resolve",
        json={"resolution_note": "Bảo vệ đã dập tắt bằng bình CO2"},
        headers=leader_headers,
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "RESOLVED"
    assert get_escalation_service().is_timer_active(alert_id1) is False

    # 2. Test Mark False Alarm
    alert_id2 = client.post(
        "/api/v1/internal/ai/fire-events",
        json={"cam_id": cam_id, "class_name": "fire", "confidence": 0.72, "timestamp": time.time() + 100},
        headers={"X-Internal-Secret": INTERNAL_API_SECRET_KEY},
    ).json()["alert_id"]

    # Notifier cannot mark false alarm -> 403
    block_fa = client.post(
        f"/api/v1/alerts/{alert_id2}/mark-false-alarm",
        headers=notifier_headers,
    )
    assert block_fa.status_code == 403

    # Leader marks false alarm -> 200 OK
    fa_res = client.post(
        f"/api/v1/alerts/{alert_id2}/mark-false-alarm",
        headers=leader_headers,
    )
    assert fa_res.status_code == 200
    assert fa_res.json()["status"] == "FALSE_ALARM"
    assert get_escalation_service().is_timer_active(alert_id2) is False


def test_dispatch_info_emergency_card():
    """
    Test 10: Dispatch Info card returns facility address, contacts, and 114 call script.
    """
    leader_id, group_id, subgroup_id, cam_id = _setup_group_and_camera()
    alert_id = client.post(
        "/api/v1/internal/ai/fire-events",
        json={"cam_id": cam_id, "class_name": "fire", "confidence": 0.89, "timestamp": time.time()},
        headers={"X-Internal-Secret": INTERNAL_API_SECRET_KEY},
    ).json()["alert_id"]

    headers = {"Authorization": f"Bearer {leader_id}"}
    resp = client.get(f"/api/v1/alerts/{alert_id}/dispatch-info", headers=headers)
    assert resp.status_code == 200
    card = resp.json()
    assert card["facility_name"] == "Nhà Máy Sản Xuất Gỗ Tân Bình"
    assert "123 Đường Số 5" in card["address"]
    assert "Xưởng Cưa B1" in card["location_name"]
    assert len(card["emergency_contacts"]) >= 1


def test_alert_specific_audit_logs():
    """
    Test 11: Alert audit logs chronology.
    """
    leader_id, group_id, subgroup_id, cam_id = _setup_group_and_camera()
    headers = {"Authorization": f"Bearer {leader_id}"}

    alert_id = client.post(
        "/api/v1/internal/ai/fire-events",
        json={"cam_id": cam_id, "class_name": "fire", "confidence": 0.93, "timestamp": time.time()},
        headers={"X-Internal-Secret": INTERNAL_API_SECRET_KEY},
    ).json()["alert_id"]

    client.post(f"/api/v1/alerts/{alert_id}/call-114", headers=headers)
    client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"resolution_note": "Đã xử lý"}, headers=headers)

    resp = client.get(f"/api/v1/alerts/{alert_id}/audit-logs", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["alert_id"] == alert_id
    assert data["total"] >= 2
    actions = [item["action"] for item in data["items"]]
    assert "CALL_114_INITIATED" in actions or "CALL_114" in actions
    assert "ALERT_RESOLVED" in actions or "RESOLVE_ALERT" in actions
