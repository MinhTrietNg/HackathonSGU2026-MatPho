"""Uncertainty for small evaluation sets: intervals and paired tests.

With a few dozen incidents a single number (e.g. "caught 6/8") hides how
little it pins down. Every evaluation report therefore carries:

* a Wilson score interval for proportions (sensitivity per incident);
* an exact (Garwood) Poisson interval for alarm counts per hour, and a
  cluster bootstrap over source videos, because clips cut from one video are
  not independent;
* an exact McNemar test for two models scored on the same incidents, and a
  paired cluster bootstrap for the difference in false alarms per hour.

Protocol v2 adds (same module, same rules):

* ``norm_cdf`` / ``norm_ppf`` (the project has no SciPy);
* a Kaplan-Meier estimate for time-to-detect with missed incidents censored;
* per-cluster false-alarm intervals (cluster bootstrap and a negative
  binomial profile-likelihood interval) that refuse to give a number when
  two clusters or fewer have any false alarm.

Only the standard library and NumPy are used (no SciPy in the project).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

Z95 = 1.959963984540054
MIN_CLUSTERS_WITH_EVENTS = 3
"""Fewer clusters with at least one false alarm -> "không ước lượng được"."""


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval of a proportion ``k / n``.

    Parameters
    ----------
    k, n : int
        Successes and trials.
    z : float
        Normal quantile (1.96 for 95 %).

    Returns
    -------
    tuple of float
        ``(low, high)``; ``(nan, nan)`` when ``n == 0``.
    """
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, center - half), min(1.0, center + half)


def _poisson_cdf(k: int, mu: float) -> float:
    if mu <= 0:
        return 1.0
    term = math.exp(-mu)
    total = term
    for i in range(1, k + 1):
        term *= mu / i
        total += term
    return min(1.0, total)


