import threading
import time
from fractions import Fraction

import av
import numpy as np
import pytest

from src import branches
from src.branches import AiBranch
from src.config import DecoderSettings
from src.endpoints import StreamInfo
from src.stats import SessionStats

INFO = StreamInfo("h264", 1280, 720, 25.0)


def frame(i=0):
    f = av.VideoFrame.from_ndarray(np.zeros((720, 1280, 3), np.uint8), format="rgb24")
    f.pts = i
    f.time_base = Fraction(1, 25)
    return f


class BlockedSink:
    """Sink whose write blocks until released, like a stalled network publish."""

    release = threading.Event()
    created = 0

    def __init__(self, *args, **kwargs):
        type(self).created += 1

    def write(self, frame, pts):
        self.release.wait(10)

    def close(self):
        pass


def test_slow_publisher_never_blocks_the_caller(monkeypatch):
    BlockedSink.release = threading.Event()
    monkeypatch.setattr(branches, "H264Sink", BlockedSink)
    stats = SessionStats()
    ai = AiBranch("x.mkv", INFO, DecoderSettings(ai_queue_size=2), stats)
    ai.start()
    t0 = time.monotonic()
    for i in range(200):
        assert ai.submit(frame(i), i / 3) is True
    assert time.monotonic() - t0 < 2.0
    assert stats.ai_frames_submitted == 200
    assert stats.ai_frames_dropped >= 190
    BlockedSink.release.set()
    ai.close()


def test_close_gives_up_on_a_stuck_worker(monkeypatch):
    BlockedSink.release = threading.Event()
    monkeypatch.setattr(branches, "H264Sink", BlockedSink)
    ai = AiBranch("x.mkv", INFO, DecoderSettings(ai_queue_size=1), SessionStats())
    ai.start()
    for i in range(5):
        ai.submit(frame(i), float(i))
    time.sleep(0.1)
    t0 = time.monotonic()
    ai.close(timeout=0.3)
    assert time.monotonic() - t0 < 1.0
    BlockedSink.release.set()


def test_queue_keeps_the_newest_frames(monkeypatch):
    seen = []
    in_flight = threading.Event()

    class Recorder(BlockedSink):
        def write(self, frame, pts):
            if not seen:
                in_flight.set()
                self.release.wait(10)
            seen.append(pts)

    BlockedSink.release = threading.Event()
    monkeypatch.setattr(branches, "H264Sink", Recorder)
    ai = AiBranch("x.mkv", INFO, DecoderSettings(ai_queue_size=2), SessionStats())
    ai.start()
    ai.submit(frame(0), 0.0)
    assert in_flight.wait(2.0)
    for i in range(1, 20):
        ai.submit(frame(i), float(i))
    BlockedSink.release.set()
    ai.close()
    assert seen[0] == 0
    assert seen[1:] == [18 * 90_000, 19 * 90_000]


def test_worker_failure_is_reported_and_isolated(monkeypatch):
    class Failing:
        def __init__(self, *args, **kwargs):
            raise ConnectionRefusedError("publish refused")

    monkeypatch.setattr(branches, "H264Sink", Failing)
    ai = AiBranch("x.mkv", INFO, DecoderSettings(), SessionStats())
    ai.start()
    deadline = time.monotonic() + 3
    while not ai.failed and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ai.failed
    assert isinstance(ai.error, ConnectionRefusedError)
    assert ai.submit(frame(), 0.0) is False
    ai.close()


def test_timestamps_are_relative_to_first_frame_in_90khz(monkeypatch):
    seen = []

    class Recorder(BlockedSink):
        def write(self, frame, pts):
            seen.append(pts)

    monkeypatch.setattr(branches, "H264Sink", Recorder)
    ai = AiBranch("x.mkv", INFO, DecoderSettings(ai_queue_size=10), SessionStats())
    ai.start()
    for t in (500.0, 500.4, 501.0):
        ai.submit(frame(), t)
    ai.close()
    assert seen == [0, 36_000, 90_000]


def test_output_size_is_derived_from_source_and_limit():
    ai = AiBranch("x.mkv", INFO, DecoderSettings(ai_max_edge=320), SessionStats())
    assert ai.size == (320, 180)


@pytest.mark.parametrize("close_twice", [False, True])
def test_close_without_start_or_twice_is_safe(close_twice):
    ai = AiBranch("x.mkv", INFO, DecoderSettings(), SessionStats())
    ai.close()
    if close_twice:
        ai.close()
