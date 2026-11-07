"""Supervision of one camera: run, detect failure, reconnect with exponential backoff."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import av

from .backoff import ExponentialBackoff
from .config import DecoderSettings, StreamSpec, redact_text, redact_url
from .pipeline import run_attempt
from .stats import SessionState, SessionStats

logger = logging.getLogger("edge.session")

EXPECTED_ERRORS = (av.FFmpegError, OSError, ValueError, RuntimeError, TimeoutError)

Attempt = Callable[[StreamSpec, DecoderSettings, SessionStats, threading.Event], None]


class DecodeSession:
    """Keep one camera decoded/remuxed for as long as it is not stopped."""

    def __init__(
        self,
        spec: StreamSpec,
        settings: DecoderSettings,
        attempt: Attempt = run_attempt,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.spec = spec
        self.settings = settings
        self.stats = SessionStats()
        self._attempt = attempt
        self._clock = clock
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name=f"decode-{spec.cam_id}", daemon=True
        )
        self._backoff = ExponentialBackoff(
            settings.backoff_initial_s, settings.backoff_max_s
        )

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    def start(self) -> None:
        self._thread.start()

    def request_stop(self) -> None:
        self._stop.set()

    def stop(self, timeout: float | None = None) -> bool:
        self.request_stop()
        if timeout is None:
            timeout = self.settings.stop_timeout_s
        if self._thread.is_alive():
            self._thread.join(timeout)
        return not self._thread.is_alive()

    def _describe(self, exc: BaseException) -> str:
        text = str(exc).strip()
        if not text:
            return exc.__class__.__name__
        return redact_text(f"{exc.__class__.__name__}: {text}")

    def _run(self) -> None:
        cam_id = self.spec.cam_id
        safe_url = redact_url(self.spec.source_url)
        while not self._stop.is_set():
            t0 = self._clock()
            self.stats.state = SessionState.CONNECTING
            logger.info("[cam_id=%s] connecting to %s", cam_id, safe_url)
            try:
                self._attempt(self.spec, self.settings, self.stats, self._stop)
                reason = "end of stream"
            except BaseException as exc:
                reason = self._describe(exc)
                if isinstance(exc, EXPECTED_ERRORS):
                    logger.warning("[cam_id=%s] disconnected: %s", cam_id, reason)
                else:
                    logger.exception(
                        "[cam_id=%s] unexpected crash in decode attempt: %s",
                        cam_id,
                        reason,
                    )
            if self._stop.is_set():
                break

            up_for = self._clock() - t0
            if up_for >= self.settings.stable_after_s:
                self._backoff.reset()
            self.stats.restarts += 1
            self.stats.last_error = reason
            self.stats.state = SessionState.BACKOFF

            delay = self._backoff.next_delay()
            logger.info(
                "[cam_id=%s] reconnecting in %.1fs (attempt #%d)",
                cam_id,
                delay,
                self.stats.restarts,
            )
            if self._stop.wait(delay):
                break

        self.stats.state = SessionState.STOPPED
        logger.info("[cam_id=%s] session finished", cam_id)