def _solve(go_up, lo: float, hi: float, iters: int = 200) -> float:
    """Bisection: ``go_up(mu)`` is True while the root lies above ``mu``."""
    for _ in range(iters):
        mid = (lo + hi) / 2
        if go_up(mid):
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def poisson_ci(count: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact (Garwood) interval of a Poisson mean from one observed count.

    Parameters
    ----------
    count : int
        Observed events.
    alpha : float
        1 - confidence level.

    Returns
    -------
    tuple of float
        ``(low, high)`` for the expected count.
    """
    hi_end = count + 10 * math.sqrt(count + 1) + 20
    # P(X >= count | low) = alpha/2 and P(X <= count | high) = alpha/2.
    low = 0.0 if count == 0 else _solve(
        lambda mu: 1 - _poisson_cdf(count - 1, mu) < alpha / 2, 0.0, hi_end)
    high = _solve(lambda mu: _poisson_cdf(count, mu) > alpha / 2, 0.0, hi_end)
    return low, high


def rate_ci(count: int, hours: float, alpha: float = 0.05) -> tuple[float, float]:
    """Exact Poisson interval of a rate per hour."""
    if hours <= 0:
        return float("nan"), float("nan")
    lo, hi = poisson_ci(count, alpha)
    return lo / hours, hi / hours


def cluster_bootstrap_rate(counts: Sequence[float], hours: Sequence[float],
                           groups: Sequence[str], n_boot: int = 4000,
                           seed: int = 42, alpha: float = 0.05
                           ) -> tuple[float, float]:
    """Percentile interval of ``sum(counts) / sum(hours)``, resampling groups.

    Parameters
    ----------
    counts, hours : sequence of float
        Per clip: alarms and duration in hours.
    groups : sequence of str
        Per clip: source video; clips of one group are resampled together.
    n_boot : int
        Bootstrap replicates.
    seed : int
        RNG seed.
    alpha : float
        1 - confidence level.

    Returns
    -------
    tuple of float
        ``(low, high)`` alarms per hour.
    """
    names = sorted(set(groups))
    if not names:
        return float("nan"), float("nan")
    idx = {g: i for i, g in enumerate(names)}
    c = np.zeros(len(names))
    h = np.zeros(len(names))
    for ci, hi, g in zip(counts, hours, groups):
        c[idx[g]] += ci
        h[idx[g]] += hi
    rng = np.random.default_rng(seed)
    draw = rng.integers(0, len(names), size=(n_boot, len(names)))
    rates = c[draw].sum(1) / np.maximum(h[draw].sum(1), 1e-12)
    return (float(np.quantile(rates, alpha / 2)),
            float(np.quantile(rates, 1 - alpha / 2)))


def paired_bootstrap_diff(a: Sequence[float], b: Sequence[float],
                          hours: Sequence[float], groups: Sequence[str],
                          n_boot: int = 4000, seed: int = 42, alpha: float = 0.05
                          ) -> tuple[float, float, float]:
    """Difference of two alarm rates on the same clips, groups resampled.

    Returns
    -------
    tuple of float
        ``(observed, low, high)`` of ``rate(a) - rate(b)`` per hour.
    """
    names = sorted(set(groups))
    idx = {g: i for i, g in enumerate(names)}
    ca, cb, h = (np.zeros(len(names)) for _ in range(3))
    for x, y, t, g in zip(a, b, hours, groups):
        ca[idx[g]] += x
        cb[idx[g]] += y
        h[idx[g]] += t
    obs = (ca.sum() - cb.sum()) / max(h.sum(), 1e-12)
    rng = np.random.default_rng(seed)
    draw = rng.integers(0, len(names), size=(n_boot, len(names)))
    d = (ca[draw].sum(1) - cb[draw].sum(1)) / np.maximum(h[draw].sum(1), 1e-12)
    return float(obs), float(np.quantile(d, alpha / 2)), float(
        np.quantile(d, 1 - alpha / 2))


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar p-value from the discordant pair counts.

    Parameters
    ----------
    only_a : int
        Incidents caught by model A but not by B.
    only_b : int
        Incidents caught by B but not by A.

    Returns
    -------
    float
        ``P`` of a split at least this uneven under H0 (Binomial(n, 0.5)).
    """
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


# ------------------------------------------------------------ protocol v2
def norm_cdf(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def norm_ppf(p: float) -> float:
    """Standard normal quantile by bisection on :func:`norm_cdf`.

    Parameters
    ----------
    p : float
        Probability in ``(0, 1)``.

    Returns
    -------
    float
        ``x`` with ``norm_cdf(x) == p`` (to about 1e-12).
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"p phải nằm trong (0, 1), nhận {p}")
    lo, hi = -40.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def kaplan_meier(times: Sequence[float], observed: Sequence[bool]
                 ) -> list[tuple[float, float, int, int]]:
    """Product-limit estimate of the survival function.

    Parameters
    ----------
    times : sequence of float
        Event or censoring time of each unit (may be negative: a detection
        before the labelled onset).
    observed : sequence of bool
        True for an event (detected), False for censored (missed).

    Returns
    -------
    list of (t, S(t), at_risk, events)
        One row per distinct event time. Units censored at ``t`` count as
        at risk at ``t`` (events are taken before censoring at ties).
    """
    data = sorted(zip((float(t) for t in times), (bool(o) for o in observed)))
    at_risk, surv, i = len(data), 1.0, 0
    out: list[tuple[float, float, int, int]] = []
    while i < len(data):
        t = data[i][0]
        d = c = 0
        while i < len(data) and data[i][0] == t:
            d += data[i][1]
            c += not data[i][1]
            i += 1
        if d:
            surv *= 1.0 - d / at_risk
            out.append((t, surv, at_risk, d))
        at_risk -= d + c
    return out


def km_quantile(times: Sequence[float], observed: Sequence[bool],
                q: float) -> float:
    """Smallest time by which a fraction ``q`` is detected (Kaplan-Meier).

    Returns ``nan`` when censoring stops the curve before ``1 - S(t)``
    reaches ``q`` (the quantile is not identified by the data).
    """
    for t, surv, _, _ in kaplan_meier(times, observed):
        if 1.0 - surv >= q - 1e-12:
            return t
    return float("nan")


@dataclass(frozen=True, slots=True)
class ClusterRate:
    """A rate per hour with an interval computed over clusters.

    Attributes
    ----------
    rate : float
        ``sum(counts) / sum(hours)``.
    lo, hi : float
        Interval bounds; ``nan`` when not estimable.
    n_clusters : int
        Clusters with positive exposure.
    n_clusters_with_events : int
        Clusters with at least one event.
    estimable : bool
        False when ``n_clusters_with_events`` is below the minimum: the
        report must then print "không ước lượng được", not an interval.
    method : str
        ``bootstrap`` or ``negbin``.
    dispersion_k : float or None
        Negative binomial size parameter (``inf`` = Poisson); the
        between-cluster coefficient of variation of the rate is
        ``1 / sqrt(k)``.
    """

    rate: float
    lo: float
    hi: float
    n_clusters: int
    n_clusters_with_events: int
    estimable: bool
    method: str
    dispersion_k: float | None = None


def _per_cluster(counts: Sequence[float], hours: Sequence[float],
                 groups: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    names = sorted(set(groups))
    idx = {g: i for i, g in enumerate(names)}
    y, h = np.zeros(len(names)), np.zeros(len(names))
    for ci, hi, g in zip(counts, hours, groups):
        y[idx[g]] += ci
        h[idx[g]] += hi
    keep = h > 0
    return y[keep], h[keep]


def cluster_rate_ci(counts: Sequence[float], hours: Sequence[float],
                    groups: Sequence[str], method: str = "bootstrap",
                    alpha: float = 0.05, n_boot: int = 4000, seed: int = 42,
                    min_clusters_with_events: int = MIN_CLUSTERS_WITH_EVENTS
                    ) -> ClusterRate:
    """Rate per hour and its interval over clusters (physical cameras).

    Parameters
    ----------
    counts, hours : sequence of float
        Per clip: false-alarm episodes and exposure in hours.
    groups : sequence of str
        Per clip: cluster (``camera_vat_ly``); clips of a cluster are
        resampled / modelled together.
    method : {"bootstrap", "negbin"}
        Percentile cluster bootstrap (:func:`cluster_bootstrap_rate`) or
        negative binomial profile likelihood (:func:`negbin_rate_ci`).
    alpha : float
        1 - confidence level.
    n_boot, seed : int
        Bootstrap settings.
    min_clusters_with_events : int
        Minimum clusters with an event; below it ``estimable`` is False.

    Returns
    -------
    ClusterRate
    """
    y, h = _per_cluster(counts, hours, groups)
    rate = float(y.sum() / h.sum()) if h.sum() > 0 else float("nan")
    m = int((y > 0).sum())
    nan = float("nan")
    if m < min_clusters_with_events:
        return ClusterRate(rate, nan, nan, len(y), m, False, method)
    if method == "bootstrap":
        names = [str(i) for i in range(len(y))]
        lo, hi = cluster_bootstrap_rate(list(y), list(h), names, n_boot, seed, alpha)
        return ClusterRate(rate, lo, hi, len(y), m, True, method)
    if method == "negbin":
        lo, hi, k = negbin_rate_ci(y, h, alpha)
        return ClusterRate(rate, lo, hi, len(y), m, True, method, k)
    raise ValueError(f"method không hợp lệ: {method}")


_K_GRID = np.logspace(-3, 7, 241)


def _negbin_profile(lam: float, y: np.ndarray, h: np.ndarray,
                    flat_i: np.ndarray) -> tuple[float, float]:
    """``max_k`` log-likelihood of NB2 counts with mean ``lam * h``.

    Constant ``-log(y!)`` dropped. The Poisson limit (``k = inf``) is
    included. Returns ``(loglik, k_at_max)``.
    """
    mu = lam * h
    pois = float((y * np.log(mu) - mu).sum())
    kk = _K_GRID[:, None]
    gam = (np.log(kk + flat_i[None, :]).sum(1) if flat_i.size
           else np.zeros(len(_K_GRID)))
    rest = (-kk * np.log1p(mu[None, :] / kk)
            + y[None, :] * (np.log(mu)[None, :] - np.log(kk + mu[None, :]))).sum(1)
    ll = gam + rest
    j = int(np.argmax(ll))
    if pois >= ll[j]:
        return pois, float("inf")
    return float(ll[j]), float(_K_GRID[j])


def negbin_rate_ci(y: Sequence[float], h: Sequence[float], alpha: float = 0.05
                   ) -> tuple[float, float, float]:
    """Profile-likelihood interval of a common rate, NB2 counts per cluster.

    Model: ``y_g ~ NegBin(mean = lam * h_g, size = k)``, i.e. the
    Gamma-Poisson model of ``01_thanh_phan.md`` §4.4 with ``c = 1/sqrt(k)``.
    ``k`` is profiled out on a log grid (plus the Poisson limit); the bounds
    solve ``2 * (l(lam_hat) - l(lam)) = z**2``.

    Parameters
    ----------
    y : sequence of float
        Event count per cluster (non-negative integers).
    h : sequence of float
        Exposure per cluster in hours (> 0).
    alpha : float
        1 - confidence level.

    Returns
    -------
    tuple of float
        ``(low, high, k_hat)``; ``(nan, nan, nan)`` when no event.
    """
    y_arr = np.asarray(y, dtype=float)
    h_arr = np.asarray(h, dtype=float)
    if y_arr.sum() <= 0:
        return float("nan"), float("nan"), float("nan")
    flat_i = np.concatenate([np.arange(int(v)) for v in y_arr]).astype(float)

    def prof(v: float) -> float:
        return _negbin_profile(math.exp(v), y_arr, h_arr, flat_i)[0]

    # MLE của log(lam) bằng golden-section quanh tỷ lệ thô.
    v0 = math.log(y_arr.sum() / h_arr.sum())
    a, b = v0 - 4.0, v0 + 4.0
    g = (math.sqrt(5) - 1) / 2
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = prof(c), prof(d)
    for _ in range(60):
        if fc > fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = prof(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = prof(d)
    v_hat = (a + b) / 2
    l_hat = prof(v_hat)
    k_hat = _negbin_profile(math.exp(v_hat), y_arr, h_arr, flat_i)[1]
    target = l_hat - norm_ppf(1 - alpha / 2) ** 2 / 2

    def root(lo_v: float, hi_v: float, rising: bool) -> float:
        for _ in range(60):
            mid = (lo_v + hi_v) / 2
            above = prof(mid) > target
            if above == rising:
                hi_v = mid
            else:
                lo_v = mid
        return math.exp((lo_v + hi_v) / 2)

    low = root(v_hat - 40.0, v_hat, rising=True)
    # Phân tán cực lớn với ít cụm: hồ sơ không xuống dưới ngưỡng -> cận trên vô hạn.
    if prof(v_hat + 40.0) > target:
        return low, float("inf"), k_hat
    high = root(v_hat, v_hat + 40.0, rising=False)
    return low, high, k_hat
