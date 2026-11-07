"""Black-and-white copies of colour frames, approximating a night / IR camera.

Many parking cameras switch to an infrared mode at night and send grayscale
video. A colour-trained detector leans on the orange of flames; a grayscale
copy of every training image forces it to also use shape and texture.

Real IR footage (clips ``dem_ir`` of the catalog, measured 04/11/2026) differs
from a plain grayscale conversion in ways that matter for fire:

* flames and other very hot / very bright sources **saturate to white** and
  bloom into a halo, while plain luma turns orange flames into mid-gray;
* red / orange surfaces reflect near-infrared strongly, so they look brighter
  than their visible luma;
* the IR illuminator lights the scene evenly enough that frames sit in a
  narrow brightness band (mean ≈ 60–100), brighter at the centre;
* frames are soft (cheap optics, heavy compression) with fine grain.

``mode="ir"`` reproduces these four effects; parameters are drawn from a
generator seeded by a stable key (file stem or clip name), so a rebuild gives
byte-identical images and every frame of one clip shares the same "camera".
It is still a colour frame turned gray, not a sensor model: thermal
contrast of hidden hot parts (a battery heating inside a scooter) cannot be
recovered from a visible-light photo.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

Mode = Literal["ir", "gray"]
Box = tuple[int, float, float, float, float]


@dataclass(frozen=True)
class IRParams:
    """One simulated IR camera setting.

    Attributes
    ----------
    target_mean : float
        Mean gray level the frame is exposed to (IR illuminator).
    contrast : float
        Gain around the target mean.
    red_gain : float
        How much brighter red / orange surfaces look than their luma (NIR).
    vignette : float
        Darkening at the corners relative to the centre, 0 = none.
    bloom : float
        Strength of the halo around saturated hot areas.
    blur_sigma : float
        Gaussian softness in pixels (at 640 px width; scaled with size).
    noise_sigma : float
        Standard deviation of the sensor grain, in gray levels.
    """

    target_mean: float
    contrast: float
    red_gain: float
    vignette: float
    bloom: float
    blur_sigma: float
    noise_sigma: float


def seed_of(key: str) -> int:
    """Stable 64-bit seed of a text key (same on every machine and run)."""
    return int(hashlib.md5(key.encode("utf-8")).hexdigest()[:16], 16)


def draw_params(rng: np.random.Generator) -> IRParams:
    """Draw one IR camera setting within the range measured on real footage.

    Parameters
    ----------
    rng : numpy.random.Generator
        Source of randomness.

    Returns
    -------
    IRParams
        target mean 60–105, contrast 0.9–1.3, red gain 0.75–0.95, vignette
        0.15–0.4, bloom 0.3–0.7, blur sigma 0.5–1.2, grain sigma 1–4.
    """
    return IRParams(target_mean=float(rng.uniform(60, 105)),
                    contrast=float(rng.uniform(0.9, 1.3)),
                    red_gain=float(rng.uniform(0.75, 0.95)),
                    vignette=float(rng.uniform(0.15, 0.4)),
                    bloom=float(rng.uniform(0.3, 0.7)),
                    blur_sigma=float(rng.uniform(0.5, 1.2)),
                    noise_sigma=float(rng.uniform(1.0, 4.0)))


def to_gray3(img: np.ndarray) -> np.ndarray:
    """BGR (or already gray) image as a 3-channel grayscale image."""
    gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


SMALL_HOT = 0.002
"""Hot blobs up to this fraction of the frame may sit anywhere (lamps and
headlights also clip to white in real IR footage)."""
FREE_HOT = 0.10
"""Without boxes (test video), the largest hot blob kept (fraction of the
frame): a flame filling a tenth of the view still clips, a sunset sky or a
straw field does not."""


def _flame_pixels(img: np.ndarray) -> np.ndarray:
    """Soft 0–1 map of flame-coloured pixels: bright and red / orange / yellow.

    Hue 0–45° (or above 345°), saturation ≥ 0.35 and value ≥ 0.70 ramp up
    to 1; near-white pixels (value ≥ 0.96) count as well, since flame cores
    are often already clipped to white in colour video.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, s, v = hsv[..., 0] * 2.0, hsv[..., 1] / 255.0, hsv[..., 2] / 255.0
    warm = ((h <= 45) | (h >= 345)).astype(np.float32)
    ramp = np.clip((v - 0.70) / 0.2, 0, 1) * np.clip((s - 0.35) / 0.2, 0, 1)
    return np.maximum(warm * ramp, np.clip((v - 0.96) / 0.04, 0, 1))


