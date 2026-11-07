import pytest
from src.config import DecoderSettings, StreamSpec
from src.manager import DecodeManager, StreamAlreadyRunning
from src.stats import SessionStats


class DummySession:
    def __init__(self, spec: StreamSpec, settings: DecoderSettings):
        self.spec = spec
        self.settings = settings
        self.stats = SessionStats()
        self.alive = False

    def start(self):
        self.alive = True

    def stop(self, timeout=None):
        self.alive = False
        return True

    def request_stop(self):
        self.alive = False


def test_decode_manager_lifecycle():
    settings = DecoderSettings()
    manager = DecodeManager(settings, session_factory=DummySession)

    # 1. Start session
    spec = manager.start("cam_test", "rtsp://192.168.1.10/live")
    assert spec.cam_id == "cam_test"
    assert manager.is_running("cam_test") is True

    # 2. Cannot start duplicate
    with pytest.raises(StreamAlreadyRunning):
        manager.start("cam_test")

    # 3. Status map
    status_map = manager.status()
    assert "cam_test" in status_map
    assert "state" in status_map["cam_test"]

    # 4. Stop session
    stopped = manager.stop("cam_test")
    assert stopped is True
    assert manager.is_running("cam_test") is False
    assert manager.stop("unknown_cam") is False
