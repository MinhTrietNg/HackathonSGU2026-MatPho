"""
Unit Tests for Phase 2: Stream Fleet Manager & Presets System
"""

import io
import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from tool_test_rtsp.src.sample_generator import generate_sample_video
from tool_test_rtsp.src.stream_fleet_manager import StreamFleetManager


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory):
    vdir = tmp_path_factory.mktemp("fleet_vids")
    fpath = vdir / "sample_test.mp4"
    return generate_sample_video(str(fpath), duration_s=3, fps=20, width=480, height=270)


def test_add_and_remove_camera(sample_video):
    mgr = StreamFleetManager(mediamtx_host="localhost", mediamtx_port=8554)
    assert len(mgr.list_cameras()) == 0

    # Auto ID generation
    w1 = mgr.add_camera(video_path=sample_video)
    assert w1.cam_id == "cam_01"

    w2 = mgr.add_camera(video_path=sample_video)
    assert w2.cam_id == "cam_02"

    # Specific ID
    w_custom = mgr.add_camera(video_path=sample_video, cam_id="cam_gate_north", cam_name="Cổng Bắc")
    assert w_custom.cam_id == "cam_gate_north"
    assert w_custom.cam_name == "Cổng Bắc"

    cams = mgr.list_cameras()
    assert len(cams) == 3

    assert mgr.get_camera("cam_01") is w1
    assert mgr.get_camera("cam_unknown") is None

    # Remove camera
    removed = mgr.remove_camera("cam_01")
    assert removed is True
    assert mgr.get_camera("cam_01") is None
    assert len(mgr.list_cameras()) == 2

    mgr.clear()
    assert len(mgr.list_cameras()) == 0


def test_add_from_directory(tmp_path, sample_video):
    vdir = tmp_path / "video_pool"
    vdir.mkdir()

    # Create dummy video files or copy sample
    import shutil
    shutil.copy(sample_video, vdir / "gate_cam.mp4")
    shutil.copy(sample_video, vdir / "corridor_cam.avi")
    shutil.copy(sample_video, vdir / "parking_cam.mkv")
    (vdir / "notes.txt").write_text("not a video")

    mgr = StreamFleetManager()
    created_ids = mgr.add_from_directory(str(vdir))

    assert len(created_ids) == 3
    assert len(mgr.list_cameras()) == 3
    # Check that .txt was ignored
    for w in mgr.list_cameras():
        assert Path(w.video_path).suffix.lower() in (".mp4", ".avi", ".mkv")


def test_batch_controls(sample_video):
    mgr = StreamFleetManager()
    w1 = mgr.add_camera(video_path=sample_video, cam_id="cam_b1")
    w2 = mgr.add_camera(video_path=sample_video, cam_id="cam_b2")

    # Start all
    mgr.start_all()
    time.sleep(0.3)
    assert w1.is_running
    assert w2.is_running

    # Pause all
    mgr.pause_all()
    assert w1.is_paused
    assert w2.is_paused

    # Resume all
    mgr.resume_all()
    assert not w1.is_paused
    assert not w2.is_paused

    # Set speed all
    mgr.set_speed_all(2.0)
    assert w1.speed == 2.0
    assert w2.speed == 2.0

    # Seek all
    mgr.seek_all_seconds(1.0)
    time.sleep(0.1)

    # Status summary
    status = mgr.get_fleet_status()
    assert len(status) == 2
    assert status[0]["cam_id"] in ("cam_b1", "cam_b2")

    # Stop all
    mgr.stop_all()
    assert not w1.is_running
    assert not w2.is_running


def test_save_and_load_preset(tmp_path, sample_video):
    mgr = StreamFleetManager(mediamtx_host="192.168.1.100", mediamtx_port=8554)
    w1 = mgr.add_camera(video_path=sample_video, cam_id="cam_preset_1", cam_name="Cam 1")
    w1.set_speed(1.5)
    w2 = mgr.add_camera(video_path=sample_video, cam_id="cam_preset_2", cam_name="Cam 2")
    w2.set_speed(0.5)

    preset_file = tmp_path / "presets" / "office_cams.json"
    mgr.save_preset(str(preset_file))

    assert preset_file.is_file()

    # Clear manager and reload
    new_mgr = StreamFleetManager()
    loaded_ids = new_mgr.load_preset(str(preset_file))

    assert set(loaded_ids) == {"cam_preset_1", "cam_preset_2"}
    assert new_mgr.mediamtx_host == "192.168.1.100"
    
    lw1 = new_mgr.get_camera("cam_preset_1")
    assert lw1 is not None
    assert lw1.cam_name == "Cam 1"
    assert lw1.speed == 1.5

    lw2 = new_mgr.get_camera("cam_preset_2")
    assert lw2 is not None
    assert lw2.cam_name == "Cam 2"
    assert lw2.speed == 0.5


def test_sync_camera_to_edge_mock(sample_video):
    mgr = StreamFleetManager()
    mgr.add_camera(video_path=sample_video, cam_id="cam_01", cam_name="Cổng Chính")

    mock_response_data = {
        "status": "ONLINE",
        "cam_id": "cam_01",
        "hls_stream_url": "http://localhost:8888/live/cam_01/index.m3u8",
    }

    # 1. Successful HTTP 200 response
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = mgr.sync_camera_to_edge("cam_01", edge_api_url="http://localhost:8090")
        assert res["success"] is True
        assert res["status_code"] == 200
        assert res["registered_rtsp"] == "rtsp://mediamtx:8554/source/cam_01"

    # 2. Sync all
    with patch("urllib.request.urlopen", return_value=mock_resp):
        all_res = mgr.sync_all_to_edge(edge_api_url="http://localhost:8090")
        assert all_res["total"] == 1
        assert all_res["synced"] == 1

    # 3. Handle Edge Offline connection error
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        res_fail = mgr.sync_camera_to_edge("cam_01", edge_api_url="http://localhost:8090")
        assert res_fail["success"] is False
        assert "Connection refused" in res_fail["error"]
