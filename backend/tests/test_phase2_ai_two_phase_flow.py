"""
Unit & Integration Tests for Phase 2:
Two-Phase Signal-First Flow (Fast Signal <30ms + Single Snapshot History Upload)
and Event Updates / False-Alarm Suppression.
"""

import json
import uuid
import pytest
from fastapi.testclient import TestClient

try:
    from src.main import app, INTERNAL_API_SECRET_KEY
    from src.services.repositories.user_repo import get_user_repo
    from src.services.repositories.group_repo import get_group_repo
    from src.services.repositories.camera_repo import get_camera_repo
    from src.services.repositories.alert_repo import get_alert_repository
    from src.services.escalation_service import get_escalation_service
    from src.models.fire_alert import AlertStatus, AlertVerification
    from src.models.camera import WatchAreaModel
except ImportError:
    from backend.src.main import app, INTERNAL_API_SECRET_KEY
    from backend.src.services.repositories.user_repo import get_user_repo
    from backend.src.services.repositories.group_repo import get_group_repo
    from backend.src.services.repositories.camera_repo import get_camera_repo
    from backend.src.services.repositories.alert_repo import get_alert_repository
    from backend.src.services.escalation_service import get_escalation_service
    from backend.src.models.fire_alert import AlertStatus, AlertVerification
    from backend.src.models.camera import WatchAreaModel

client = TestClient(app)


def _setup_test_environment(suffix: str):
    user_repo = get_user_repo()
    group_repo = get_group_repo()
    camera_repo = get_camera_repo()

    phone = f"096{uuid.uuid4().int % 9000000 + 1000000}"
    user = user_repo.register_user_transaction(
        phone_number=phone,
        password_hash="$2b$12$eXampleHashedPassword12345678901234567890123456789012",
        full_name=f"User Phase2_{suffix}",
    )
    group = group_repo.create_group(
        group_name=f"Nhà Kho Thử Nghiệm {suffix}",
        address="Khu Chế Xuất Linh Trung, Thủ Đức",
        leader_id=user.user_id,
    )
    subgroup = group_repo.create_subgroup(
        group_id=group.group_id,
        subgroup_name=f"Khu Vực Băng Tải {suffix}",
        created_by=user.user_id,
    )
    cam = camera_repo.create_camera(
        group_id=group.group_id,
        subgroup_id=subgroup.subgroup_id,
        cam_name=f"Cam Băng Tải {suffix}",
        rtsp_url=f"rtsp://mock-cam/stream_{suffix}",
        created_by=user.user_id,
        device_name="Dahua IPC-HFW2431S-S-S2",
        watch_area=WatchAreaModel(left=0.0, top=0.0, width=1.0, height=1.0),
    )
    return user.user_id, group.group_id, cam.cam_id


