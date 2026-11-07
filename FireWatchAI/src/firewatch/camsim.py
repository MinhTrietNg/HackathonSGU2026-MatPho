"""Camera-processing variants: the same scene as different CCTV pipelines see it.

A parking camera rarely delivers the clean frames of public datasets. Each
training image gets one copy passed through one of these effects (seeded by
the image name, so rebuilds are byte-identical):

``dem_mau``   night colour mode: dark, gamma-crushed, strong luma/chroma noise
``nen_thap``  low-bitrate recorder: downscale, heavy JPEG, upscale (blocking)
``loa_sang``  over-exposure / auto-exposure hunting, bloom around bright areas
``ong_kinh``  wide-angle lens: barrel distortion + vignetting (boxes remapped)
``mo``        motion blur or defocus
``osd``       timestamp and camera name burnt into a corner (can also be added
              on top of another effect)

Deliberately left out: fog, haze, rain streaks and smoke-like overlays — they
look like smoke and would teach the model the wrong class. The grayscale
infrared look is ``firewatch.irsim`` (a separate copy of every image).
Boxes are YOLO-normalised ``(cls, cx, cy, w, h)``; only ``ong_kinh`` moves
them, every other effect keeps geometry.
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from firewatch.irsim import seed_of

Box = tuple[int, float, float, float, float]
EFFECTS = ("dem_mau", "nen_thap", "loa_sang", "ong_kinh", "mo")
MIN_SIDE = 0.005                       # quy ước §4: box < 0,5 % cạnh ảnh bị bỏ


def _dem_mau(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    f = img.astype(np.float32) / 255.0
    f = f ** rng.uniform(1.5, 2.3) * rng.uniform(0.45, 0.75)
    luma = rng.normal(0, rng.uniform(5, 12) / 255.0, f.shape[:2])[..., None]
    chroma = rng.normal(0, rng.uniform(2, 6) / 255.0, f.shape)
    f = cv2.GaussianBlur(f + luma + chroma, (3, 3), 0)
    return np.clip(f * 255.0, 0, 255).astype(np.uint8)


def _nen_thap(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    h, w = img.shape[:2]
    s = rng.uniform(0.3, 0.55)
    small = cv2.resize(img, (max(16, int(w * s)), max(16, int(h * s))),
                       interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", small,
                           [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(12, 31))])
    small = cv2.imdecode(buf, cv2.IMREAD_COLOR) if ok else small
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def _loa_sang(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    f = img.astype(np.float32) / 255.0
    # Tăng sáng theo độ sáng sẵn có: ảnh đã sáng chỉ tăng nhẹ, không trắng xoá.
    mean = float(f.mean())
    gain = min(rng.uniform(1.2, 1.6), max(1.05, 0.62 / max(mean, 1e-3)))
    f = np.clip(f * gain, 0, 1) ** rng.uniform(0.8, 0.95)
    lum = f.max(axis=2, keepdims=True)
    thr = max(0.85, float(np.quantile(lum, 0.98)))       # chỉ 2 % sáng nhất toả quầng
    bright = (lum >= thr).astype(np.float32) * f
    k = int(max(img.shape[:2]) * rng.uniform(0.02, 0.04)) | 1
    halo = cv2.GaussianBlur(bright, (k, k), 0)
    halo = halo if halo.ndim == 3 else halo[..., None]
    f = f + halo * rng.uniform(0.3, 0.6)
    return np.clip(f * 255.0, 0, 255).astype(np.uint8)


def boxes_still_visible(before: np.ndarray, after: np.ndarray,
                        boxes: Sequence[Box], min_keep: float = 0.35,
                        min_std: float = 6.0) -> bool:
    """True when every box region keeps enough gray-level contrast.

    A flame washed out to flat white (or crushed to black) would leave a box
    on nothing; such a copy must not be used. Contrast is the standard
    deviation of the gray values inside the box.
    """
    if not boxes:
        return True
    h, w = before.shape[:2]
    gb = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY).astype(np.float32)
    ga = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY).astype(np.float32)
    for _, bx, by, bw, bh in boxes:
        # Lõi 80 % của box: viền box thường là nền, không phải vật.
        x0, x1 = int(max(0, (bx - bw * 0.4) * w)), int(min(w, (bx + bw * 0.4) * w))
        y0, y1 = int(max(0, (by - bh * 0.4) * h)), int(min(h, (by + bh * 0.4) * h))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        sb, sa = float(gb[y0:y1, x0:x1].std()), float(ga[y0:y1, x0:x1].std())
        if sa < min_std or sa < min_keep * sb:
            return False
    return True


def _mo(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    if rng.random() < 0.5:                                   # mờ chuyển động
        n = int(rng.integers(5, 14))
        kern = np.zeros((n, n), np.float32)
        kern[n // 2, :] = 1.0 / n
        rot = cv2.getRotationMatrix2D((n / 2 - 0.5, n / 2 - 0.5),
                                      float(rng.uniform(0, 180)), 1.0)
        kern = cv2.warpAffine(kern, rot, (n, n))
        kern /= max(kern.sum(), 1e-6)
        return cv2.filter2D(img, -1, kern)
    return cv2.GaussianBlur(img, (0, 0), float(rng.uniform(1.2, 2.5)))  # lệch nét


def lens_maps(w: int, h: int, k: float) -> tuple[np.ndarray, np.ndarray, float]:
    """Remap grids for barrel distortion ``k`` (> 0), zoomed to fill the frame.

    Output pixel at normalised radius ``r`` (half-diagonal = 1) samples the
    source at ``s * r * (1 + k r²)`` with ``s = 1 / (1 + k)``, so the corners
    stay corners, the centre is magnified and the edges are compressed.
    """
    cx, cy, half = (w - 1) / 2, (h - 1) / 2, np.hypot(w, h) / 2
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32),
                         np.arange(h, dtype=np.float32))
    nx, ny = (xs - cx) / half, (ys - cy) / half
    s = 1.0 / (1.0 + k)
    f = s * (1 + k * (nx * nx + ny * ny))
    return (nx * f * half + cx).astype(np.float32), (ny * f * half + cy).astype(
        np.float32), s


def lens_points(px: np.ndarray, py: np.ndarray, w: int, h: int,
                k: float) -> tuple[np.ndarray, np.ndarray]:
    """Where source pixels land in the distorted image (inverse of the maps).

    Solves ``r_src = s * r_out * (1 + k r_out²)`` for ``r_out`` by bisection;
    the right side is increasing in ``r_out``, so the root is unique.
    """
    cx, cy, half = (w - 1) / 2, (h - 1) / 2, np.hypot(w, h) / 2
    nx, ny = (px - cx) / half, (py - cy) / half
    r_src = np.hypot(nx, ny)
    s = 1.0 / (1.0 + k)
    lo, hi = np.zeros_like(r_src), np.full_like(r_src, 4.0)
    for _ in range(50):
        mid = (lo + hi) / 2
        up = s * mid * (1 + k * mid * mid) < r_src
        lo, hi = np.where(up, mid, lo), np.where(up, hi, mid)
    r_out = (lo + hi) / 2
    scale = np.where(r_src > 1e-9, r_out / np.maximum(r_src, 1e-9), 1.0 / s)
    return nx * scale * half + cx, ny * scale * half + cy


def lens_boxes(boxes: Sequence[Box], w: int, h: int, k: float) -> list[Box]:
    """Boxes after :func:`lens_maps`: bounding box of 9 points per edge."""
    out: list[Box] = []
    t = np.linspace(0.0, 1.0, 9)
    for c, bx, by, bw, bh in boxes:
        x0, x1 = (bx - bw / 2) * w, (bx + bw / 2) * w
        y0, y1 = (by - bh / 2) * h, (by + bh / 2) * h
        px = np.concatenate([x0 + (x1 - x0) * t, x0 + (x1 - x0) * t,
                             np.full(9, x0), np.full(9, x1)])
        py = np.concatenate([np.full(9, y0), np.full(9, y1),
                             y0 + (y1 - y0) * t, y0 + (y1 - y0) * t])
        qx, qy = lens_points(px, py, w, h, k)
        ax0, ax1 = np.clip([qx.min(), qx.max()], 0, w)
        ay0, ay1 = np.clip([qy.min(), qy.max()], 0, h)
        nw, nh = (ax1 - ax0) / w, (ay1 - ay0) / h
        if nw < MIN_SIDE or nh < MIN_SIDE:
            continue
        out.append((c, float((ax0 + ax1) / 2 / w), float((ay0 + ay1) / 2 / h),
                    float(nw), float(nh)))
    return out


def _ong_kinh(img: np.ndarray, rng: np.random.Generator, boxes: Sequence[Box]
              ) -> tuple[np.ndarray, list[Box]]:
    h, w = img.shape[:2]
    k = float(rng.uniform(0.12, 0.30))
    mx, my, _ = lens_maps(w, h, k)
    out = cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) / np.sqrt(2)
    vig = 1.0 - rng.uniform(0.25, 0.5) * r ** 2
    out = np.clip(out.astype(np.float32) * vig[..., None], 0, 255).astype(np.uint8)
    return out, lens_boxes(boxes, w, h, k)


def draw_osd(img: np.ndarray, rng: np.random.Generator,
             boxes: Sequence[Box]) -> np.ndarray:
    """Timestamp + camera name in the corner that overlaps the boxes least."""
    h, w = img.shape[:2]
    stamp = (f"20{rng.integers(19, 27)}-{rng.integers(1, 13):02d}-"
             f"{rng.integers(1, 29):02d} {rng.integers(0, 24):02d}:"
             f"{rng.integers(0, 60):02d}:{rng.integers(0, 60):02d}")
    name = f"CAM {rng.integers(1, 17):02d}"
    scale = max(0.4, h / 700.0)
    th = max(1, int(round(scale * 2)))
    (tw, tht), _ = cv2.getTextSize(stamp, cv2.FONT_HERSHEY_SIMPLEX, scale, th)
    pad = int(8 * scale)
    corners = {"tl": (pad, pad + tht), "tr": (w - tw - pad, pad + tht),
               "bl": (pad, h - pad), "br": (w - tw - pad, h - pad - tht)}

    def overlap(org: tuple[int, int]) -> float:
        x0, y1 = org
        x1, y0 = x0 + tw, y1 - tht * 2 - pad
        tot = 0.0
        for _, bx, by, bw, bh in boxes:
            ix = max(0.0, min(x1, (bx + bw / 2) * w) - max(x0, (bx - bw / 2) * w))
            iy = max(0.0, min(y1, (by + bh / 2) * h) - max(y0, (by - bh / 2) * h))
            tot += ix * iy
        return tot

    order = sorted(corners, key=lambda c: (overlap(corners[c]), rng.random()))
    x, y = corners[order[0]]
    out = img.copy()
    for text, yy in ((stamp, y), (name, y + tht + pad if y < h / 2 else y - tht - pad)):
        cv2.putText(out, text, (x, yy), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0),
                    th + 2, cv2.LINE_AA)
        cv2.putText(out, text, (x, yy), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (235, 235, 235), th, cv2.LINE_AA)
    return out


def min_fire_px(boxes: Sequence[Box], w: int, h: int, train_side: int = 640) -> float:
    """Shortest side of the smallest fire box once the image is resized so its
    long side is ``train_side`` (what the detector sees); ``inf`` if no fire."""
    k = train_side / max(w, h)
    sides = [min(bw * w, bh * h) * k for c, _, _, bw, bh in boxes if c == 0]
    return min(sides) if sides else float("inf")


def pick_effect(key: str, weights: dict[str, float] | None = None) -> str:
    """Effect assigned to an image, deterministic in ``key``."""
    names = list(weights) if weights else list(EFFECTS)
    p = np.array([weights[n] for n in names] if weights else [1.0] * len(names))
    rng = np.random.default_rng(seed_of("hieu_ung:" + key))
    return names[int(rng.choice(len(names), p=p / p.sum()))]


def camera_copy(img: np.ndarray, boxes: Sequence[Box], key: str,
                effect: str | None = None, weights: dict[str, float] | None = None,
                osd_prob: float = 0.3, small_fire_px: float = 8.0
                ) -> tuple[np.ndarray, list[Box], str]:
    """One camera-processing copy of an image and its boxes.

    Parameters
    ----------
    img : numpy.ndarray
        BGR uint8 image.
    boxes : sequence of tuple
        YOLO boxes ``(cls, cx, cy, w, h)``, normalised.
    key : str
        Stable identifier (image stem): seeds the effect choice and strength.
    effect : str, optional
        Force one of ``EFFECTS`` (or ``"osd"``); default draws by ``weights``.
    weights : dict, optional
        Relative frequency of each effect; uniform when omitted.
    osd_prob : float
        Chance of also burning a timestamp in (always when ``effect="osd"``).
    small_fire_px : float
        ``nen_thap`` shrinks the frame to 30–55 %: an image whose smallest fire
        box is below this many pixels at the training size
        (:func:`min_fire_px`) never gets it, the flame would be 2–4 pixels.

    Returns
    -------
    tuple
        ``(image, boxes, tag)``; ``tag`` names the effect(s), e.g.
        ``"nen_thap+osd"``. When the drawn effect would wipe out a box region
        (:func:`boxes_still_visible`), the next effect in ``EFFECTS`` order is
        tried, skipping effects whose weight is 0; geometry-only ``ong_kinh``
        and ``osd`` are always accepted.
    """
    first = effect or pick_effect(key, weights)
    allowed = [e for e in EFFECTS if not weights or weights.get(e, 0) > 0]
    order = [first] + [e for e in allowed if e != first] if first in EFFECTS \
        else [first]
    if min_fire_px(boxes, img.shape[1], img.shape[0]) < small_fire_px:
        order = [e for e in order if e != "nen_thap"] or ["ong_kinh"]
    for effect in order:
        rng = np.random.default_rng(seed_of(f"{effect}:{key}"))
        out, new_boxes = img, list(boxes)
        if effect == "ong_kinh":
            out, new_boxes = _ong_kinh(img, rng, boxes)
        elif effect == "dem_mau":
            out = _dem_mau(img, rng)
        elif effect == "nen_thap":
            out = _nen_thap(img, rng)
        elif effect == "loa_sang":
            out = _loa_sang(img, rng)
        elif effect == "mo":
            out = _mo(img, rng)
        elif effect != "osd":
            raise ValueError(f"hiệu ứng không hợp lệ: {effect}")
        if effect in ("ong_kinh", "osd") or boxes_still_visible(img, out, boxes):
            break
    tag = effect
    if effect == "osd" or rng.random() < osd_prob:
        out = draw_osd(out, rng, new_boxes)
        tag = "osd" if effect == "osd" else f"{effect}+osd"
    return out, new_boxes, tag
