"""
Unit / Integration Tests for Phase 3: Desktop GUI Studio
Tests the GUI structure, CameraCard components, seeking, and lifecycle in headless Tkinter.
"""

import time
import tkinter as tk
from unittest.mock import MagicMock, patch
import pytest

from tool_test_rtsp.src.gui_app import CameraCard, RTSPStudioApp
from tool_test_rtsp.src.sample_generator import generate_sample_video


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory):
    vdir = tmp_path_factory.mktemp("gui_vids")
    fpath = vdir / "gui_sample.mp4"
    return generate_sample_video(str(fpath), duration_s=3, fps=20, width=320, height=180)


@pytest.fixture
def tk_root():
    root = tk.Tk()
    root.withdraw()  # Headless mode for automated tests
    yield root
    try:
        root.destroy()
    except Exception:
        pass


def test_gui_app_initialization(tk_root):
    app = RTSPStudioApp(tk_root)
    assert app.fleet is not None
    assert len(app.cards) == 0
    assert "Mắt Phố" in tk_root.title()
    app._on_close()


def test_camera_card_lifecycle_and_controls(tk_root, sample_video):
    app = RTSPStudioApp(tk_root)
    worker = app.fleet.add_camera(
        video_path=sample_video,
        cam_id="cam_ui_01",
        cam_name="Cổng Tây",
        auto_start=True,
    )
    app._rebuild_card_ui()

    assert "cam_ui_01" in app.cards
    card = app.cards["cam_ui_01"]
    assert card.worker is worker

    # Allow worker to start and decode a frame
    time.sleep(0.4)
    card.update_ui()

    # Verify status reflects streaming
    assert card.lbl_status.cget("text") == "STREAMING"

    # Test speed change via button callback
    card._set_speed(2.0)
    assert worker.speed == 2.0

    # Test pause/resume toggle
    card._toggle_play_pause()
    time.sleep(0.1)
    card.update_ui()
    assert worker.is_paused
    assert card.lbl_status.cget("text") == "PAUSED"

    card._toggle_play_pause()
    time.sleep(0.1)
    card.update_ui()
    assert not worker.is_paused

    # Test slider seek
    card.seek_var.set(50.0)
    # Simulate slider release
    card._on_slider_release(None)
    time.sleep(0.2)

    # Test rewind
    card._rewind()
    time.sleep(0.2)

    # Test remove
    with patch("tkinter.messagebox.askyesno", return_value=True):
        app._handle_remove_camera("cam_ui_01")

    assert "cam_ui_01" not in app.cards
    assert len(app.fleet.list_cameras()) == 0

    app._on_close()


def test_action_generate_samples(tk_root, tmp_path):
    app = RTSPStudioApp(tk_root)
    with patch("tool_test_rtsp.src.gui_app.ensure_default_sample_videos") as mock_ensure:
        norm_file = tmp_path / "norm.mp4"
        fire_file = tmp_path / "fire.mp4"
        norm_file.write_text("dummy")
        fire_file.write_text("dummy")
        mock_ensure.return_value = {"normal": str(norm_file), "fire": str(fire_file)}

        with patch("tool_test_rtsp.src.virtual_cam_worker.VirtualCamWorker.start"):
            app._action_generate_samples()

    assert "cam_sample_normal" in app.cards
    assert "cam_sample_fire" in app.cards
    assert len(app.fleet.list_cameras()) == 2

    app._on_close()