def test_phase1_fast_signal_and_phase2_snapshot_flow():
    """
    Test End-to-End:
    1. Phase 1 Fast Signal ingestion (~0.6KB, without image):
       - Verifies 202 Accepted, Redis Escalation timer started, snapshot_status="PENDING".
    2. Phase 2 Background Snapshot upload:
       - Verifies 202 Accepted, single clean image saved to Firebase Storage, snapshot_status="READY".
       - Verifies timeline_snapshots has exactly 1 entry (Single Snapshot History).
    """
    user_id, group_id, cam_id = _setup_test_environment("e2e_flow")
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    secret = INTERNAL_API_SECRET_KEY

    # 1. Phase 1: Fast Signal Ingestion
    signal_payload = {
        "type": "created",
        "event_id": event_id,
        "camera_id": cam_id,
        "status": "open",
        "severity": "WARNING",
        "fire_type": "UNCONTROLLED",
        "started_at": "2026-11-07T21:10:03+07:00",
        "last_seen_ts": "2026-11-07T21:12:33+07:00",
        "frame_ts": "2026-11-07T21:12:33+07:00",
        "frame_w": 1920,
        "frame_h": 1080,
        "boxes": [
            {
                "cls": "fire",
                "conf": 0.88,
                "xyxy": [800, 400, 1000, 680],
                "xyxyn": [0.4167, 0.3704, 0.5208, 0.6296],
            }
        ],
        "verification": "UNVERIFIED",
        "verifier": {
            "status": "PENDING",
            "needs_human_check": False,
            "latency_ms": None,
            "reason": None,
        },
        "luot_xac_minh": 1,
        # Omit snapshot_base64 to simulate pure fast signal
    }

    # Use Authorization: Bearer <secret>
    res_signal = client.post(
        "/api/v1/internal/ai/fire-events",
        json=signal_payload,
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert res_signal.status_code == 202
    data_signal = res_signal.json()
    assert data_signal["status"] == "accepted"
    alert_id = data_signal["alert_id"]
    assert data_signal["type"] == "created"
    assert data_signal["escalation_level"] == 0

    # Verify Redis timer is started
    esc_svc = get_escalation_service()
    assert esc_svc.is_timer_active(alert_id) is True

    # Verify Firestore record created with PENDING snapshot
    alert_repo = get_alert_repository()
    alert_doc = alert_repo.get_alert(alert_id)
    assert alert_doc is not None
    assert alert_doc.cam_id == cam_id
    assert alert_doc.snapshot_status == "PENDING"
    assert len(alert_doc.boxes) == 1
    first_box = alert_doc.boxes[0]
    box_cls = first_box.get("cls") if isinstance(first_box, dict) else first_box.cls
    assert box_cls == "fire"
    assert alert_doc.frame_w == 1920
    assert alert_doc.frame_h == 1080

    # 2. Phase 2: Background Snapshot Upload
    dummy_b64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
    upload_payload = {
        "event_id": event_id,
        "cam_id": cam_id,
        "camera_id": cam_id,
        "frame_ts": "2026-11-07T21:12:33+07:00",
        "frame_w": 1920,
        "frame_h": 1080,
        "boxes": [
            {
                "cls": "fire",
                "conf": 0.88,
                "xyxy": [800, 400, 1000, 680],
                "xyxyn": [0.4167, 0.3704, 0.5208, 0.6296],
            }
        ],
        "snapshot_base64": dummy_b64,
    }

    res_upload = client.post(
        f"/api/v1/internal/ai/fire-events/{event_id}/snapshot",
        json=upload_payload,
        headers={"X-Internal-Secret": secret},
    )
    assert res_upload.status_code == 202
    data_upload = res_upload.json()
    assert data_upload["status"] == "snapshot_uploaded"
    assert data_upload["event_id"] == event_id
    assert "still_url" in data_upload and data_upload["still_url"]

    # Re-fetch alert doc and verify Single Snapshot History
    updated_doc = alert_repo.get_alert(alert_id)
    assert updated_doc.snapshot_status == "READY"
    assert updated_doc.still_url is not None
    assert updated_doc.fire_image_url is not None
    # Crucial: verify history contains exactly 1 snapshot entry (no 60-frame buildup)
    assert len(updated_doc.timeline_snapshots) == 1
    assert updated_doc.timeline_snapshots[0].frame_w == 1920
    assert len(updated_doc.timeline_snapshots[0].boxes) == 1


def test_updated_event_suppressed_cancels_redis_timer():
    """
    Test AI Event Update:
    When VLM or verifier completes and concludes SUPPRESSED / REJECTED:
    - Backend updates alert record to SUPPRESSED
    - Immediately cancels the 60s Redis escalation timer
    """
    user_id, group_id, cam_id = _setup_test_environment("suppress_flow")
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    secret = INTERNAL_API_SECRET_KEY
    esc_svc = get_escalation_service()

    # Step 1: Fire event created (unverified)
    res1 = client.post(
        "/api/v1/internal/ai/fire-events",
        json={
            "type": "created",
            "event_id": event_id,
            "camera_id": cam_id,
            "status": "open",
            "severity": "WARNING",
            "started_at": "2026-11-07T21:10:03+07:00",
            "last_seen_ts": "2026-11-07T21:10:03+07:00",
            "frame_ts": "2026-11-07T21:10:03+07:00",
            "frame_w": 1920,
            "frame_h": 1080,
            "boxes": [{"cls": "fire", "conf": 0.72, "xyxy": [100, 100, 200, 200], "xyxyn": [0.05, 0.09, 0.1, 0.18]}],
            "verification": "UNVERIFIED",
            "verifier": {"status": "PENDING", "needs_human_check": False},
        },
        headers={"X-Internal-Secret": secret},
    )
    assert res1.status_code == 202
    alert_id = res1.json()["alert_id"]
    assert esc_svc.is_timer_active(alert_id) is True

    # Step 2: AI completes analysis ~2s later, concludes SUPPRESSED (lamp reflection)
    res2 = client.post(
        "/api/v1/internal/ai/fire-events",
        json={
            "type": "updated",
            "event_id": event_id,
            "camera_id": cam_id,
            "status": "ended",
            "severity": "WARNING",
            "started_at": "2026-11-07T21:10:03+07:00",
            "last_seen_ts": "2026-11-07T21:10:05+07:00",
            "frame_ts": "2026-11-07T21:10:05+07:00",
            "frame_w": 1920,
            "frame_h": 1080,
            "boxes": [],
            "verification": "SUPPRESSED",
            "vlm": {
                "is_fire": False,
                "is_smoke": False,
                "confidence": 0.98,
                "description_vi": "Vật thể phát sáng từ đèn xe phản chiếu bề mặt sàn, không có nhiệt và khói.",
                "fire_type": "NONE",
            },
            "verifier": {
                "status": "REJECTED",
                "needs_human_check": False,
                "latency_ms": 1850,
                "reason": "lamp_reflection",
            },
            "luot_xac_minh": 2,
        },
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert res2.status_code == 202
    data2 = res2.json()
    assert data2["verification"] == "SUPPRESSED"

    # Step 3: Verify Timer was canceled
    assert esc_svc.is_timer_active(alert_id) is False

    # Step 4: Verify Firestore status is SUPPRESSED
    alert_repo = get_alert_repository()
    doc = alert_repo.get_alert(alert_id)
    assert doc.status == AlertStatus.SUPPRESSED
    assert doc.verification == AlertVerification.SUPPRESSED
    assert "đèn xe" in doc.detail or "phản chiếu" in doc.detail
