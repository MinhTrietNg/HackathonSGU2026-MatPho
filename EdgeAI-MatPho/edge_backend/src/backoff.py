"""Exponential reconnect backoff with jitter."""

from __future__ import annotations

import random
from typing import Callable


class ExponentialBackoff:
    """Produce growing, jittered delays between reconnect attempts."""

    def __init__(
        self,
        initial: float,
        maximum: float,
        factor: float = 2.0,
        jitter: float = 0.2,
        rng: Callable[[], float] = random.random,
    ) -> None:
        if not 0 < initial <= maximum:
            raise ValueError("require 0 < initial <= maximum")
        if factor < 1 or not 0 <= jitter < 1:
            raise ValueError("require factor >= 1 and 0 <= jitter < 1")
        self._initial = initial
        self._maximum = maximum
        self._factor = factor
        self._jitter = jitter
        self._rng = rng
        self._nominal = initial

    def next_delay(self) -> float:
        """Return the delay to wait now and advance the schedule."""
        nominal = self._nominal
        self._nominal = min(self._maximum, nominal * self._factor)
        spread = 1.0 + self._jitter * (2.0 * self._rng() - 1.0)
        return nominal * spread

    def reset(self) -> None:
        """Restart from the initial delay (call after a stable connection)."""
        self._nominal = self._initial
