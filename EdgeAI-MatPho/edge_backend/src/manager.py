"""Registry of running camera decode/remux sessions."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from .config import DecoderSettings, StreamSpec
from .session import DecodeSession

logger = logging.getLogger("edge.manager")

SessionFactory = Callable[[StreamSpec, DecoderSettings], DecodeSession]


class StreamAlreadyRunning(RuntimeError):
    """A session for this camera already exists."""


class DecodeManager:
    """Start, stop and inspect decode sessions, one per camera."""

    def __init__(
        self,
        settings: DecoderSettings,
        session_factory: SessionFactory = DecodeSession,
    ) -> None:
        self.settings = settings
        self._factory = session_factory
        self._sessions: dict[str, DecodeSession] = {}
        self._lock = threading.Lock()

    def is_running(self, cam_id: str) -> bool:
        """Return True if session exists and is alive."""
        with self._lock:
            session = self._sessions.get(cam_id)
            return session is not None and session.alive

    def start(self, cam_id: str, source_url: str | None = None) -> StreamSpec:
        """Begin decoding/remuxing a camera."""
        spec = StreamSpec.for_camera(cam_id, self.settings, source_url)
        with self._lock:
            existing = self._sessions.get(cam_id)
            if existing is not None and existing.alive:
                raise StreamAlreadyRunning(cam_id)
            session = self._factory(spec, self.settings)
            self._sessions[cam_id] = session

        session.start()
        logger.info("[cam_id=%s] session started for %s", cam_id, spec.source_url)
        return spec

    def stop(self, cam_id: str) -> bool:
        """Stop one camera session; return False if unknown or did not stop."""
        with self._lock:
            session = self._sessions.pop(cam_id, None)
        if session is None:
            return False
        return session.stop()

    def stop_all(self) -> None:
        """Stop every session gracefully."""
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.request_stop()
        for session in sessions:
            if not session.stop():
                logger.warning(
                    "[cam_id=%s] did not stop in time", session.spec.cam_id
                )

    def status(self) -> dict[str, dict[str, Any]]:
        """Return a snapshot of every running session, keyed by cam_id."""
        with self._lock:
            items = list(self._sessions.items())
        return {cam: s.stats.snapshot() for cam, s in items}
