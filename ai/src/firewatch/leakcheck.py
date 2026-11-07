"""Crop- and scale-tolerant near-duplicate search with classical features.

The dHash check of :mod:`firewatch.dataaudit` hashes the *whole* frame, so a
re-upload that is cropped, rescaled, letter-boxed or carries a new logo is
invisible to it (clip 097 vs test clip 089). This module finds such pairs in
two classical steps, without any neural network:

1. **Candidates (cheap)** — every image becomes a bag of ORB visual words
   (binary descriptors quantised on a small vocabulary trained with
   ``cv2.kmeans``), weighted TF-IDF, square-rooted and L2-normalised. Local
   words survive cropping and rescaling: the overlapping part of two views
   contributes the same words. Cosine similarity ranks the reference images
   for each query and the top ``k`` go to step 2.
2. **Verification** — SIFT keypoints, Lowe ratio test, RANSAC homography.
   A pair is accepted only if enough matches agree with one geometric
   transform *and* the inliers cover a real part of both images (their
   convex hull), so a shared corner logo or a news outro strip alone does
   not count.

Thresholds are module constants fixed before looking at any labelled pair;
callers report them with every result.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

ORB_FEATURES = 500
"""ORB keypoints per image for the candidate step."""
CAND_SIDE = 480
"""Longest image side for the candidate step (pixels)."""
VERIFY_SIDE = 800
"""Longest image side for SIFT verification (pixels)."""
RATIO = 0.75
"""Lowe ratio test."""
RANSAC_PX = 5.0
"""RANSAC reprojection threshold in pixels (at ``VERIFY_SIDE``)."""
MIN_INLIERS = 20
"""Minimum RANSAC inliers for a verified pair."""
MIN_INLIER_RATIO = 0.20
"""Minimum inliers / ratio-test matches."""
MIN_HULL_FRAC = 0.05
"""Minimum convex-hull area of the inliers, as a fraction of each image."""
MIN_SV_RATIO = 0.2
"""Minimum ratio of the singular values of the homography's linear part
(rejects transforms that squash one image onto a line or a point)."""
MAX_JAC_SPREAD = 10.0
"""Maximum ratio of the Jacobian determinants at the four corners of the
query image (rejects folded or extremely perspective-warped mappings)."""
SCALE_RANGE = (0.05, 20.0)
"""Allowed linear scale between the two images."""


# ─────────────────────────── image loading ───────────────────────────


def to_gray(img: np.ndarray, max_side: int) -> np.ndarray:
    """Grayscale copy whose longest side is at most ``max_side``."""
    g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = g.shape[:2]
    s = max_side / max(h, w)
    if s < 1:
        g = cv2.resize(g, (max(1, round(w * s)), max(1, round(h * s))),
                       interpolation=cv2.INTER_AREA)
    return g


def read_gray(path: Path, max_side: int) -> np.ndarray | None:
    """Decode an image file as grayscale, downscaled to ``max_side``.

    Large files are decoded at reduced resolution by libjpeg directly,
    which is much faster than decoding at full size and resizing.
    """
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    flag = cv2.IMREAD_GRAYSCALE
    if data.size > 1_500_000:
        flag = cv2.IMREAD_REDUCED_GRAYSCALE_4
    elif data.size > 400_000:
        flag = cv2.IMREAD_REDUCED_GRAYSCALE_2
    img = cv2.imdecode(data, flag)
    if img is None:
        return None
    return to_gray(img, max_side)


# ───────────────────────── candidate step (ORB) ─────────────────────────


def orb_descriptors(gray: np.ndarray, n: int = ORB_FEATURES) -> np.ndarray:
    """ORB descriptors ``(k, 32)`` uint8; empty array when none."""
    orb = cv2.ORB_create(nfeatures=n)
    _, des = orb.detectAndCompute(gray, None)
    if des is None:
        return np.zeros((0, 32), dtype=np.uint8)
    return des


def _bits(des: np.ndarray) -> np.ndarray:
    return np.unpackbits(des, axis=1).astype(np.float32)


def train_vocabulary(descriptors: np.ndarray, words: int = 1024,
                     seed: int = 0, iters: int = 20) -> np.ndarray:
    """Binary visual words from ORB descriptors (k-means on bits, rounded).

    Parameters
    ----------
    descriptors : np.ndarray
        ``(n, 32)`` uint8 ORB descriptors (a sample of the reference set).
    words : int, optional
        Vocabulary size.
    seed : int, optional
        Seed for ``cv2.kmeans`` (deterministic results).
    iters : int, optional
        Maximum k-means iterations.

    Returns
    -------
    np.ndarray
        ``(words, 32)`` uint8 binary centres.
    """
    if len(descriptors) < words:
        raise ValueError(f"cần ≥ {words} descriptor, có {len(descriptors)}")
    cv2.setRNGSeed(seed)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, iters, 1e-3)
    _, _, centres = cv2.kmeans(_bits(descriptors), words, None, crit, 1,
                               cv2.KMEANS_PP_CENTERS)
    return np.packbits(centres >= 0.5, axis=1)


def assign_words(des: np.ndarray, vocab: np.ndarray) -> np.ndarray:
    """Nearest binary word (Hamming) of every descriptor."""
    if len(des) == 0:
        return np.zeros(0, dtype=np.int64)
    a, v = _bits(des), _bits(vocab)
    # Hamming = |a| + |v| - 2 a·v với a, v thuộc {0, 1}
    ham = a.sum(1, keepdims=True) + v.sum(1)[None, :] - 2.0 * (a @ v.T)
    return ham.argmin(axis=1)


def word_histogram(words: np.ndarray, size: int) -> np.ndarray:
    """Raw term counts ``(size,)`` float32."""
    return np.bincount(words, minlength=size).astype(np.float32)


def idf_weights(histograms: np.ndarray) -> np.ndarray:
    """Inverse document frequency of every word over a set of images."""
    df = (histograms > 0).sum(axis=0).astype(np.float64)
    return np.log((1 + len(histograms)) / (1 + df)).astype(np.float32) + 1.0


def bovw_vectors(histograms: np.ndarray, idf: np.ndarray) -> np.ndarray:
    """TF-IDF, square root (Hellinger), L2-normalised rows."""
    x = np.sqrt(histograms * idf[None, :])
    norm = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.maximum(norm, 1e-9)


def top_candidates(query: np.ndarray, ref: np.ndarray, k: int,
                   chunk: int = 4096) -> tuple[np.ndarray, np.ndarray]:
    """Top-``k`` reference rows by cosine similarity for every query row.

    Returns
    -------
    idx : np.ndarray
        ``(n_query, k)`` reference indices, best first.
    sim : np.ndarray
        Matching similarities.
    """
    k = min(k, len(ref))
    idx = np.zeros((len(query), k), dtype=np.int64)
    sim = np.zeros((len(query), k), dtype=np.float32)
    for s in range(0, len(query), chunk):
        sc = query[s:s + chunk] @ ref.T
        part = np.argpartition(-sc, k - 1, axis=1)[:, :k]
        ps = np.take_along_axis(sc, part, axis=1)
        order = np.argsort(-ps, axis=1, kind="stable")
        idx[s:s + chunk] = np.take_along_axis(part, order, axis=1)
        sim[s:s + chunk] = np.take_along_axis(ps, order, axis=1)
    return idx, sim


# ─────────────────────── verification step (SIFT) ───────────────────────


@dataclass(slots=True)
class Features:
    """SIFT keypoints (as an ``(n, 2)`` array) and descriptors of one image."""

    pts: np.ndarray
    des: np.ndarray
    shape: tuple[int, int]


@dataclass(slots=True)
class Verdict:
    """Geometric verification of one pair."""

    ok: bool
    matches: int
    inliers: int
    inlier_ratio: float
    hull_a: float
    hull_b: float
    reason: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "matches": self.matches, "inliers": self.inliers,
                "inlier_ratio": round(self.inlier_ratio, 3),
                "hull_a": round(self.hull_a, 3), "hull_b": round(self.hull_b, 3),
                "reason": self.reason}


def sift_features(gray: np.ndarray, max_side: int = VERIFY_SIDE) -> Features:
    """SIFT on a grayscale image downscaled to ``max_side``."""
    g = to_gray(gray, max_side)
    kps, des = cv2.SIFT_create().detectAndCompute(g, None)
    if des is None or not kps:
        return Features(np.zeros((0, 2), np.float32),
                        np.zeros((0, 128), np.float32), g.shape[:2])
    pts = np.array([k.pt for k in kps], dtype=np.float32)
    return Features(pts, des.astype(np.float32), g.shape[:2])


def _hull_frac(pts: np.ndarray, shape: tuple[int, int]) -> float:
    if len(pts) < 3:
        return 0.0
    hull = cv2.convexHull(pts.reshape(-1, 1, 2))
    return float(cv2.contourArea(hull)) / float(shape[0] * shape[1])


def homography_problem(h: np.ndarray, shape: tuple[int, int]) -> str:
    """Why ``h`` is not a plausible crop/scale/re-encode mapping (``""`` if ok).

    Checks, on the homography normalised so that ``h[2, 2] = 1``: the linear
    part is not near-singular (singular-value ratio ≥ :data:`MIN_SV_RATIO`),
    its scale lies in :data:`SCALE_RANGE`, and the Jacobian determinant at the
    four corners of the source image keeps one sign and varies by at most
    :data:`MAX_JAC_SPREAD` (no fold, no extreme perspective).
    """
    if abs(h[2, 2]) < 1e-12:
        return "homography suy biến"
    h = h / h[2, 2]
    sv = np.linalg.svd(h[:2, :2], compute_uv=False)
    if sv[1] < MIN_SV_RATIO * sv[0]:
        return f"homography suy biến (tỉ lệ trị kỳ dị {sv[1] / sv[0]:.3f})"
    scale = float(np.sqrt(sv[0] * sv[1]))
    if not SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]:
        return f"tỉ lệ {scale:.3f} ngoài khoảng"
    hgt, wid = shape
    dets = []
    for x, y in ((0, 0), (wid, 0), (0, hgt), (wid, hgt)):
        w = h[2, 0] * x + h[2, 1] * y + 1.0
        if abs(w) < 1e-9:
            return "homography có điểm ở vô cực"
        dets.append(np.linalg.det(h) / w ** 3)
    dets = np.asarray(dets)
    if not (np.all(dets > 0) or np.all(dets < 0)):
        return "homography gập ảnh"
    spread = float(np.abs(dets).max() / max(np.abs(dets).min(), 1e-12))
    if spread > MAX_JAC_SPREAD:
        return f"phối cảnh quá mạnh ({spread:.1f})"
    return ""


def verify(a: Features, b: Features) -> Verdict:
    """Ratio-test SIFT matches + RANSAC homography + inlier coverage.

    The pair is accepted when inliers ≥ :data:`MIN_INLIERS`, inliers /
    matches ≥ :data:`MIN_INLIER_RATIO`, the inlier convex hull covers ≥
    :data:`MIN_HULL_FRAC` of *both* images and the homography passes
    :func:`homography_problem`.
    """
    if len(a.des) < 2 or len(b.des) < 2:
        return Verdict(False, 0, 0, 0.0, 0.0, 0.0, "ít đặc trưng")
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(a.des, b.des, k=2)
    good = [m for m, n in (p for p in pairs if len(p) == 2)
            if m.distance < RATIO * n.distance]
    if len(good) < 4:
        return Verdict(False, len(good), 0, 0.0, 0.0, 0.0, "ít cặp khớp")
    pa = a.pts[[m.queryIdx for m in good]]
    pb = b.pts[[m.trainIdx for m in good]]
    h, mask = cv2.findHomography(pa, pb, cv2.RANSAC, RANSAC_PX, maxIters=2000,
                                 confidence=0.995)
    if h is None or mask is None:
        return Verdict(False, len(good), 0, 0.0, 0.0, 0.0, "không có homography")
    inl = mask.ravel().astype(bool)
    n_in = int(inl.sum())
    ratio = n_in / len(good)
    ha, hb = _hull_frac(pa[inl], a.shape), _hull_frac(pb[inl], b.shape)
    reasons = []
    if n_in < MIN_INLIERS:
        reasons.append(f"inlier {n_in} < {MIN_INLIERS}")
    if ratio < MIN_INLIER_RATIO:
        reasons.append(f"tỉ lệ inlier {ratio:.2f} < {MIN_INLIER_RATIO}")
    if min(ha, hb) < MIN_HULL_FRAC:
        reasons.append(f"vùng phủ {min(ha, hb):.3f} < {MIN_HULL_FRAC}")
    geo = homography_problem(h, a.shape)
    if geo:
        reasons.append(geo)
    return Verdict(not reasons, len(good), n_in, ratio, ha, hb, "; ".join(reasons))


def thresholds() -> dict:
    """The fixed thresholds, for reports."""
    return {"orb_features": ORB_FEATURES, "cand_side": CAND_SIDE,
            "verify_side": VERIFY_SIDE, "ratio": RATIO, "ransac_px": RANSAC_PX,
            "min_inliers": MIN_INLIERS, "min_inlier_ratio": MIN_INLIER_RATIO,
            "min_hull_frac": MIN_HULL_FRAC, "min_sv_ratio": MIN_SV_RATIO,
            "max_jac_spread": MAX_JAC_SPREAD, "scale_range": list(SCALE_RANGE)}


# ───────────────────── frame sources and workers ─────────────────────
# Đặt ở module thư viện (không ở script) để ProcessPoolExecutor trên Windows
# (spawn) pickle được hàm worker.


def video_frames(path: Path, fps: float = 1.0):
    """Yield ``(t_seconds, BGR frame)`` sampled every ``1/fps`` s (by index)."""
    cap = cv2.VideoCapture(str(path))
    vfps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, round(vfps / fps))
    i = 0
    while cap.grab():
        if i % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                yield round(i / vfps, 2), frame
        i += 1
    cap.release()


def frame_at(path: Path, t: float) -> np.ndarray | None:
    """One BGR frame of a video at ``t`` seconds (seek by frame index)."""
    cap = cv2.VideoCapture(str(path))
    vfps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * vfps)))
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def gray_of(key: tuple[str, float], max_side: int = VERIFY_SIDE) -> np.ndarray | None:
    """Gray image of ``(path, t)``: an image file when ``t < 0``, else a frame."""
    path, t = key
    if t < 0:
        return read_gray(Path(path), max_side)
    frame = frame_at(Path(path), t)
    return None if frame is None else to_gray(frame, max_side)


_VOCAB: np.ndarray | None = None


def worker_init(vocab: np.ndarray | str) -> None:
    """Load the vocabulary in a worker process (or in-process)."""
    global _VOCAB
    _VOCAB = np.load(vocab) if isinstance(vocab, str) else vocab
    cv2.setNumThreads(1)


def _hist_of_gray(g: np.ndarray) -> np.ndarray:
    des = orb_descriptors(to_gray(g, CAND_SIDE))
    return word_histogram(assign_words(des, _VOCAB), len(_VOCAB))


def image_hist(path: str) -> tuple[str, np.ndarray | None]:
    """Word histogram of one image file (worker)."""
    g = read_gray(Path(path), CAND_SIDE)
    return path, None if g is None else _hist_of_gray(g)


def video_hists(args: tuple[str, float]) -> list[tuple[str, float, np.ndarray]]:
    """Word histograms of the sampled frames of one video (worker)."""
    path, fps = args
    return [(path, t, _hist_of_gray(to_gray(f, CAND_SIDE)))
            for t, f in video_frames(Path(path), fps)]


REF_CACHE_SIZE = 256
"""SIFT features of recently used reference images kept per worker."""
_REF_CACHE: OrderedDict = OrderedDict()


def ref_features(key: tuple[str, float]) -> Features | None:
    """SIFT features of a reference image, through a small per-process LRU.

    Neighbouring query frames of one clip share most candidates, so feeding
    a worker long runs of consecutive queries makes this cache effective.
    """
    if key in _REF_CACHE:
        _REF_CACHE.move_to_end(key)
        return _REF_CACHE[key]
    g = gray_of(key)
    feats = None if g is None else sift_features(g)
    _REF_CACHE[key] = feats
    if len(_REF_CACHE) > REF_CACHE_SIZE:
        _REF_CACHE.popitem(last=False)
    return feats


def verify_query(args) -> list[dict]:
    """Verify one query ``(key, [(ref_key, sim), ...])`` (worker)."""
    qkey, cands = args
    cv2.setNumThreads(1)
    qg = gray_of(qkey)
    if qg is None:
        return []
    qf = sift_features(qg)
    out = []
    for rkey, sim in cands:
        rf = ref_features(rkey)
        if rf is None:
            continue
        v = verify(qf, rf)
        out.append({"q": qkey[0], "q_t": qkey[1], "r": rkey[0], "r_t": rkey[1],
                    "sim": round(float(sim), 4), **v.to_dict()})
    return out


# ─────────────────────────── statistics ───────────────────────────


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score 95 % interval of ``k / n`` (``(nan, nan)`` when n = 0)."""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def precision_recall(pred: list[bool], truth: list[bool]) -> dict:
    """Precision and recall with counts and Wilson intervals."""
    tp = sum(p and t for p, t in zip(pred, truth))
    fp = sum(p and not t for p, t in zip(pred, truth))
    fn = sum(t and not p for p, t in zip(pred, truth))
    tn = sum(not p and not t for p, t in zip(pred, truth))
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else float("nan"),
            "precision_ci": wilson(tp, tp + fp),
            "recall": tp / (tp + fn) if tp + fn else float("nan"),
            "recall_ci": wilson(tp, tp + fn),
            "specificity": tn / (tn + fp) if tn + fp else float("nan"),
            "specificity_ci": wilson(tn, tn + fp)}
