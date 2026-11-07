"""Per-camera runtime state and telemetry counters."""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any

from .endpoints import StreamInfo


class SessionState(str, enum.Enum):
    """Lifecycle state of a decode session."""

    STARTING = "starting"
    CONNECTING = "connecting"
    RUNNING = "running"
    BACKOFF = "backoff"
    STOPPED = "stopped"


@dataclass
class SessionStats:
    """Mutable counters of one camera."""

    state: SessionState = SessionState.STARTING
    source: StreamInfo | None = None
    live_mode: str | None = None
    restarts: int = 0
    last_error: str | None = None
    packets_in: int = 0
    frames_decoded: int = 0
    decode_errors: int = 0
    live_packets_out: int = 0
    ai_frames_submitted: int = 0
    ai_frames_encoded: int = 0
    ai_frames_dropped: int = 0
    ai_restarts: int = 0
    awaiting_keyframe: bool = False
    connected_at: float | None = field(default=None, repr=False)
    last_packet_at: float | None = field(default=None, repr=False)

    def mark_connected(self, info: StreamInfo, live_mode: str) -> None:
        """Record a successful connection and transition to RUNNING."""
        self.source = info
        self.live_mode = live_mode
        self.connected_at = time.monotonic()
        self.last_packet_at = self.connected_at
        self.state = SessionState.RUNNING

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-friendly copy of the current state."""
        now = time.monotonic()
        src = self.source
        return {
            "state": self.state.value,
            "source": (
                {
                    "codec": src.codec,
                    "width": src.width,
                    "height": src.height,
                    "fps": round(src.fps, 2),
                }
                if src
                else None
            ),
            "live_mode": self.live_mode,
            "restarts": self.restarts,
            "last_error": self.last_error,
            "packets_in": self.packets_in,
            "frames_decoded": self.frames_decoded,
            "decode_errors": self.decode_errors,
            "live_packets_out": self.live_packets_out,
            "ai_frames_submitted": self.ai_frames_submitted,
            "ai_frames_encoded": self.ai_frames_encoded,
            "ai_frames_dropped": self.ai_frames_dropped,
            "ai_restarts": self.ai_restarts,
            "awaiting_keyframe": self.awaiting_keyframe,
            "uptime_s": (
                round(now - self.connected_at, 1)
                if self.connected_at is not None
                and self.state is SessionState.RUNNING
                else None
            ),
            "idle_s": (
                round(now - self.last_packet_at, 1)
                if self.last_packet_at is not None
                and self.state is SessionState.RUNNING
                else None
            ),
        }
