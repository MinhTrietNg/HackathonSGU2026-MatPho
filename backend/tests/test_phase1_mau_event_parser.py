"""
Unit Tests for Phase 1: FireWatch AI 18-Field Contract & mau_event.json Parser
"""

import json
from pathlib import Path
import pytest
from fastapi import HTTPException

try:
    from src.models.fire_alert import (
        AIFireEventPayload,
        AISnapshotUploadPayload,
        AIEventBoxModel,
        AIVLMResultModel,
        AIVerifierModel,
        FireAlertModel,
    )
    from src.core.security import verify_internal_secret
    from src.core.config import settings
except ImportError:
    from backend.src.models.fire_alert import (
        AIFireEventPayload,
        AISnapshotUploadPayload,
        AIEventBoxModel,
        AIVLMResultModel,
        AIVerifierModel,
        FireAlertModel,
    )
    from backend.src.core.security import verify_internal_secret
    from backend.src.core.config import settings


def test_parse_mau_event_json():
    json_path = Path("docs/mau_event.json")
    assert json_path.exists(), "docs/mau_event.json must exist"

    with open(json_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # 1. Parse via AIFireEventPayload
    payload = AIFireEventPayload(**raw_data)

    assert payload.type == "created"
    assert payload.event_id == "7f3a8b21-4d92-4e89-9a71-89a1c2d3e4f5"
    assert payload.camera_id == "ham-b1-cam03"
    assert payload.status == "open"
    assert payload.severity == "WARNING"
    assert payload.fire_type == "UNCONTROLLED"
    assert payload.started_at == "2026-11-07T21:10:03+07:00"
    assert payload.last_seen_ts == "2026-11-07T21:12:33+07:00"
    assert payload.frame_ts == "2026-11-07T21:12:33+07:00"
    assert payload.frame_w == 1920
    assert payload.frame_h == 1080

    assert len(payload.boxes) == 1
    b0 = payload.boxes[0]
    assert b0.cls == "fire"
    assert b0.conf == 0.83
    assert b0.xyxy == [812, 404, 1010, 690]
    assert b0.xyxyn == [0.423, 0.374, 0.526, 0.639]

    assert payload.verification == "UNVERIFIED"
    assert payload.vlm is None
    assert payload.verifier is not None
    assert payload.verifier.status == "PENDING"
    assert payload.verifier.needs_human_check is False

    assert payload.luot_xac_minh == 1
    assert payload.snapshot_path == "snapshots/7f3a8b21.jpg"
    assert payload.snapshot_base64 is not None and len(payload.snapshot_base64) > 10


def test_verify_internal_secret_dual_headers():
    secret = settings.INTERNAL_API_SECRET_KEY

    # 1. Valid via X-Internal-Secret
    assert verify_internal_secret(x_internal_secret=secret, authorization=None) is True

    # 2. Valid via Authorization: Bearer <token>
    assert verify_internal_secret(x_internal_secret=None, authorization=f"Bearer {secret}") is True

    # 3. Valid via direct token in Authorization
    assert verify_internal_secret(x_internal_secret=None, authorization=secret) is True

    # 4. Valid with both present
    assert verify_internal_secret(x_internal_secret=secret, authorization=f"Bearer {secret}") is True

    # 5. Invalid secret raises UnauthorizedException / AppException (status_code 401)
    with pytest.raises(Exception) as excinfo:
        verify_internal_secret(x_internal_secret="wrong_secret", authorization=None)
    assert getattr(excinfo.value, "status_code", None) == 401

    with pytest.raises(Exception) as excinfo:
        verify_internal_secret(x_internal_secret=None, authorization="Bearer wrong_token")
    assert getattr(excinfo.value, "status_code", None) == 401

    with pytest.raises(Exception) as excinfo:
        verify_internal_secret(x_internal_secret=None, authorization=None)
    assert getattr(excinfo.value, "status_code", None) == 401


def test_snapshot_upload_payload():
    snap_payload = AISnapshotUploadPayload(
        event_id="7f3a8b21-4d92-4e89-9a71-89a1c2d3e4f5",
        cam_id="cam_01",
        frame_w=1920,
        frame_h=1080,
        boxes=[AIEventBoxModel(cls="fire", conf=0.91, xyxy=[100, 200, 300, 400], xyxyn=[0.1, 0.2, 0.3, 0.4])],
        snapshot_base64="/9j/4AAQSkZJRg==",
    )
    assert snap_payload.event_id == "7f3a8b21-4d92-4e89-9a71-89a1c2d3e4f5"
    assert snap_payload.cam_id == "cam_01"
    assert len(snap_payload.boxes) == 1
    assert snap_payload.boxes[0].cls == "fire"
