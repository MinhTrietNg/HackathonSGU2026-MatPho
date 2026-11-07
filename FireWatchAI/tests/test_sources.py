"""Heartbeat sampler and source-kind inference (pure logic, no model)."""

import numpy as np

from firewatch.sources import Frame, HeartbeatSampler, infer_kind


def _frames(fps: float, seconds: float):
    n = int(round(fps * seconds))
    img = np.zeros((4, 4, 3), dtype=np.uint8)
    for i in range(n):
        yield Frame(image=img, video_ts=i / fps, wall_time=0.0, index=i)


def test_heartbeat_grid_at_one_second():
    s = HeartbeatSampler(interval_s=1.0, ring_buffer=5)
    ts = [hb.frame.video_ts for f in _frames(25, 5) if (hb := s.push(f))]
    assert ts == [0.0, 1.0, 2.0, 3.0, 4.0]


def test_heartbeat_half_second_and_ring_size():
    s = HeartbeatSampler(interval_s=0.5, ring_buffer=3)
    hbs = [hb for f in _frames(10, 2) if (hb := s.push(f))]
    assert [round(h.frame.video_ts, 2) for h in hbs] == [0.0, 0.5, 1.0, 1.5]
    assert len(hbs[0].ring) == 1
    assert len(hbs[-1].ring) == 3
    assert hbs[-1].ring[-1] is hbs[-1].frame
    assert [h.seq for h in hbs] == [0, 1, 2, 3]


def test_heartbeat_skips_missed_ticks():
    s = HeartbeatSampler(interval_s=1.0)
    img = np.zeros((2, 2, 3), dtype=np.uint8)
    assert s.push(Frame(img, 0.0, 0.0, 0)) is not None
    # Khoảng trống 3.4 s (mất khung): chỉ 1 heartbeat, mốc kế tiếp là 4.0.
    assert s.push(Frame(img, 3.4, 0.0, 1)) is not None
    assert s.push(Frame(img, 3.9, 0.0, 2)) is None
    assert s.push(Frame(img, 4.0, 0.0, 3)) is not None


class _FakeCap:
    """Pretend camera: frames arrive fast; fails after ``fail_after`` reads."""

    instances = 0

    def __init__(self, *args, fail_after=10**9, delay=0.001):
        type(self).instances += 1
        self.n, self.fail_after, self.delay = 0, fail_after, delay

    def isOpened(self):
        return True

    def get(self, prop):
        return 30.0

    def read(self):
        import time
        time.sleep(self.delay)
        if self.n >= self.fail_after:
            return False, None
        self.n += 1
        return True, np.full((2, 2, 3), self.n % 255, dtype=np.uint8)

    def release(self):
        pass


def test_camera_source_serves_latest_frame_and_counts_drops(monkeypatch):
    import time

    from firewatch import sources

    monkeypatch.setattr(sources.cv2, "VideoCapture", lambda *a, **k: _FakeCap())
    src = sources.CameraSource("0")
    with src:
        f1 = src.read()
        time.sleep(0.1)          # consumer bận: camera đã đẩy ~100 khung
        f2 = src.read()
        assert f2.index > f1.index + 10, "phải nhận khung MỚI NHẤT, không xếp hàng"
        assert src.dropped == f2.index - f1.index - 1
        assert f2.video_ts > f1.video_ts and f2.wall_time >= f1.wall_time
        f3 = src.read()
        assert f3.index > f2.index


def test_camera_source_reconnects_then_gives_up(monkeypatch):
    from firewatch import sources

    _FakeCap.instances = 0

    def factory(*a, **k):
        # Cap đầu cho 3 khung rồi chết; mọi cap mở lại đều chết ngay.
        return _FakeCap(fail_after=3 if _FakeCap.instances == 0 else 0)

    monkeypatch.setattr(sources.cv2, "VideoCapture", factory)
    src = sources.CameraSource("0", reconnect_s=0.01, max_reconnects=2)
    with src:
        got = []
        while (f := src.read()) is not None:
            got.append(f.index)
            if len(got) > 20:
                break
        assert got == [0, 1, 2] or (got and got[-1] <= 2)
        assert _FakeCap.instances == 3   # 1 lần mở đầu + 2 lần mở lại rồi bỏ cuộc


def test_infer_kind():
    assert infer_kind("0") == "webcam"
    assert infer_kind("rtsp://10.0.0.5/live") == "rtsp"
    assert infer_kind("data/samples/fire_bus_01.webm") == "file"
