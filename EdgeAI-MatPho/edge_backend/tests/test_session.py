import threading
import time

import pytest

from src.config import DecoderSettings, StreamSpec
from src.session import DecodeSession
from src.stats import SessionState

FAST = DecoderSettings(
    backoff_initial_s=0.01, backoff_max_s=0.04, stable_after_s=3600.0
)
SPEC = StreamSpec(
    "cam_t",
    "rtsp://admin:s3cret@10.0.0.5:554/live/x",
    "rtsp://mediamtx:8554/live/cam_t",
    "rtsp://mediamtx:8554/ai/cam_t",
)


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_retries_after_failures_then_runs_until_stopped():
    calls = []

    def attempt(spec, settings, stats, stop):
        calls.append(time.monotonic())
        if len(calls) <= 3:
            raise ConnectionError("camera unreachable")
        stats.state = SessionState.RUNNING
        stop.wait()

    session = DecodeSession(SPEC, FAST, attempt=attempt)
    session.start()
    assert wait_for(lambda: len(calls) == 4)
    assert session.stats.restarts == 3
    assert "ConnectionError" in session.stats.last_error
    assert session.stop() is True
    assert session.stats.state is SessionState.STOPPED
    assert not session.alive


def test_end_of_stream_is_treated_as_disconnect():
    calls = []

    def attempt(spec, settings, stats, stop):
        calls.append(1)

    session = DecodeSession(SPEC, FAST, attempt=attempt)
    session.start()
    assert wait_for(lambda: len(calls) >= 3)
    assert session.stop()
    assert session.stats.restarts >= 2


def test_credentials_never_reach_last_error():
    def attempt(spec, settings, stats, stop):
        raise OSError(f"Connection refused: '{spec.source_url}'")

    session = DecodeSession(SPEC, FAST, attempt=attempt)
    session.start()
    assert wait_for(lambda: session.stats.last_error is not None)
    session.stop()
    assert "s3cret" not in session.stats.last_error
    assert "admin:***@10.0.0.5" in session.stats.last_error


def test_credentials_are_masked_even_if_the_url_is_quoted_differently():
    def attempt(spec, settings, stats, stop):
        raise OSError("401 Unauthorized for rtsp://admin:s3cret@10.0.0.5/other")

    session = DecodeSession(SPEC, FAST, attempt=attempt)
    session.start()
    assert wait_for(lambda: session.stats.last_error is not None)
    session.stop()
    assert "s3cret" not in session.stats.last_error


def test_unexpected_exception_does_not_kill_the_session():
    calls = []

    def attempt(spec, settings, stats, stop):
        calls.append(1)
        raise KeyError("bug")

    session = DecodeSession(SPEC, FAST, attempt=attempt)
    session.start()
    assert wait_for(lambda: len(calls) >= 3)
    assert session.alive
    assert session.stop()


def test_stop_interrupts_backoff_promptly():
    slow = DecoderSettings(backoff_initial_s=30.0, backoff_max_s=30.0)

    def attempt(spec, settings, stats, stop):
        raise ConnectionError("down")

    session = DecodeSession(SPEC, slow, attempt=attempt)
    session.start()
    assert wait_for(lambda: session.stats.state is SessionState.BACKOFF)
    t0 = time.monotonic()
    assert session.stop(timeout=2.0)
    assert time.monotonic() - t0 < 1.0


def test_stop_signals_running_attempt():
    seen = threading.Event()

    def attempt(spec, settings, stats, stop):
        stats.state = SessionState.RUNNING
        stop.wait()
        seen.set()

    session = DecodeSession(SPEC, FAST, attempt=attempt)
    session.start()
    assert wait_for(lambda: session.stats.state is SessionState.RUNNING)
    assert session.stop()
    assert seen.is_set()


class _RecordingStop:
    def __init__(self, rounds):
        self.delays = []
        self._rounds = rounds

    def is_set(self):
        return len(self.delays) >= self._rounds

    def set(self):
        self._rounds = 0

    def wait(self, delay=None):
        self.delays.append(delay)
        return self.is_set()


def _recorded_delays(settings, clock, rounds=6):
    def attempt(spec, settings_, stats, stop):
        raise ConnectionError("down")

    session = DecodeSession(SPEC, settings, attempt=attempt, clock=clock)
    session._stop = _RecordingStop(rounds)
    session._run()
    return session._stop.delays


def test_backoff_grows_while_connections_are_short_lived():
    s = DecoderSettings(
        backoff_initial_s=1.0, backoff_max_s=8.0, stable_after_s=30.0
    )
    delays = _recorded_delays(s, clock=lambda: 0.0)
    nominal = [1, 2, 4, 8, 8, 8]
    assert all(0.8 * n <= d <= 1.2 * n for d, n in zip(delays, nominal))


def test_backoff_resets_after_a_stable_connection():
    s = DecoderSettings(
        backoff_initial_s=1.0, backoff_max_s=8.0, stable_after_s=30.0
    )
    ticks = iter(range(0, 10_000, 100))
    delays = _recorded_delays(s, clock=lambda: float(next(ticks)))
    assert all(0.8 <= d <= 1.2 for d in delays)


def test_default_stop_timeout_outlasts_a_blocked_connect():
    waited = []

    class FakeThread:
        def is_alive(self):
            return True

        def join(self, timeout):
            waited.append(timeout)

    settings = DecoderSettings(open_timeout_s=10, read_timeout_s=5)
    session = DecodeSession(SPEC, settings, attempt=lambda *a: None)
    session._thread = FakeThread()
    session.stop()
    assert waited == [settings.stop_timeout_s] and waited[0] > 10


def test_session_state_starts_as_starting():
    session = DecodeSession(SPEC, FAST, attempt=lambda *a: None)
    assert session.stats.state is SessionState.STARTING
    assert session.stop() is True


def test_snapshot_is_json_friendly():
    import json

    session = DecodeSession(SPEC, FAST, attempt=lambda *a: None)
    json.dumps(session.stats.snapshot())


@pytest.mark.parametrize("n", [1, 2])
def test_stop_is_idempotent(n):
    session = DecodeSession(SPEC, FAST, attempt=lambda s, c, st, stop: stop.wait())
    session.start()
    for _ in range(n):
        assert session.stop()