def _box_mask(shape: tuple[int, int], boxes: Sequence[Box], grow: float,
              fire_cls: int = 0) -> np.ndarray:
    """Boolean mask of the fire boxes, each grown by ``grow`` of its size."""
    h, w = shape
    mask = np.zeros((h, w), bool)
    for c, bx, by, bw, bh in boxes:
        if c != fire_cls:
            continue
        gw, gh = bw * (1 + 2 * grow), bh * (1 + 2 * grow)
        x0, x1 = int(max(0, (bx - gw / 2) * w)), int(min(w, np.ceil((bx + gw / 2) * w)))
        y0, y1 = int(max(0, (by - gh / 2) * h)), int(min(h, np.ceil((by + gh / 2) * h)))
        mask[y0:y1, x0:x1] = True
    return mask


def hot_mask(img: np.ndarray, boxes: Sequence[Box] | None = None) -> np.ndarray:
    """Soft 0–1 map of the pixels that saturate in the simulated IR frame.

    Colour alone is not enough: sunset sky, straw, sand, skin and smoke lit
    by the fire are also bright and warm, and turning them all white made
    ~9.5 % of the fire boxes sit inside a flat white patch (measured on 1.500
    copies, 04/11/2026). Flame-coloured pixels are grouped into connected
    blobs; small blobs (``SMALL_HOT``, lamps) may clip anywhere, and other
    pixels only inside a fire box grown by 25 % — smoke lit orange by the
    fire is often one blob with the flame and must stay gray. Without boxes
    (test video, ``None``) a blob is kept up to ``FREE_HOT`` of the frame; an
    empty box list means a labelled negative image, where only small blobs
    may clip.

    Parameters
    ----------
    img : numpy.ndarray
        BGR uint8 image.
    boxes : sequence of tuple, optional
        YOLO boxes ``(cls, cx, cy, w, h)``; only class 0 (fire) counts.
    """
    soft = _flame_pixels(img)
    v = img.max(axis=2) if img.ndim == 3 else img
    h, w = soft.shape
    n, lab, stats, _ = cv2.connectedComponentsWithStats(
        (soft > 0.05).astype(np.uint8), connectivity=8)
    if n <= 1:
        return soft * 0
    area = stats[1:, cv2.CC_STAT_AREA] / float(h * w)
    keep = area <= (SMALL_HOT if boxes is not None else FREE_HOT)
    mask = np.concatenate([[False], keep])[lab].astype(np.float32)
    if boxes is not None:
        # Trong box chỉ phần sáng nhất là lõi lửa; nền được lửa chiếu cam đều cả box
        # không được thành khối trắng vuông. Mép làm mềm cho cùng lý do.
        core = np.zeros((h, w), np.float32)
        for b in boxes:
            region = _box_mask((h, w), [b], 0.25)
            if region.any():
                core[region & (v >= np.quantile(v[region], 0.6))] = 1.0
        k = int(max(h, w) * 0.03) | 1
        mask = np.maximum(mask, cv2.GaussianBlur(core, (k, k), 0))
    return soft * mask


def bright_outside(gray: np.ndarray, boxes: Sequence[Box],
                   level: int = 245) -> float:
    """Share of the pixels outside every box that are clipped near white.

    A simulated IR frame with large white areas away from the labelled
    objects is not what an IR camera shows at night; the dataset builder
    drops such copies.
    """
    g = gray if gray.ndim == 2 else cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    inside = _box_mask(g.shape, [(0, *b[1:]) for b in boxes], 0.0)
    out = g[~inside]
    return float((out >= level).mean()) if out.size else 0.0


