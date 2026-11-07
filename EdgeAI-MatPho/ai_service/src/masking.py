"""
Watch Area Masking & Bounding Box Overlap Filter for FireWatch AI Service
Supports BOTH `watch_area` formats (Q2):
1. Rectangle Dict (from App I5 / Cloud Backend):
   `{"left": 0.1, "top": 0.2, "width": 0.5, "height": 0.4}` (normalized [0.0, 1.0])
2. Polygon List (from Edge Spec):
   `[[x1, y1], [x2, y2], [x3, y3], ...]` (normalized [0.0, 1.0])
"""

import cv2
import numpy as np
from typing import List, Dict, Optional, Union

WatchAreaInput = Union[Dict[str, float], List[List[float]]]


def normalize_watch_area_to_polygon(
    watch_area: Optional[WatchAreaInput],
) -> Optional[List[List[float]]]:
    """
    Convert either a Rectangle dict `{"left", "top", "width", "height"}`
    or a Polygon list `[[x, y], ...]` into a normalized 4+ vertex polygon list.
    Returns None if `watch_area` is empty or invalid.
    """
    if not watch_area:
        return None

    if isinstance(watch_area, dict):
        try:
            left = float(watch_area.get("left", 0.0))
            top = float(watch_area.get("top", 0.0))
            width = float(watch_area.get("width", 0.0))
            height = float(watch_area.get("height", 0.0))
        except (TypeError, ValueError):
            return None
        if width <= 0.0 or height <= 0.0:
            return None
        x1 = max(0.0, min(1.0, left))
        y1 = max(0.0, min(1.0, top))
        x2 = max(0.0, min(1.0, left + width))
        y2 = max(0.0, min(1.0, top + height))
        if x2 <= x1 or y2 <= y1:
            return None
        return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

    if isinstance(watch_area, list) and len(watch_area) >= 3:
        pts: List[List[float]] = []
        for pt in watch_area:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                continue
            pts.append([float(pt[0]), float(pt[1])])
        if len(pts) >= 3:
            return pts

    return None


def apply_watch_area_mask(
    frame: np.ndarray,
    watch_area: Optional[WatchAreaInput],
) -> np.ndarray:
    """
    Black-out all pixels OUTSIDE the `watch_area` before passing the frame to the AI model.
    Accepts either Rectangle dict `{"left", "top", "width", "height"}` or Polygon list `[[x, y], ...]`.
    """
    polygon_norm = normalize_watch_area_to_polygon(watch_area)
    if not polygon_norm:
        return frame

    h, w = frame.shape[:2]
    pts = []
    for pt in polygon_norm:
        px = int(max(0.0, min(1.0, float(pt[0]))) * w)
        py = int(max(0.0, min(1.0, float(pt[1]))) * h)
        pts.append([px, py])

    if len(pts) < 3:
        return frame

    poly_np = np.array([pts], dtype=np.int32)
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, poly_np, 255)
    masked_frame = cv2.bitwise_and(frame, frame, mask=mask)
    return masked_frame


apply_polygon_mask = apply_watch_area_mask


def is_bbox_in_watch_area(
    bbox: List[float],
    watch_area: Optional[WatchAreaInput],
    frame_width: int = 1,
    frame_height: int = 1,
    min_overlap_ratio: float = 0.10,
) -> bool:
    """
    Post-inference helper: Check if a detected Bounding Box `[x1, y1, x2, y2]`
    overlaps with `watch_area` by at least `min_overlap_ratio` (default 10%).
    """
    polygon_norm = normalize_watch_area_to_polygon(watch_area)
    if not polygon_norm:
        return True
    if len(bbox) < 4 or frame_width <= 0 or frame_height <= 0:
        return False

    bx1, by1, bx2, by2 = [float(v) for v in bbox[:4]]
    box_w = max(0.0, bx2 - bx1)
    box_h = max(0.0, by2 - by1)
    box_area = box_w * box_h
    if box_area <= 0.0:
        return False

    xs = [pt[0] * frame_width for pt in polygon_norm]
    ys = [pt[1] * frame_height for pt in polygon_norm]
    wx1, wx2 = min(xs), max(xs)
    wy1, wy2 = min(ys), max(ys)

    ix1 = max(bx1, wx1)
    iy1 = max(by1, wy1)
    ix2 = min(bx2, wx2)
    iy2 = min(by2, wy2)

    inter_area = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    return (inter_area / box_area) >= min_overlap_ratio
