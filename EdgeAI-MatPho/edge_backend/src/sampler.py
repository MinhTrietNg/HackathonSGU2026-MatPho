"""Frame-rate decimation driven by presentation timestamps."""

from __future__ import annotations


class FrameRateSampler:
    """Pick frames so the output approximates a fixed, lower frame rate."""

    def __init__(self, target_fps: float) -> None:
        if target_fps <= 0:
            raise ValueError("target_fps must be positive")
        self._period = 1.0 / target_fps
        self._next_t: float | None = None
        self._last_t: float | None = None

    def reset(self) -> None:
        """Forget the time grid; next frame is accepted unconditionally."""
        self._next_t = None
        self._last_t = None

    def accept(self, t: float) -> bool:
        """Decide whether the frame at stream time t (seconds) is kept."""
        if self._next_t is None or self._last_t is None or t < self._last_t:
            self._anchor(t)
            return True
        self._last_t = t
        if t < self._next_t:
            return False
        if t - self._next_t >= self._period:
            self._next_t = t + self._period
        else:
            self._next_t += self._period
        return True

    def _anchor(self, t: float) -> None:
        self._last_t = t
        self._next_t = t + self._period
