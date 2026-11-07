import pytest
from src.config import ConfigError, DecoderSettings, StreamSpec, redact_text, redact_url, validate_cam_id


def test_validate_cam_id_valid():
    assert validate_cam_id("cam_01") == "cam_01"
    assert validate_cam_id("cam-front-gate") == "cam-front-gate"
    assert validate_cam_id("CAM_123") == "CAM_123"


def test_validate_cam_id_invalid():
    with pytest.raises(ConfigError):
        validate_cam_id("cam/../escape")
    with pytest.raises(ConfigError):
        validate_cam_id("cam with space")
    with pytest.raises(ConfigError):
        validate_cam_id("")


def test_redact_url():
    url = "rtsp://admin:secret123@192.168.1.100:554/live"
    redacted = redact_url(url)
    assert "secret123" not in redacted
    assert "admin:***@192.168.1.100:554/live" in redacted

    # Safe url without credentials
    url_safe = "rtsp://192.168.1.100:554/live"
    assert redact_url(url_safe) == url_safe


def test_redact_text():
    text = "Failed to connect to rtsp://admin:pass456@camera.lan:554/ch0 after 5 retries"
    cleaned = redact_text(text)
    assert "pass456" not in cleaned
    assert "admin:***@" in cleaned


def test_stream_spec_for_camera_standardized_paths():
    """Verify stream URLs strictly follow live/{cam_id} standardization (Q1)."""
    settings = DecoderSettings(mediamtx_rtsp_url="rtsp://mediamtx:8554")
    spec = StreamSpec.for_camera("cam_front", settings, "rtsp://192.168.1.50/stream")

    assert spec.cam_id == "cam_front"
    assert spec.source_url == "rtsp://192.168.1.50/stream"
    assert spec.app_url == "rtsp://mediamtx:8554/live/cam_front"
    assert spec.ai_url == "rtsp://mediamtx:8554/live/cam_front"
