"""Image-level audit helpers: integrity, quality metrics, near-duplicates.

Pure functions plus a small union-find, so the audit logic is unit-tested
without real data. ``scripts/audit_data.py`` drives them over every source.

Near-duplicates are found in two steps. A 64-bit difference hash (dHash)
proposes candidates: two images whose hashes differ in ≤ ``max_dist`` bits.
dHash alone collides on low-detail images (dark frames, smoke-filled views),
so every candidate is then *verified* with the Pearson correlation of 16×16
grayscale thumbnails (``same_scene``); nearly flat thumbnails never match.
That catches consecutive 1-fps frames of a static CCTV view, re-encoded
copies and Roboflow augmentations, which exact md5 misses, without chaining
unrelated images together.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(slots=True)
class ImageInfo:
    """Cheap per-image facts gathered in one decode."""

    path: Path
    ok: bool
    width: int = 0
    height: int = 0
    dhash: int = 0
    brightness: float = 0.0
    """Mean luma 0..255 (night scenes are dark)."""
    gray: bool = False
    """All three channels identical (IR / night-vision footage)."""
    sharpness: float = 0.0
    """Variance of the Laplacian on a 256-px-wide copy (low = blurry)."""
    thumb: np.ndarray | None = None
    """16×16 grayscale thumbnail, zero-mean / unit-std (``None`` when flat)."""
    error: str = ""


FLAT_STD = 10.0
"""Thumbnails with a grey-level std below this are 'flat' and never matched."""


def dhash(gray: np.ndarray, size: int = 8) -> int:
    """64-bit difference hash of a grayscale image."""
    small = cv2.resize(gray, (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return int(sum(1 << i for i, b in enumerate(bits) if b))


def make_thumb(gray: np.ndarray) -> np.ndarray | None:
    """Normalised 16×16 thumbnail for :func:`same_scene`; ``None`` if flat."""
    t = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA).astype(np.float32)
    std = float(t.std())
    if std < FLAT_STD:
        return None
    return (t - t.mean()) / std


def same_scene(a: np.ndarray | None, b: np.ndarray | None,
               min_corr: float = 0.90) -> bool:
    """Pearson correlation of two normalised thumbnails ≥ ``min_corr``."""
    if a is None or b is None:
        return False
    return float((a * b).mean()) >= min_corr


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def inspect_image(path: Path) -> ImageInfo:
    """Decode once and compute size, hash, brightness, IR flag, sharpness."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)      # an toàn với tên có dấu
        img = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    except OSError as exc:
        return ImageInfo(path, False, error=f"OSError: {exc}")
    if img is None:
        return ImageInfo(path, False, error="không decode được")
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    b, g, r = img[..., 0], img[..., 1], img[..., 2]
    is_gray = bool(np.abs(b.astype(np.int16) - g).max() <= 3
                   and np.abs(g.astype(np.int16) - r).max() <= 3)
    scale = 256 / w if w > 256 else 1.0
    small = (cv2.resize(gray, (round(w * scale), round(h * scale)))
             if scale < 1 else gray)
    sharp = float(cv2.Laplacian(small, cv2.CV_64F).var())
    return ImageInfo(path, True, w, h, dhash(gray), float(gray.mean()), is_gray, sharp,
                     make_thumb(gray))


class UnionFind:
    """Disjoint sets over integer ids (used to merge near-duplicate groups)."""

    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def cross_pairs(left: list[int], right: list[int], max_dist: int,
                chunk: int = 2048) -> list[tuple[int, int, int]]:
    """All ``(i, j, d)`` with ``hamming(left[i], right[j]) <= max_dist``.

    Brute force over every left × right pair with NumPy popcount, which stays
    fast for loose thresholds where the band trick of
    :func:`near_duplicate_pairs` degenerates into huge buckets.
    """
    if not left or not right:
        return []
    lv = np.array(left, dtype=np.uint64)
    rv = np.array(right, dtype=np.uint64)
    out: list[tuple[int, int, int]] = []
    for s0 in range(0, len(lv), chunk):
        d = np.bitwise_count(lv[s0:s0 + chunk, None] ^ rv[None, :])
        ii, jj = np.nonzero(d <= max_dist)
        out += [(int(i) + s0, int(j), int(d[i, j])) for i, j in zip(ii, jj)]
    return out


FLAT_DIST = 2
"""dHash bits under which two images count as duplicates even when one of
them is too flat for the thumbnail check (dark night frames, fades): without
this, byte-identical dark images were never matched (check of 04/11/2026)."""


def verified(a: np.ndarray | None, b: np.ndarray | None, dist: int,
             min_corr: float = 0.90) -> bool:
    """Accept a dHash candidate pair: thumbnails correlate, or one is flat and
    the hashes are almost equal (``dist <= FLAT_DIST``)."""
    if a is None or b is None:
        return dist <= FLAT_DIST
    return float((a * b).mean()) >= min_corr


def self_pairs(hashes: list[int], max_dist: int,
               chunk: int = 2048) -> list[tuple[int, int, int]]:
    """All ``(i, j, d)`` with ``i < j`` and ``hamming <= max_dist`` (NumPy)."""
    hv = np.array(hashes, dtype=np.uint64)
    out: list[tuple[int, int, int]] = []
    for s0 in range(0, len(hv), chunk):
        d = np.bitwise_count(hv[s0:s0 + chunk, None] ^ hv[None, :])
        ii, jj = np.nonzero(d <= max_dist)
        keep = jj > ii + s0
        out += [(int(i) + s0, int(j), int(d[i, j]))
                for i, j in zip(ii[keep], jj[keep])]
    return out


def near_duplicate_pairs(hashes: list[int], max_dist: int = 4,
                         ) -> list[tuple[int, int, int]]:
    """All index pairs whose dHash distance ≤ ``max_dist``.

    Uses the pigeonhole trick: split the 64 bits into ``max_dist + 1`` bands;
    two hashes within ``max_dist`` must agree exactly on at least one band,
    so only bucket-mates are compared. Exact for the given threshold.
    """
    n_bands = max_dist + 1
    width = 64 // n_bands
    masks = [((1 << width) - 1) << (k * width) for k in range(n_bands - 1)]
    masks.append(~0 & ((1 << 64) - 1) & ~sum(masks))
    seen: set[tuple[int, int]] = set()
    out: list[tuple[int, int, int]] = []
    for mask in masks:
        buckets: dict[int, list[int]] = {}
        for i, h in enumerate(hashes):
            buckets.setdefault(h & mask, []).append(i)
        for members in buckets.values():
            if len(members) < 2:
                continue
            for x in range(len(members)):
                for y in range(x + 1, len(members)):
                    i, j = members[x], members[y]
                    if (i, j) in seen:
                        continue
                    d = hamming(hashes[i], hashes[j])
                    if d <= max_dist:
                        seen.add((i, j))
                        out.append((i, j, d))
    return out


def thin_sequence(order: list[int], hashes: list[int], max_dist: int,
                  same=None) -> list[int]:
    """Keep frames of one clip that differ from every *kept* frame so far.

    ``order`` is the clip's frame indices in time order. Static stretches of
    CCTV collapse to one representative while real changes are kept. ``same``
    (optional ``(i, j) -> bool``) verifies a hash match before dropping.
    """
    kept: list[int] = []
    for i in order:
        dup = any(hamming(hashes[i], hashes[k]) <= max_dist
                  and (same is None or same(i, k)) for k in kept[-50:])
        if not dup:
            kept.append(i)
    return kept