def apply_ir(img: np.ndarray, params: IRParams, rng: np.random.Generator,
             boxes: Sequence[Box] | None = None) -> np.ndarray:
    """Apply one IR camera setting to a BGR image.

    Parameters
    ----------
    img : numpy.ndarray
        BGR uint8 image (a 2-D gray input skips the colour-dependent steps).
    params : IRParams
        Camera setting from :func:`draw_params`.
    rng : numpy.random.Generator
        Randomness for the per-frame grain.
    boxes : sequence of tuple, optional
        Labelled boxes; when given, only flames at fire boxes saturate
        (:func:`hot_mask`).

    Returns
    -------
    numpy.ndarray
        3-channel uint8 image whose three channels are equal.
    """
    if img.ndim == 2:
        base = img.astype(np.float32) / 255.0
        heat = np.clip((base - 0.96) / 0.04, 0, 1)
    else:
        f = img.astype(np.float32) / 255.0
        luma = 0.114 * f[..., 0] + 0.587 * f[..., 1] + 0.299 * f[..., 2]
        base = np.maximum(luma, params.red_gain * f[..., 2])   # đỏ/cam sáng (NIR)
        heat = hot_mask(img, boxes)
    h, w = base.shape
    mean = float(base.mean())
    gamma = float(np.clip(np.log(params.target_mean / 255.0)
                          / np.log(min(max(mean, 1e-3), 0.999)), 0.3, 2.5))
    g = base ** gamma * 255.0
    g = (g - params.target_mean) * params.contrast + params.target_mean
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r2 = ((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2
    g *= 1.0 - params.vignette * np.clip(r2 / 2.0, 0, 1)        # đèn IR sáng ở tâm
    g = g * (1 - heat) + 255.0 * heat                           # lửa bão hoà trắng
    k = int(max(h, w) * 0.04) | 1
    g += cv2.GaussianBlur(heat, (k, k), 0) * 255.0 * params.bloom
    g = cv2.GaussianBlur(g, (0, 0), params.blur_sigma * max(w, 1) / 640.0)
    if params.noise_sigma > 0:
        g = g + rng.normal(0.0, params.noise_sigma, g.shape).astype(np.float32)
    out = np.clip(g, 0, 255).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


def bw_copy(img: np.ndarray, key: str, mode: Mode = "ir",
            boxes: Sequence[Box] | None = None) -> np.ndarray:
    """Black-and-white copy of one still image, deterministic in ``key``.

    Parameters
    ----------
    img : numpy.ndarray
        BGR uint8 image.
    key : str
        Stable identifier (e.g. the file stem) used to seed the camera.
    mode : {"ir", "gray"}
        ``gray`` is plain grayscale; ``ir`` is :func:`apply_ir`.
    boxes : sequence of tuple, optional
        YOLO boxes of a labelled image (see :func:`hot_mask`).

    Returns
    -------
    numpy.ndarray
        3-channel grayscale uint8 image, same size as ``img``.
    """
    if mode == "gray":
        return to_gray3(img)
    rng = np.random.default_rng(seed_of(key))
    return apply_ir(img, draw_params(rng), rng, boxes)


def weak_fire_boxes(gray: np.ndarray,
                    boxes: Sequence[tuple[int, float, float, float, float]],
                    fire_cls: int = 0) -> int:
    """How many fire boxes carry almost no signal in a grayscale copy.

    Rule from the 04/11/2026 check of the IR copies (confirmed by eye on 10
    of 12 flagged images): a fire box is *weak* when its 95th-percentile gray
    level is below 230 **and** not above that of the ring around it (box
    grown by half its size on each side) **and** its mean is not above the
    ring's mean — the flame is neither bright nor brighter than its
    surroundings, so the box would teach the model to fire on gray smoke.
    """
    g = gray if gray.ndim == 2 else cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    weak = 0
    for c, bx, by, bw, bh in boxes:
        if c != fire_cls:
            continue
        x0, x1 = int(max(0, (bx - bw / 2) * w)), int(min(w, (bx + bw / 2) * w))
        y0, y1 = int(max(0, (by - bh / 2) * h)), int(min(h, (by + bh / 2) * h))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        inner = g[y0:y1, x0:x1].astype(np.float32)
        rx0, rx1 = int(max(0, x0 - (x1 - x0) / 2)), int(min(w, x1 + (x1 - x0) / 2))
        ry0, ry1 = int(max(0, y0 - (y1 - y0) / 2)), int(min(h, y1 + (y1 - y0) / 2))
        ring = g[ry0:ry1, rx0:rx1].astype(np.float32).copy()
        ring[y0 - ry0:y1 - ry0, x0 - rx0:x1 - rx0] = np.nan
        ring = ring[~np.isnan(ring)]
        if ring.size == 0:
            continue
        p_in, p_ring = np.percentile(inner, 95), np.percentile(ring, 95)
        if p_in < 230 and p_in <= p_ring and inner.mean() <= ring.mean():
            weak += 1
    return weak
