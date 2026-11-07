"""Audit helpers: dHash stability, near-duplicate search, union-find, thinning."""

import random
from pathlib import Path

import cv2
import numpy as np

from firewatch.dataaudit import (UnionFind, dhash, hamming, inspect_image,
                                 make_thumb, near_duplicate_pairs, same_scene,
                                 thin_sequence)


def _scene(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, (12, 16), dtype=np.uint8)
    return cv2.resize(base, (320, 240), interpolation=cv2.INTER_CUBIC)


def test_dhash_stable_under_reencode_and_resize():
    img = _scene(1)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])
    reenc = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    resized = cv2.resize(img, (640, 480))
    assert hamming(dhash(img), dhash(reenc)) <= 4
    assert hamming(dhash(img), dhash(resized)) <= 4
    assert hamming(dhash(img), dhash(_scene(2))) > 10


def test_near_duplicate_pairs_matches_brute_force():
    rng = random.Random(0)
    hashes = [rng.getrandbits(64) for _ in range(300)]
    for k in range(30):                               # cấy 30 bản gần trùng
        h = hashes[k]
        for b in rng.sample(range(64), rng.randint(0, 4)):
            h ^= 1 << b
        hashes.append(h)
    fast = {(i, j) for i, j, _ in near_duplicate_pairs(hashes, 4)}
    brute = {(i, j) for i in range(len(hashes)) for j in range(i + 1, len(hashes))
             if hamming(hashes[i], hashes[j]) <= 4}
    assert fast == brute and len(brute) >= 30


def test_union_find_merges_transitively():
    uf = UnionFind(5)
    uf.union(0, 1)
    uf.union(3, 4)
    uf.union(1, 4)
    assert len({uf.find(i) for i in range(5)}) == 2
    assert uf.find(0) == uf.find(3)


def test_thin_sequence_collapses_static_runs():
    a, b = 0, (1 << 64) - 1
    hashes = [a, a, a ^ 1, b, b ^ 3, a]
    assert thin_sequence(list(range(6)), hashes, 4) == [0, 3]


def test_same_scene_verifies_and_ignores_flat_images():
    a = _scene(5)
    ok, buf = cv2.imencode(".jpg", a, [cv2.IMWRITE_JPEG_QUALITY, 50])
    b = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    assert same_scene(make_thumb(a), make_thumb(b))
    assert not same_scene(make_thumb(a), make_thumb(_scene(6)))
    flat = np.full((240, 320), 20, np.uint8)
    noisy_flat = flat + np.random.default_rng(0).integers(0, 3, flat.shape,
                                                          dtype=np.uint8)
    assert make_thumb(flat) is None
    assert not same_scene(make_thumb(flat), make_thumb(noisy_flat))


def test_thin_sequence_respects_verification():
    hashes = [0, 0, 0]
    assert thin_sequence([0, 1, 2], hashes, 4, same=lambda i, j: False) == [0, 1, 2]


def test_inspect_image_flags_gray_and_unicode_path(tmp_path: Path):
    p = tmp_path / "ảnh hồng ngoại.jpg"
    g = _scene(3)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(g, cv2.COLOR_GRAY2BGR))
    p.write_bytes(buf.tobytes())
    info = inspect_image(p)
    assert info.ok and info.gray and info.width == 320 and info.height == 240
    bad = tmp_path / "hong.jpg"
    bad.write_bytes(b"not an image")
    assert inspect_image(bad).ok is False
