"""
Unit Tests for Phase 1: Virtual Camera Worker & Sample Video Generator
"""

import os
import time
import pytest
from pathlib import Path

from tool_test_rtsp.src.sample_generator import generate_sample_video, ensure_default_sample_videos
from tool_test_rtsp.src.virtual_cam_worker import VirtualCamWorker


@pytest.fixture(scope="module")
def sample_video_path(tmp_path_factory):
    fn = tmp_path_factory.mktemp("videos") / "test_sim.mp4"
    path = generate_sample_video(str(fn), duration_s=4, fps=20, width=640, height=360, has_fire=True)
    return path


def test_generate_sample_video(sample_video_path):
    p = Path(sample_video_path)
    assert p.is_file()
    assert p.stat().st_size > 1000


def test_ensure_default_sample_videos(tmp_path):
    res = ensure_default_sample_videos(tmp_path)
    assert "normal" in res
    assert "fire" in res
    assert Path(res["normal"]).exists()
    assert Path(res["fire"]).exists()


def test_virtual_cam_worker_lifecycle_controls(sample_video_path):
    worker = VirtualCamWorker(
        cam_id="cam_test_01",
        cam_name="Camera Test Cổng 1",
        video_path=sample_video_path,
        target_rtsp_url="rtsp://127.0.0.1:8554/source/cam_test_01",
        fps=20,
        width=640,
        height=360,
    )

    assert not worker.is_running

    # 1. Start worker
    worker.start()
    assert worker.is_running
    time.sleep(0.5)

    # 2. Check initial state
    state = worker.get_state()
    assert state["cam_id"] == "cam_test_01"
    assert state["is_running"] is True
    assert state["duration_sec"] > 0
    assert state["speed"] == 1.0
    assert not state["is_paused"]

    # 3. Test Pause and Resume
    worker.pause()
    assert worker.is_paused
    time.sleep(0.2)
    state_paused = worker.get_state()
    assert state_paused["is_paused"] is True

    worker.resume()
    assert not worker.is_paused

    # 4. Test Speed change
    worker.set_speed(2.0)
    assert worker.speed == 2.0
    worker.set_speed(0.5)
    assert worker.speed == 0.5

    # 5. Test Seek
    worker.seek_to_second(2.0)
    time.sleep(0.2)
    worker.seek_to_ratio(0.8)
    time.sleep(0.2)

    # 6. Test Preview thumbnail
    thumb = worker.get_preview_thumbnail(max_w=160, max_h=90)
    assert thumb is not None
    assert thumb.shape[1] <= 160
    assert thumb.shape[0] <= 90

    # 7. Test Stop
    worker.stop()
    assert not worker.is_running
