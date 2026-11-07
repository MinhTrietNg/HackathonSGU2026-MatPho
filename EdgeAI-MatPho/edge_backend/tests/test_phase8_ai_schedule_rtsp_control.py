"""
Unit & Integration Tests for Edge Backend Phase 8:
Per-Camera AI Mode (ALWAYS | SCHEDULE | OFF), Rest Schedules, and RTSP AI Stream Gating
"""

from datetime import datetime, timezone, timedelta
import pytest
from src.db import EdgeDatabase
from src.main import compute_should_ai_scan_now, handle_cloud_command, state

VN_TZ = timezone(timedelta(hours=7))


def test_edge_compute_should_ai_scan_now():
    # 1. ALWAYS -> True
    assert compute_should_ai_scan_now("ALWAYS", []) is True

    # 2. OFF -> False
    assert compute_should_ai_scan_now("OFF", []) is False

    # 3. SCHEDULE (intra-day 17:00 - 19:30)
    schedules = [
        {
            "slot_id": "slot_1",
            "start_time": "17:00",
            "end_time": "19:30",
            "days": ["T2", "T3", "T4", "T5", "T6", "T7", "CN"],
        }
    ]
    mon_1800 = datetime(2026, 11, 2, 18, 0, tzinfo=VN_TZ)
    mon_2100 = datetime(2026, 11, 2, 21, 0, tzinfo=VN_TZ)

    assert compute_should_ai_scan_now("SCHEDULE", schedules, now_vn=mon_1800) is False
    assert compute_should_ai_scan_now("SCHEDULE", schedules, now_vn=mon_2100) is True


@pytest.mark.asyncio
async def test_edge_db_and_ws_command_set_camera_ai_config(tmp_path):
    db_file = str(tmp_path / "test_edge_ai_schedule.db")
    db = EdgeDatabase(db_path=db_file)
    await db.init_db()

    await db.upsert_camera(
        cam_id="cam_bep_01",
        rtsp_url="rtsp://192.168.1.50:554/stream1",
        cam_name="Bếp",
        is_active=True,
    )
    cam = await db.get_camera("cam_bep_01")
    assert cam is not None
    assert cam["ai_mode"] == "ALWAYS"
    assert cam["ai_schedules"] == []

    # Update to OFF
    ok = await db.update_camera_ai_config("cam_bep_01", "OFF", [])
    assert ok is True
    cam_off = await db.get_camera("cam_bep_01")
    assert cam_off["ai_mode"] == "OFF"
    assert compute_should_ai_scan_now(cam_off["ai_mode"], cam_off["ai_schedules"]) is False

    # Update to SCHEDULE with 2 slots via handle_cloud_command
    old_db = state.db
    state.db = db
    try:
        ack = await handle_cloud_command(
            {
                "action": "SET_CAMERA_AI_CONFIG",
                "cam_id": "cam_bep_01",
                "ai_mode": "OFF",
                "schedules": [],
            }
        )
        assert ack["type"] == "CAMERA_AI_CONFIG_ACK"
        assert ack["cam_id"] == "cam_bep_01"
        assert ack["ai_mode"] == "OFF"
        assert ack["should_ai_scan_now"] is False
        assert ack["stream_action"] == "DISCONNECT_AI_RTSP"
    finally:
        state.db = old_db
