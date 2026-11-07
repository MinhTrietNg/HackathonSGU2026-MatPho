"""Split groups for public images that were cut from one video or one camera.

D-Fire and FASDD ship video frames as separate images (``AoF05098`` and
``AoF05101`` are two moments of one clip; ``smoke_CV0185xx–0195xx`` come from
a few fixed mountain cameras). Grouping them one image per group put 2.1 % of
the val originals next to a near-copy in train (thumbnail correlation ≥ 0.98,
measured 04/11/2026), which inflates val and hides overfitting.

Two kinds of link merge groups:

* any two images whose 16×16 thumbnails correlate ≥ ``corr_any``;
* two images of one source whose names share a prefix and whose frame
  numbers differ by at most ``seq_window``, when they correlate ≥
  ``corr_seq`` — consecutive numbers are a strong prior for one clip, so
  the visual test can be looser and chains a whole sequence together.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from firewatch.dataaudit import make_thumb

SEQ_RE = re.compile(r"^(.*?)(\d+)$")


def thumbnails(paths: Sequence[Path], workers: int = 8) -> np.ndarray:
    """Zero-mean / unit-std 16×16 thumbnails, one row of 256 per image.

    Flat images (see :func:`firewatch.dataaudit.make_thumb`) get a row of
    NaN and never link by appearance.
    """
    def one(p: Path) -> np.ndarray:
        g = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_GRAYSCALE)
        t = make_thumb(g) if g is not None else None
        return t.ravel() if t is not None else np.full(256, np.nan, np.float32)

    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(one, paths))
    return np.stack(rows).astype(np.float32) if rows else np.zeros((0, 256),
                                                                    np.float32)


def sequence_key(stem: str) -> tuple[str, int] | None:
    """``("AoF", 5098)`` for ``AoF05098``; ``None`` when no trailing number."""
    m = SEQ_RE.match(stem)
    return (m.group(1), int(m.group(2))) if m else None


def scene_links(stems: Sequence[str], sources: Sequence[str], thumbs: np.ndarray,
                corr_any: float = 0.98, corr_seq: float = 0.90,
                seq_window: int = 20, block: int = 1024) -> list[tuple[int, int]]:
    """Index pairs that belong to one clip / camera (see module docstring).

    Parameters
    ----------
    stems, sources : sequence of str
        File stem and source name of every image.
    thumbs : numpy.ndarray
        ``(n, 256)`` from :func:`thumbnails`.
    corr_any, corr_seq : float
        Correlation needed without / with a naming-sequence prior.
    seq_window : int
        Largest frame-number gap linked through the naming sequence.
    block : int
        Rows per block of the brute-force correlation.

    Returns
    -------
    list of tuple
        ``(i, j)`` with ``i < j``.
    """
    n = len(stems)
    flat = np.isnan(thumbs).any(axis=1)
    t = np.nan_to_num(thumbs)
    links: set[tuple[int, int]] = set()
    for a in range(0, n, block):
        c = t[a:a + block] @ t.T / t.shape[1]
        c[flat[a:a + block]] = -1
        c[:, flat] = -1
        ii, jj = np.nonzero(c >= corr_any)
        links |= {(a + i, j) for i, j in zip(ii.tolist(), jj.tolist()) if a + i < j}
    seq: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    for i, (stem, src) in enumerate(zip(stems, sources)):
        k = sequence_key(stem)
        if k:
            seq[(src, k[0])].append((k[1], i))
    for members in seq.values():
        members.sort()
        for p, (num, i) in enumerate(members):
            for num2, j in members[p + 1:]:
                if num2 - num > seq_window:
                    break
                if not (flat[i] or flat[j]) and float(
                        t[i] @ t[j]) / t.shape[1] >= corr_seq:
                    links.add((min(i, j), max(i, j)))
    return sorted(links)


def merge_groups(groups: Sequence[str], links: Sequence[tuple[int, int]]
                 ) -> list[str]:
    """New group of every item: linked items (and their old groups) unite.

    The merged group keeps the alphabetically first old name, so results do
    not depend on the order of ``links``.
    """
    parent = list(range(len(groups)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    first: dict[str, int] = {}
    for i, g in enumerate(groups):                 # nhóm cũ vẫn là một khối
        if g in first:
            parent[find(i)] = find(first[g])
        else:
            first[g] = i
    for i, j in links:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)
    name: dict[int, str] = {}
    for i, g in enumerate(groups):
        r = find(i)
        name[r] = min(name.get(r, g), g)
    return [name[find(i)] for i in range(len(groups))]
