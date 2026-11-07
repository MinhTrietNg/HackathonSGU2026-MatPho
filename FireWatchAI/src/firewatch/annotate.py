"""Draw detections and a status banner on frames (used by `run` and alerts)."""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from .detector import Detection

log = logging.getLogger(__name__)


def write_jpeg(path: Path, image: np.ndarray, quality: int = 90) -> bool:
    """Save ``image`` as JPEG; safe with non-ASCII paths on Windows.

    ``cv2.imwrite`` silently fails on paths it cannot encode; encoding in
    memory and writing the bytes ourselves avoids that and lets the caller
    know when nothing was written.
    """
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        log.warning("không encode được JPEG cho %s", path)
        return False
    try:
        Path(path).write_bytes(buf.tobytes())
    except OSError as exc:
        log.warning("không ghi được %s: %s", path, exc)
        return False
    return True

# BGR. Lửa đỏ, khói xám-cam; class khác (weights COCO) xanh lá.
CLASS_COLORS = {"fire": (0, 0, 255), "smoke": (0, 165, 255)}
DEFAULT_COLOR = (80, 200, 80)


def draw_detections(image: np.ndarray, detections: list[Detection],
                    banner: str | None = None) -> np.ndarray:
    """Return a copy of ``image`` with boxes, labels and an optional banner.

    Parameters
    ----------
    image : ndarray
        BGR frame; it is not modified.
    detections : list of Detection
        Boxes in pixel coordinates.
    banner : str, optional
        Text drawn in the top-left corner (timestamp, state ...).
    """
    out = image.copy()
    h, w = out.shape[:2]
    thick = max(1, round(min(h, w) / 360))
    scale = max(0.45, min(h, w) / 900)
    for d in detections:
        color = CLASS_COLORS.get(d.cls_name, DEFAULT_COLOR)
        x1, y1, x2, y2 = (int(round(v)) for v in d.xyxy)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, thick)
        label = f"{d.cls_name} {d.conf:.2f}"
        (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
        ty = y1 - 4 if y1 - th - 6 > 0 else y2 + th + 4
        cv2.rectangle(out, (x1, ty - th - 4), (x1 + tw + 4, ty + base), color, -1)
        cv2.putText(out, label, (x1 + 2, ty), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (255, 255, 255), thick, cv2.LINE_AA)
    if banner:
        (tw, th), base = cv2.getTextSize(banner, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
        cv2.rectangle(out, (0, 0), (tw + 12, th + base + 10), (0, 0, 0), -1)
        cv2.putText(out, banner, (6, th + 5), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (255, 255, 255), thick, cv2.LINE_AA)
    return out


STATE_COLORS = {"CANDIDATE": (0, 255, 255), "CONFIRMED": (0, 0, 255),
                "COOLDOWN": (160, 160, 160)}


def draw_tracks(image: np.ndarray, tracks, window_m: int, k_enter: int) -> np.ndarray:
    """Overlay voting tracks: dashed-looking thin box + ``state votes/k`` label.

    Parameters
    ----------
    tracks : iterable of firewatch.voting.Track
        Current tracks of the voting engine (modified in place on a copy).
    """
    out = image.copy()
    h, w = out.shape[:2]
    thick = max(1, round(min(h, w) / 360))
    scale = max(0.45, min(h, w) / 900)
    for t in tracks:
        color = STATE_COLORS.get(t.state.value, (255, 255, 255))
        x1, y1, x2, y2 = (int(round(v)) for v in t.box)
        width = thick * 3 if t.state.value == "CONFIRMED" else thick
        cv2.rectangle(out, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), color, width)
        label = f"#{t.track_id} {t.state.value} {t.votes}/{k_enter} (M={window_m})"
        if t.state.value != "CANDIDATE":
            label += f" {t.severity.value}"
        (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
        ty = min(h - 2, y2 + th + 8)
        cv2.rectangle(out, (x1 - 3, ty - th - 4), (x1 + tw + 1, ty + base), color, -1)
        cv2.putText(out, label, (x1 - 1, ty), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (0, 0, 0), thick, cv2.LINE_AA)
    return out
