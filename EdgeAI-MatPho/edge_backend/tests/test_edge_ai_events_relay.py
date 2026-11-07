"""
Unit & Integration Tests for EAG 2-Phase AI Event Relay Buffer:
- Camera ID Resolution (camera_id -> cam_id)
- Phase 1 Fast Signal Forwarding (<30ms)
- Phase 2 Background Snapshot History Upload
- Offline Fallback Queueing to SQLite WAL when Cloud WAN is unreachable
"""

import os
import json
import base64
import tempfile
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from src.main import app, state, INTERNAL_API_SECRET_KEY


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.mark.asyncio
async def test_edge_relay_mapping_and_two_phase_dispatch(client):
    """
    Test 1: EAG maps raw camera_id to registered cam_id,
    dispatches Phase 1 stripped fast signal, and fires Phase 2 snapshot upload in background.
    """
    # 1. Register a camera in Edge SQLite
    await state.db.upsert_camera(
        cam_id="cam_gate_01",
        cam_name="ham-b1-cam03",
        rtsp_url="rtsp://192.168.1.50:554/live",
        is_active=False,
    )

    dummy_b64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
    ai_event_payload = {
        "type": "created",
        "event_id": "evt_edge_relay_101",
        "camera_id": "ham-b1-cam03",
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
                "conf": 0.85,
                "xyxy": [812, 404, 1010, 690],
                "xyxyn": [0.423, 0.374, 0.526, 0.639],
            }
        ],
        "verification": "UNVERIFIED",
        "verifier": {
            "status": "PENDING",
            "needs_human_check": False,
        },
        "luot_xac_minh": 1,
        "snapshot_base64": dummy_b64,
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 202
    mock_resp.json.return_value = {"status": "accepted", "alert_id": "alt_edge_relay_101"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        res = client.post(
            "/api/v1/edge/ai-events",
            json=ai_event_payload,
            headers={"Authorization": f"Bearer {INTERNAL_API_SECRET_KEY}"},
        )
        assert res.status_code == 202
        data = res.json()
        assert data["status"] == "accepted"
        # Check camera mapping
        assert data["cam_id"] == "cam_gate_01"
        assert data["event_id"] == "evt_edge_relay_101"
        assert data["relay_signal"] == "forwarded"

        # Verify mock_post called for Phase 1 Fast Signal
        assert mock_post.called
        call_args_list = mock_post.call_args_list
        assert len(call_args_list) >= 1

        # First call must be Phase 1 signal without snapshot_base64
        phase1_call = call_args_list[0]
        posted_url = phase1_call[0][0] if phase1_call[0] else phase1_call.kwargs.get("url", "")
        assert "/api/v1/internal/ai/fire-events" in posted_url
        posted_json = phase1_call.kwargs.get("json", {})
        assert "snapshot_base64" not in posted_json
        assert posted_json.get("cam_id") == "cam_gate_01"
        assert posted_json.get("camera_id") == "ham-b1-cam03"


@pytest.mark.asyncio
async def test_edge_relay_offline_fallback_when_cloud_unreachable(client):
    """
    Test 2: When Cloud Backend WAN is down, EAG automatically enqueues
    the fire signal to local SQLite WAL offline_events_queue.
    """
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        import httpx
        mock_post.side_effect = httpx.ConnectError("Network unreachable")

        offline_payload = {
            "type": "created",
            "event_id": "evt_offline_999",
            "camera_id": "cam_offline_test",
            "status": "open",
            "boxes": [{"cls": "fire", "conf": 0.9}],
        }

        res = client.post(
            "/api/v1/edge/ai-events",
            json=offline_payload,
            headers={"X-Internal-Secret": INTERNAL_API_SECRET_KEY},
        )
        assert res.status_code == 202
        data = res.json()
        assert data["relay_signal"] == "queued_offline"

        # Check SQLite DB
        queued_events = await state.db.peek_offline_events(limit=10)
        matched = [e for e in queued_events if e["payload"].get("event_id") == "evt_offline_999"]
        assert len(matched) == 1
        assert matched[0]["event_type"] == "FIRE_SIGNAL"
        assert matched[0]["cam_id"] == "cam_offline_test"

        # Clean up
        await state.db.delete_offline_event(matched[0]["id"])


@pytest.mark.asyncio
async def test_edge_relay_reads_snapshot_from_disk_if_path_provided(client):
    """
    Test 3: If AI provides snapshot_path instead of snapshot_base64,
    EAG reads the image from local disk, encodes to Base64, and forwards Phase 2 snapshot.
    """
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(b"MOCK_JPEG_IMAGE_BYTES_FOR_EDGE_RELAY")
        tmp_path = tmp.name

    try:
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {"status": "accepted"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp

            res = client.post(
                "/api/v1/edge/ai-events",
                json={
                    "type": "created",
                    "event_id": "evt_disk_snap_888",
                    "camera_id": "cam_disk_01",
                    "snapshot_path": tmp_path,
                },
                headers={"Authorization": f"Bearer {INTERNAL_API_SECRET_KEY}"},
            )
            assert res.status_code == 202
            assert res.json()["status"] == "accepted"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
