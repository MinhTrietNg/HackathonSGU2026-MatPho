"""Paired non-inferiority (Tango, Newcombe), Holm / IUT and power.

Every formula is checked by an independent route: numerical maximisation of
the restricted likelihood, inversion of the score test on a grid, exact
coverage by enumerating all tables, and Monte Carlo simulation.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from firewatch.noninferiority import (PairedCounts, fa_ni_power_normal, holm,
                                      intersection_union, joint_power_bounds,
                                      mcnemar_one_sided, mcnemar_power_exact,
                                      n_for_power, newcombe_ci, ni_power_exact,
                                      ni_power_normal, noninferiority, tango_ci,
                                      tango_q21, tango_score)
from firewatch.stats import mcnemar_exact, norm_ppf, wilson

Z = norm_ppf(0.975)


def _lgf(k: int) -> float:
    return math.lgamma(k + 1)


def _trinomial(n: int, q12: float, q21: float):
    q0 = 1 - q12 - q21
    for b in range(n + 1):
        for c in range(n - b + 1):
            r = n - b - c
            lp = _lgf(n) - _lgf(b) - _lgf(c) - _lgf(r)
            ok = True
            for k, q in ((b, q12), (c, q21), (r, q0)):
                if k:
                    if q <= 0:
                        ok = False
                        break
                    lp += k * math.log(q)
            if ok:
                yield b, c, math.exp(lp)


# ------------------------------------------------------------------ Tango
def test_tango_score_at_zero_is_mcnemar_score():
    for b, c, n in ((5, 1, 31), (0, 6, 6), (3, 3, 10), (7, 2, 90)):
        assert tango_score(b, c, n, 0.0) == pytest.approx((b - c) / math.sqrt(b + c))


@pytest.mark.parametrize("b,c,n,delta", [(5, 1, 31, -0.1), (5, 1, 31, 0.2),
                                         (0, 0, 20, -0.15), (2, 7, 25, 0.05),
                                         (6, 0, 6, -0.3)])
def test_tango_q21_is_the_restricted_mle(b, c, n, delta):
    """Closed form = numerical argmax of the constrained likelihood."""
    lo, hi = max(0.0, -delta) + 1e-12, (1 - delta) / 2 - 1e-12

    def ll(q):
        out = 0.0
        for k, p in ((b, q + delta), (c, q), (n - b - c, 1 - 2 * q - delta)):
            if k:
                out += k * math.log(max(p, 1e-300))
        return out

    g = (math.sqrt(5) - 1) / 2
    x1, x2 = hi - g * (hi - lo), lo + g * (hi - lo)
    for _ in range(200):
        if ll(x1) > ll(x2):
            hi, x2 = x2, x1
            x1 = hi - g * (hi - lo)
        else:
            lo, x1 = x1, x2
            x2 = lo + g * (hi - lo)
    assert tango_q21(b, c, n, delta) == pytest.approx((lo + hi) / 2, abs=1e-6)


def test_tango_ci_is_the_inverted_score_test():
    grid = np.linspace(-1, 1, 4001)
    n = 12
    for b in range(n + 1):
        for c in range(n - b + 1):
            lo, hi = tango_ci(b, c, n)
            z = np.array([tango_score(b, c, n, d) for d in grid])
            assert np.all(np.diff(z) <= 1e-9)                  # Z giảm theo delta
            inside = grid[np.abs(z) <= Z + 1e-9]
            assert inside.min() == pytest.approx(lo, abs=6e-4)
            assert inside.max() == pytest.approx(hi, abs=6e-4)


def test_vectorised_score_equals_scalar_and_flags_build_the_table():
    from firewatch.noninferiority import tango_score_array
    n = 15
    b, c = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij")
    keep = b + c <= n
    for delta in (-0.2, 0.0, 0.1, -1.0, 1.0):
        z = tango_score_array(b[keep], c[keep], n, delta)
        ref = [tango_score(int(x), int(y), n, delta) for x, y in zip(b[keep], c[keep])]
        assert np.allclose(z, ref, equal_nan=False)
    t = PairedCounts.from_flags([1, 1, 0, 0, 1], [1, 0, 1, 0, 0])
    assert (t.both, t.only_a, t.only_b, t.neither, t.n) == (1, 2, 1, 1, 5)
    assert t.diff == pytest.approx(0.2)
    with pytest.raises(ValueError):
        PairedCounts.from_flags([1], [1, 0])


def test_tango_zero_discordance_is_symmetric_and_shrinks_with_n():
    lo31, hi31 = tango_ci(0, 0, 31)
    lo160, hi160 = tango_ci(0, 0, 160)
    assert lo31 == pytest.approx(-hi31) and hi160 < hi31 < 0.2


def _coverage(n, q12, q21, ci):
    delta = q12 - q21
    return sum(p for b, c, p in _trinomial(n, q12, q21)
               if ci(b, c, n)[0] - 1e-9 <= delta <= ci(b, c, n)[1] + 1e-9)


def _wald(b, c, n):
    d = (b - c) / n
    se = math.sqrt(max((b + c) / n - d * d, 0.0) / n)
    return d - Z * se, d + Z * se


def test_tango_exact_coverage_close_to_nominal():
    """Exact coverage by enumeration (n = 31); Wald shown as a contrast."""
    pts = [(0.05, 0.0), (0.05, 0.05), (0.1, 0.05), (0.2, 0.1), (0.1, 0.1)]
    tango = [_coverage(31, a, b, tango_ci) for a, b in pts]
    wald = [_coverage(31, a, b, _wald) for a, b in pts]
    assert 0.935 <= float(np.mean(tango)) <= 0.975 and min(tango) >= 0.90
    assert float(np.mean(wald)) < float(np.mean(tango)) and min(wald) < 0.85


# --------------------------------------------------------------- Newcombe
def test_newcombe_with_zero_phi_is_square_and_add_of_wilson():
    c = PairedCounts(4, 2, 2, 1)                    # ad - bc = 0 -> phi = 0
    l1, u1 = wilson(6, 9)
    l2, u2 = wilson(6, 9)
    lo, hi = newcombe_ci(c)
    assert lo == pytest.approx(0 - math.sqrt((6 / 9 - l1) ** 2 + (u2 - 6 / 9) ** 2))
    assert hi == pytest.approx(0 + math.sqrt((u1 - 6 / 9) ** 2 + (6 / 9 - l2) ** 2))


def test_newcombe_is_antisymmetric():
    lo, hi = newcombe_ci(PairedCounts(20, 6, 1, 4))
    lo2, hi2 = newcombe_ci(PairedCounts(20, 1, 6, 4))
    assert (lo, hi) == pytest.approx((-hi2, -lo2))


def test_newcombe_exact_coverage_by_enumerating_tables():
    n = 20
    pts = [(0.6, 0.1, 0.05, 0.25), (0.5, 0.2, 0.1, 0.2), (0.3, 0.1, 0.1, 0.5)]
    covs = []
    for q in pts:
        cov = 0.0
        for a in range(n + 1):
            for b in range(n - a + 1):
                for c in range(n - a - b + 1):
                    d = n - a - b - c
                    lp = (_lgf(n) - _lgf(a) - _lgf(b) - _lgf(c) - _lgf(d)
                          + a * math.log(q[0]) + b * math.log(q[1])
                          + c * math.log(q[2]) + d * math.log(q[3]))
                    lo, hi = newcombe_ci(PairedCounts(a, b, c, d))
                    if lo - 1e-9 <= q[1] - q[2] <= hi + 1e-9:
                        cov += math.exp(lp)
        covs.append(cov)
    assert 0.93 <= float(np.mean(covs)) <= 0.98 and min(covs) >= 0.90


# --------------------------------------------------------------- decisions
def test_ni_p_value_agrees_with_interval():
    n = 20
    for b in range(n + 1):
        for c in range(n - b + 1):
            r = noninferiority(PairedCounts(n - b - c, b, c, 0), 0.10)
            assert r.noninferior == (r.p_value < 0.025)


def test_small_n_identical_models_are_not_non_inferior():
    """n = 6, both catch the same 5: the v1 counting rule says "không kém";
    the Tango interval reaches below -0.3 and Newcombe below -0.25, so NI
    fails at a 15-point margin."""
    c = PairedCounts(5, 0, 0, 1)
    assert c.only_b <= c.only_a                         # quy tắc đếm v1: qua
    r = noninferiority(c, 0.15)
    assert not r.noninferior and r.low < -0.3
    assert newcombe_ci(c)[0] < -0.25


@pytest.mark.parametrize("n", [6, 31])
def test_counting_rule_vs_ni_test_for_a_truly_worse_model(n):
    """Model A truly 10 points worse (boundary of the margin), psi = 0.20.
    v1 rule (only_B <= only_A) passes often; the Tango NI test at 0.10
    keeps its one-sided level (exact enumeration)."""
    q_only_a, q_only_b = 0.05, 0.15
    old = sum(p for b, c, p in _trinomial(n, q_only_a, q_only_b) if c <= b)
    new = sum(p for b, c, p in _trinomial(n, q_only_a, q_only_b)
              if noninferiority(PairedCounts(n - b - c, b, c, 0), 0.10).noninferior)
    assert old > 0.10 and new <= 0.035


def test_mcnemar_one_sided_is_half_of_two_sided():
    for a, b in ((6, 0), (8, 1), (10, 2), (3, 1)):
        assert 2 * mcnemar_one_sided(a, b) == pytest.approx(min(1.0,
                                                               mcnemar_exact(a, b)))
    assert mcnemar_one_sided(0, 0) == 1.0 and mcnemar_one_sided(0, 3) == 1.0


def test_holm_by_hand():
    adj = holm({"a": 0.01, "b": 0.04, "c": 0.03}, 0.05)
    assert adj["a"] == (pytest.approx(0.03), True)
    assert adj["c"] == (pytest.approx(0.06), False)
    assert adj["b"] == (pytest.approx(0.06), False)


def test_intersection_union():
    assert intersection_union({"x": True, "y": True})
    assert not intersection_union({"x": True, "y": False})
    assert not intersection_union({})


# ------------------------------------------------------------------- power
def test_ni_power_exact_matches_monte_carlo():
    rng = np.random.default_rng(3)
    n, d, psi = 31, 0.15, 0.20
    q = [(1 - psi) / 2, psi / 2, psi / 2, (1 - psi) / 2]
    reps = 1500
    hits = sum(noninferiority(PairedCounts(*rng.multinomial(n, q)), d).noninferior
               for _ in range(reps))
    p = ni_power_exact(n, d, psi)
    assert abs(hits / reps - p) < 3 * math.sqrt(p * (1 - p) / reps) + 0.005
    # Xấp xỉ chuẩn lạc quan ở n nhỏ (0,51 so với 0,37), gần đúng hơn ở n = 90.
    assert ni_power_normal(n, d, psi) > p
    assert abs(ni_power_normal(90, 0.10, psi) - ni_power_exact(90, 0.10, psi)) < 0.08


def test_mcnemar_power_reproduces_audit_table():
    """01_thanh_phan.md §4.2 (independent script of the audit): Delta 0.15,
    psi 0.25 -> power 0.25 at n = 31 and n = 92 reaches 0.8."""
    assert mcnemar_power_exact(31, 0.25, 0.15) == pytest.approx(0.25, abs=0.01)
    assert mcnemar_power_exact(92, 0.25, 0.15) >= 0.8 > mcnemar_power_exact(
        80, 0.25, 0.15)


def test_n_for_power_and_joint_bounds():
    n = n_for_power(lambda k: ni_power_exact(k, 0.20, 0.20), 0.8, 400)
    assert n is not None and ni_power_exact(n, 0.20, 0.20) >= 0.8
    assert ni_power_exact(n - 12, 0.20, 0.20) < 0.8
    assert n_for_power(lambda k: 0.0, 0.8, 50) is None
    lo, ind, hi = joint_power_bounds(0.9, 6)
    assert lo == pytest.approx(0.4) and ind == pytest.approx(0.9 ** 6) and hi == 0.9


def test_fa_power_normal_limits():
    assert fa_ni_power_normal(1e6, 6_000_000, 3.0, 1.0, 0.5) == pytest.approx(1.0)
    assert fa_ni_power_normal(40, 240, 3.0, 1.0, 0.0) == pytest.approx(0.025)
    assert fa_ni_power_normal(40, 240, 3.0, 1.0, 1.0) > fa_ni_power_normal(
        9, 54, 3.0, 1.0, 1.0)
