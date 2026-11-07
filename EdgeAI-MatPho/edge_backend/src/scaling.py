"""Geometry helpers for video scaling."""

from __future__ import annotations


def fit_even(width: int, height: int, max_edge: int) -> tuple[int, int]:
    """Scale (width, height) so the longest side is at most max_edge, rounded to even numbers."""
    if width <= 0 or height <= 0 or max_edge <= 0:
        raise ValueError("width, height and max_edge must be positive")
    scale = min(1.0, max_edge / max(width, height))
    out_w = max(2, int(width * scale) // 2 * 2)
    out_h = max(2, int(height * scale) // 2 * 2)
    return out_w, out_h
