"""Loose same-scene search between training hashes and held-out hashes."""

import random

from firewatch.dataaudit import cross_pairs, hamming


def test_cross_pairs_finds_every_pair_within_distance():
    rng = random.Random(0)
    left = [rng.getrandbits(64) for _ in range(300)]
    right = [rng.getrandbits(64) for _ in range(200)]
    right[3] = left[10] ^ 0b1011              # 3 bit khác
    right[4] = left[11] ^ ((1 << 11) - 1)     # 11 bit khác: ngoài ngưỡng 10
    got = cross_pairs(left, right, 10, chunk=64)
    want = [(i, j, hamming(a, b)) for i, a in enumerate(left)
            for j, b in enumerate(right) if hamming(a, b) <= 10]
    assert sorted(got) == sorted(want)
    assert (10, 3, 3) in got and all((11, 4) != (i, j) for i, j, _ in got)
    assert cross_pairs([], right, 4) == [] and cross_pairs(left, [], 4) == []


def test_self_pairs_and_flat_verification():
    import numpy as np

    from firewatch.dataaudit import self_pairs, verified
    rng = random.Random(1)
    hs = [rng.getrandbits(64) for _ in range(150)]
    hs[20] = hs[5] ^ 0b11
    got = self_pairs(hs, 8, chunk=32)
    want = [(i, j, hamming(hs[i], hs[j])) for i in range(len(hs))
            for j in range(i + 1, len(hs)) if hamming(hs[i], hs[j]) <= 8]
    assert sorted(got) == sorted(want) and (5, 20, 2) in got
    t = np.ones(256, np.float32)
    assert verified(None, t, 2) and not verified(None, t, 3)   # ảnh phẳng
    assert verified(t, t, 9) and not verified(t, -t, 0)
