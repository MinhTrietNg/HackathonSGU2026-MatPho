"""Polygon Watch Area Masking for Edge AI Frame Preprocessing.

Excludes noise sources (gas stoves, fireplaces, car headlights) outside the user-drawn
watch_area polygon before passing frames to AI inference models.
"""

from __future__ import annotations

import cv2
import numpy as np


def apply_watch_area_mask(
    frame_bgr: np.ndarray,
    watch_area: list[list[float]] | list[tuple[float, float]] | None,
) -> np.ndarray:
    """Mask out pixels outside the normalized watch_area polygon.

    Parameters
    ----------
    frame_bgr : np.ndarray
        Input image in BGR format with shape (H, W, 3).
    watch_area : list of [x, y] coordinates in [0.0, 1.0] range
        Polygon vertices (e.g. [[0.1, 0.2], [0.8, 0.2], [0.8, 0.9], [0.1, 0.9]]).

    Returns
    -------
    np.ndarray
        Masked BGR frame where all regions outside the polygon are set to black (0, 0, 0).
    """
    if not watch_area or len(watch_area) < 3:
        return frame_bgr

    h, w = frame_bgr.shape[:2]

    # Convert normalized coordinates [0.0, 1.0] to integer pixel coordinates
    pixel_points = []
    for pt in watch_area:
        if len(pt) >= 2:
            x_px = int(np.clip(float(pt[0]) * w, 0, w - 1))
            y_px = int(np.clip(float(pt[1]) * h, 0, h - 1))
            pixel_points.append([x_px, y_px])

    if len(pixel_points) < 3:
        return frame_bgr

    pts = np.array(pixel_points, dtype=np.int32).reshape((-1, 1, 2))

    # Create single-channel binary mask
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [pts], 255)

    # Apply mask onto frame
    return cv2.bitwise_and(frame_bgr, frame_bgr, mask=mask)
