"""Normal quantiles, Kaplan-Meier and false-alarm intervals over clusters."""

from __future__ import annotations

import math

import numpy as np
import pytest

from firewatch.stats import (cluster_bootstrap_rate, cluster_rate_ci, kaplan_meier,
                             km_quantile, negbin_rate_ci, norm_cdf, norm_ppf,
                             rate_ci)


def test_norm_ppf_inverts_cdf():
    assert norm_ppf(0.975) == pytest.approx(1.959963984540054, abs=1e-9)
    for p in (0.001, 0.2, 0.5, 0.8, 0.999):
        assert norm_cdf(norm_ppf(p)) == pytest.approx(p, abs=1e-12)
    with pytest.raises(ValueError):
        norm_ppf(1.0)


def _efron_redistribute(times, observed):
    """Kaplan-Meier by Efron's redistribute-to-the-right (independent algorithm):
    each censored unit passes its mass equally to every unit to its right."""
    order = sorted(range(len(times)), key=lambda i: (times[i], not observed[i]))
    mass = {i: 1 / len(times) for i in order}
    for pos, i in enumerate(order):
        if not observed[i]:
            right = order[pos + 1:]
            if right:
                for j in right:
                    mass[j] += mass[i] / len(right)
                mass[i] = 0.0
    out, acc = {}, 0.0
    for i in order:
        if observed[i]:
            acc += mass[i]
            out[times[i]] = 1.0 - acc
    return out


def test_kaplan_meier_equals_redistribute_to_the_right():
    rng = np.random.default_rng(5)
    for _ in range(30):
        n = int(rng.integers(3, 25))
        times = [float(t) for t in rng.integers(-5, 30, n)]
        observed = [bool(x) for x in rng.random(n) < 0.6]
        km = {t: s for t, s, _, _ in kaplan_meier(times, observed)}
        ref = _efron_redistribute(times, observed)
        assert set(km) == set(ref)
        for t in km:
            assert km[t] == pytest.approx(ref[t], abs=1e-12)


def test_km_quantile_without_censoring_is_empirical_and_nan_when_not_reached():
    t = [4.0, 1.0, 3.0, 2.0]
    assert km_quantile(t, [True] * 4, 0.5) == 2.0
    assert km_quantile(t, [True] * 4, 0.75) == 3.0
    # Chỉ t = 1 là sự kiện, các đơn vị khác kiểm duyệt: S dừng ở 0,75.
    assert math.isnan(km_quantile(t, [False, True, False, False], 0.5))
    # Sự kiện duy nhất ở cuối (t = 4) đưa S về 0.
    assert km_quantile(t, [True, False, False, False], 0.5) == 4.0


def test_cluster_interval_refuses_two_or_fewer_clusters_with_events():
    c = cluster_rate_ci([4, 0, 0, 3], [1, 1, 1, 1], ["a", "b", "c", "a"])
    assert not c.estimable and c.n_clusters_with_events == 1 and c.n_clusters == 3
    assert math.isnan(c.lo) and c.rate == pytest.approx(7 / 4)
    nb = cluster_rate_ci([4, 0, 0, 3], [1, 1, 1, 1], list("abcd"), "negbin")
    assert not nb.estimable and nb.n_clusters_with_events == 2
    assert cluster_rate_ci([4, 0, 2, 3], [1, 1, 1, 1], list("abcd"),
                           "negbin").estimable
    with pytest.raises(ValueError):
        cluster_rate_ci([1, 1, 1], [1, 1, 1], list("abc"), "bad")


def test_cluster_bootstrap_interval_matches_existing_function():
    y, h, g = [2, 0, 1, 3, 0, 1], [0.5] * 6, list("abcdef")
    c = cluster_rate_ci(y, h, g, "bootstrap", n_boot=2000, seed=1)
    assert c.estimable and (c.lo, c.hi) == cluster_bootstrap_rate(y, h, g, 2000, 1)


def _poisson_lr_ci(total, hours, z=1.959963984540054):
    """Likelihood-ratio interval of a Poisson rate, solved independently."""
    lam_hat = total / hours

    def ll(lam):
        return total * math.log(lam) - lam * hours

    target = ll(lam_hat) - z * z / 2

    def solve(a, b, rising):
        for _ in range(200):
            m = (a + b) / 2
            if (ll(m) > target) == rising:
                b = m
            else:
                a = m
        return (a + b) / 2

    return solve(1e-9, lam_hat, True), solve(lam_hat, 100 * lam_hat, False)


def test_negbin_reduces_to_poisson_without_overdispersion():
    y, h = [2, 2, 2, 2, 2, 2], [0.5] * 6
    lo, hi, k = negbin_rate_ci(y, h)
    assert math.isinf(k)
    plo, phi = _poisson_lr_ci(12, 3.0)
    assert lo == pytest.approx(plo, rel=1e-4) and hi == pytest.approx(phi, rel=1e-4)


def test_negbin_covers_better_than_poisson_under_overdispersion():
    """Monte Carlo, Gamma-Poisson clusters (c = 1, 30 cameras x 1 hour): the
    exact Poisson interval ignores between-camera spread and under-covers."""
    rng = np.random.default_rng(2)
    lam, g_n, h, reps = 3.0, 30, 1.0, 80
    nb = po = 0
    for _ in range(reps):
        y = rng.poisson(rng.gamma(1.0, lam, g_n) * h)
        lo, hi, _ = negbin_rate_ci(y, [h] * g_n)
        nb += lo <= lam <= hi
        plo, phi = rate_ci(int(y.sum()), g_n * h)
        po += plo <= lam <= phi
    assert nb / reps >= 0.85 and nb / reps > po / reps + 0.1
