import pytest

from src.config import ConfigError, DecoderSettings
from src.manager import DecodeManager, StreamAlreadyRunning
from src.session import DecodeSession


def idle_attempt(spec, settings, stats, stop):
    stop.wait()


@pytest.fixture
def manager():
    m = DecodeManager(
        DecoderSettings(read_timeout_s=1.0),
        session_factory=lambda spec, s: DecodeSession(spec, s, attempt=idle_attempt),
    )
    yield m
    m.stop_all()


def test_start_derives_source_from_mediamtx(manager):
    spec = manager.start("cam_001")
    assert spec.source_url == "rtsp://mediamtx:8554/source/cam_001"
    assert spec.app_url == "rtsp://mediamtx:8554/live/cam_001"
    assert "cam_001" in manager.status()


def test_start_with_explicit_source(manager):
    spec = manager.start("cam_002", "rtsp://10.0.0.9:554/s")
    assert spec.source_url == "rtsp://10.0.0.9:554/s"
    assert spec.app_url == "rtsp://mediamtx:8554/live/cam_002"


def test_duplicate_start_rejected(manager):
    manager.start("cam_001")
    with pytest.raises(StreamAlreadyRunning):
        manager.start("cam_001")


def test_invalid_input_rejected_and_nothing_registered(manager):
    with pytest.raises(ConfigError):
        manager.start("bad/id")
    with pytest.raises(ConfigError):
        manager.start("cam_001", "http://not-rtsp")
    assert manager.status() == {}


def test_stop_known_and_unknown(manager):
    manager.start("cam_001")
    assert manager.stop("cam_001") is True
    assert manager.status() == {}
    assert manager.stop("cam_001") is False
    manager.start("cam_001")


def test_status_reports_every_camera(manager):
    manager.start("cam_001")
    manager.start("cam_002")
    status = manager.status()
    assert set(status) == {"cam_001", "cam_002"}
    assert all("state" in v for v in status.values())


def test_stop_all_stops_everything():
    sessions = []

    def factory(spec, settings):
        session = DecodeSession(spec, settings, attempt=idle_attempt)
        sessions.append(session)
        return session

    m = DecodeManager(DecoderSettings(read_timeout_s=1.0), session_factory=factory)
    for i in range(3):
        m.start(f"cam_{i}")
    m.stop_all()
    assert m.status() == {}
    assert all(not s.alive for s in sessions)
