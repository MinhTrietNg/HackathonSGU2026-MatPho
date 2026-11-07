"""Paired comparison of two detectors on the same incidents (protocol v2, M-6).

Replaces the counting rule of protocol v1 ("incidents only the baseline
caught <= incidents only the candidate caught") by a non-inferiority test
with a margin fixed in advance:

* ``tango_ci`` -- score interval of Tango (1998) for the difference of two
  paired proportions; it stays defined when a discordant cell is zero and
  its test at margin 0 is the McNemar score test;
* ``newcombe_ci`` -- hybrid score interval of Newcombe (1998), built from
  the Wilson intervals of the two marginal proportions and the phi
  correlation of the 2x2 table (no continuity correction);
* one-sided McNemar exact p-value for superiority, Holm step-down for many
  individual claims and the intersection-union rule for "against every
  competitor";
* exact power of these tests by enumerating the trinomial of discordant
  cells, and a normal approximation for false alarms per hour.

All formulas are re-derived in the module docstrings and checked in the
tests by independent means (numerical likelihood maximisation, exact
enumeration of coverage, Monte Carlo); no constant is copied from a paper.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from .stats import norm_cdf, norm_ppf, wilson


@dataclass(frozen=True, slots=True)
class PairedCounts:
    """2x2 table of two models on the same incidents.

    Attributes
    ----------
    both, only_a, only_b, neither : int
        Incidents caught by both / only A / only B / neither.
    """

    both: int
    only_a: int
    only_b: int
    neither: int

    @property
    def n(self) -> int:
        return self.both + self.only_a + self.only_b + self.neither

    @property
    def diff(self) -> float:
        """Observed ``sens(A) - sens(B)``."""
        return (self.only_a - self.only_b) / self.n if self.n else float("nan")

    @classmethod
    def from_flags(cls, a: Sequence[bool], b: Sequence[bool]) -> PairedCounts:
        """Build from per-incident caught flags (same incidents, same order)."""
        if len(a) != len(b):
            raise ValueError("hai model phải được chấm trên cùng danh sách sự cố")
        n11 = sum(1 for x, y in zip(a, b) if x and y)
        n10 = sum(1 for x, y in zip(a, b) if x and not y)
        n01 = sum(1 for x, y in zip(a, b) if y and not x)
        return cls(n11, n10, n01, len(a) - n11 - n10 - n01)


# ------------------------------------------------------------------ Tango
def tango_q21(only_a: int, only_b: int, n: int, delta: float) -> float:
    """Restricted MLE of the ``only_b`` cell probability given ``delta``.

    With cells ``q11, q12 (only A), q21 (only B), q22`` and the constraint
    ``q12 - q21 = delta``, the likelihood in ``q = q21`` is
    ``b log(q + delta) + c log q + (n - b - c) log(1 - 2q - delta)``; its
    stationary point solves ``2n q^2 + B q + C = 0`` with
    ``B = -b - c + (2n - b + c) delta`` and ``C = -c delta (1 - delta)``.
    The admissible root is the larger one.
    """
    a_ = 2.0 * n
    b_ = -only_a - only_b + (2.0 * n - only_a + only_b) * delta
    c_ = -only_b * delta * (1.0 - delta)
    disc = max(b_ * b_ - 4.0 * a_ * c_, 0.0)
    return (math.sqrt(disc) - b_) / (2.0 * a_)


def tango_score(only_a: int, only_b: int, n: int, delta: float) -> float:
    """Score statistic of ``H: sens(A) - sens(B) = delta``.

    ``Z = (b - c - n delta) / sqrt(n (2 q21 + delta (1 - delta)))`` with the
    restricted MLE ``q21``. At ``delta = 0`` it equals the McNemar score
    ``(b - c) / sqrt(b + c)``. Large positive values favour A.
    """
    q = tango_q21(only_a, only_b, n, delta)
    var = n * (2.0 * q + delta * (1.0 - delta))
    num = only_a - only_b - n * delta
    if var <= 1e-15:
        return 0.0 if abs(num) < 1e-12 else math.copysign(math.inf, num)
    return num / math.sqrt(var)


def tango_ci(only_a: int, only_b: int, n: int, alpha: float = 0.05
             ) -> tuple[float, float]:
    """Tango score interval for ``sens(A) - sens(B)`` (paired).

    The set ``{delta : |Z(delta)| <= z}`` (``Z`` decreases with ``delta``)
    is found by bisection on each side of the observed difference.

    Returns
    -------
    tuple of float
        ``(low, high)``; ``(nan, nan)`` when ``n == 0``.
    """
    if n <= 0:
        return float("nan"), float("nan")
    z = norm_ppf(1 - alpha / 2)
    obs = (only_a - only_b) / n

    def solve(lo: float, hi: float, target: float) -> float:
        # Z giảm theo delta: tìm delta với Z(delta) = target (2^-60 là đủ).
        for _ in range(60):
            mid = (lo + hi) / 2
            if tango_score(only_a, only_b, n, mid) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    low = -1.0 if tango_score(only_a, only_b, n, -1.0) <= z else solve(-1.0, obs, z)
    high = 1.0 if tango_score(only_a, only_b, n, 1.0) >= -z else solve(obs, 1.0, -z)
    return low, high


def tango_score_array(b: np.ndarray, c: np.ndarray, n: int, delta: float
                      ) -> np.ndarray:
    """Vectorised :func:`tango_score` over arrays of discordant counts."""
    b = b.astype(float)
    c = c.astype(float)
    a_ = 2.0 * n
    b_ = -b - c + (2.0 * n - b + c) * delta
    c_ = -c * delta * (1.0 - delta)
    q = (np.sqrt(np.maximum(b_ * b_ - 4.0 * a_ * c_, 0.0)) - b_) / (2.0 * a_)
    var = n * (2.0 * q + delta * (1.0 - delta))
    num = b - c - n * delta
    with np.errstate(divide="ignore", invalid="ignore"):
        z = num / np.sqrt(var)
        small = var <= 1e-15
        z[small] = np.where(np.abs(num[small]) < 1e-12, 0.0,
                            np.sign(num[small]) * np.inf)
    return z


# --------------------------------------------------------------- Newcombe
def newcombe_ci(c: PairedCounts, alpha: float = 0.05) -> tuple[float, float]:
    """Newcombe hybrid score interval for paired ``sens(A) - sens(B)``.

    ``theta = p1 - p2``; with Wilson intervals ``[l1, u1]`` of ``p1`` and
    ``[l2, u2]`` of ``p2`` and the phi coefficient of the 2x2 table,
    ``low = theta - sqrt((p1-l1)^2 - 2 phi (p1-l1)(u2-p2) + (u2-p2)^2)`` and
    ``high = theta + sqrt((u1-p1)^2 - 2 phi (u1-p1)(p2-l2) + (p2-l2)^2)``.
    ``phi = 0`` when a margin of the table is empty.
    """
    n = c.n
    if n == 0:
        return float("nan"), float("nan")
    z = norm_ppf(1 - alpha / 2)
    k1, k2 = c.both + c.only_a, c.both + c.only_b
    p1, p2 = k1 / n, k2 / n
    l1, u1 = wilson(k1, n, z)
    l2, u2 = wilson(k2, n, z)
    margins = (k1 * (n - k1) * k2 * (n - k2))
    phi = ((c.both * c.neither - c.only_a * c.only_b) / math.sqrt(margins)
           if margins > 0 else 0.0)
    theta = p1 - p2
    d_lo = math.sqrt(max((p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2)
                         + (u2 - p2) ** 2, 0.0))
    d_hi = math.sqrt(max((u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2)
                         + (p2 - l2) ** 2, 0.0))
    return max(-1.0, theta - d_lo), min(1.0, theta + d_hi)


# --------------------------------------------------------- decisions
@dataclass(frozen=True, slots=True)
class NIResult:
    """Non-inferiority of A versus B on paired sensitivity.

    Attributes
    ----------
    diff, low, high : float
        Observed difference and its two-sided ``1 - alpha`` interval.
    margin : float
        ``delta_S`` (positive): A is non-inferior when ``low > -margin``.
    method : str
        ``tango`` or ``newcombe``.
    noninferior, superior : bool
        ``low > -margin``; ``low > 0``.
    p_value : float
        One-sided score p-value of ``H0: diff <= -margin`` (Tango only;
        ``nan`` for Newcombe, which has no score test).
    counts : PairedCounts
        The 2x2 table.
    """

    diff: float
    low: float
    high: float
    margin: float
    method: str
    noninferior: bool
    superior: bool
    p_value: float
    counts: PairedCounts


def noninferiority(c: PairedCounts, margin: float, alpha: float = 0.05,
                   method: str = "tango") -> NIResult:
    """Paired non-inferiority of sensitivity with a margin set in advance.

    Parameters
    ----------
    c : PairedCounts
        Table of A (our model) against B (a competitor).
    margin : float
        ``delta_S`` > 0, e.g. 0.10 for 10 percentage points.
    alpha : float
        Two-sided level of the interval (one-sided test at ``alpha / 2``).
    method : {"tango", "newcombe"}

    Returns
    -------
    NIResult
    """
    if margin < 0:
        raise ValueError("biên không-kém phải >= 0")
    if method == "tango":
        lo, hi = tango_ci(c.only_a, c.only_b, c.n, alpha)
        z = tango_score(c.only_a, c.only_b, c.n, -margin) if c.n else 0.0
        p = 1.0 - norm_cdf(z) if math.isfinite(z) else (0.0 if z > 0 else 1.0)
    elif method == "newcombe":
        lo, hi = newcombe_ci(c, alpha)
        p = float("nan")
    else:
        raise ValueError(f"method không hợp lệ: {method}")
    return NIResult(c.diff, lo, hi, margin, method, lo > -margin, lo > 0, p, c)


def mcnemar_one_sided(only_a: int, only_b: int) -> float:
    """Exact one-sided McNemar p-value of "A catches more than B".

    ``P(X >= only_a)`` for ``X ~ Binomial(only_a + only_b, 1/2)``.
    """
    n = only_a + only_b
    if n == 0:
        return 1.0
    return sum(math.comb(n, i) for i in range(only_a, n + 1)) / 2 ** n


def holm(pvalues: Mapping[str, float], alpha: float = 0.05
         ) -> dict[str, tuple[float, bool]]:
    """Holm step-down adjustment.

    Parameters
    ----------
    pvalues : mapping
        Claim name -> unadjusted p-value.
    alpha : float
        Family-wise error rate.

    Returns
    -------
    dict
        Claim -> ``(adjusted_p, rejected)``.
    """
    order = sorted(pvalues, key=lambda k: (pvalues[k], k))
    m = len(order)
    out: dict[str, tuple[float, bool]] = {}
    running = 0.0
    for i, key in enumerate(order):
        running = max(running, min(1.0, (m - i) * pvalues[key]))
        out[key] = (running, running <= alpha)
    return out


def intersection_union(decisions: Mapping[str, bool]) -> bool:
    """Intersection-union rule: the claim "for every competitor" holds only
    when each per-competitor test, each at the full level, rejects.

    An empty set of competitors never supports a claim.
    """
    return bool(decisions) and all(decisions.values())


# ------------------------------------------------------------------ power
def _trinomial_grid(n: int, q12: float, q21: float
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """All ``(b, c)`` with ``b + c <= n`` and their trinomial probabilities."""
    if min(q12, q21) < -1e-12 or q12 + q21 > 1 + 1e-12:
        raise ValueError("xác suất ô lệch không hợp lệ")
    lg = np.array([math.lgamma(i + 1) for i in range(n + 1)])
    b, c = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij")
    keep = b + c <= n
    b, c = b[keep], c[keep]
    rest = n - b - c
    q0 = max(1.0 - q12 - q21, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        logp = (lg[n] - lg[b] - lg[c] - lg[rest]
                + np.where(b > 0, b * np.log(max(q12, 1e-300)), 0.0)
                + np.where(c > 0, c * np.log(max(q21, 1e-300)), 0.0)
                + np.where(rest > 0, rest * np.log(max(q0, 1e-300)), 0.0))
    p = np.exp(logp)
    p[(b > 0) & (q12 <= 0)] = 0.0
    p[(c > 0) & (q21 <= 0)] = 0.0
    p[(rest > 0) & (q0 <= 0)] = 0.0
    return b, c, p


def ni_power_exact(n: int, margin: float, psi: float, delta_true: float = 0.0,
                   alpha: float = 0.05) -> float:
    """Exact power of the Tango non-inferiority test.

    Parameters
    ----------
    n : int
        Incidents.
    margin : float
        ``delta_S``.
    psi : float
        True discordance ``P(only A) + P(only B)``.
    delta_true : float
        True ``sens(A) - sens(B)``.
    alpha : float
        Two-sided level of the interval (test at ``alpha / 2``).
    """
    b, c, p = _trinomial_grid(n, (psi + delta_true) / 2, (psi - delta_true) / 2)
    z = tango_score_array(b, c, n, -margin)
    return float(p[z > norm_ppf(1 - alpha / 2)].sum())


def ni_power_normal(n: int, margin: float, psi: float, delta_true: float = 0.0,
                    alpha: float = 0.05) -> float:
    """Normal approximation (Connor-type, as in ``01_thanh_phan.md`` §4.2).

    ``power = Phi((sqrt(n) (delta_true + margin) - z sqrt(psi - margin^2))
    / sqrt(psi - delta_true^2))`` with ``z`` the one-sided ``alpha / 2``
    quantile; the variance under the null boundary uses the same ``psi``.
    """
    z = norm_ppf(1 - alpha / 2)
    v0 = max(psi - margin ** 2, 1e-12)
    v1 = max(psi - delta_true ** 2, 1e-12)
    return norm_cdf((math.sqrt(n) * (delta_true + margin) - z * math.sqrt(v0))
                    / math.sqrt(v1))


def mcnemar_power_exact(n: int, psi: float, delta_true: float,
                        alpha: float = 0.05) -> float:
    """Exact power of the one-sided exact McNemar test at ``alpha / 2``."""
    q12, q21 = (psi + delta_true) / 2, (psi - delta_true) / 2
    b, c, p = _trinomial_grid(n, q12, q21)
    crit = np.full(n + 1, n + 1)
    for nd in range(n + 1):
        tail = 0.0
        for k in range(nd, -1, -1):
            tail += math.comb(nd, k) / 2 ** nd
            if tail > alpha / 2:
                crit[nd] = k + 1
                break
        else:
            crit[nd] = 0
    reject = b >= crit[b + c]
    reject &= (b + c) > 0
    return float(p[reject].sum())


def n_for_power(power_fn, target: float = 0.8, n_max: int = 2000,
                stable: int = 10, n_start: int = 2) -> int | None:
    """Smallest ``n`` with ``power_fn(n) >= target`` for ``stable`` values in
    a row (exact power of discrete tests is saw-toothed).

    ``n_start`` skips small ``n`` known to be far below the target (e.g. half
    of the normal-approximation answer). Returns ``None`` when not reached
    by ``n_max``.
    """
    run = 0
    for n in range(max(2, n_start), n_max + 1):
        run = run + 1 if power_fn(n) >= target else 0
        if run >= stable:
            return n - stable + 1
    return None


def joint_power_bounds(single: float, n_competitors: int
                       ) -> tuple[float, float, float]:
    """Power of an intersection-union claim over ``N`` competitors.

    Returns ``(lower, independent, upper)``: Bonferroni/Fréchet lower bound
    ``max(0, 1 - N (1 - p))``, the value ``p**N`` if the tests were
    independent, and the upper bound ``p``.
    """
    return (max(0.0, 1.0 - n_competitors * (1.0 - single)),
            single ** n_competitors, single)


def fa_ni_power_normal(hours: float, clusters: int, rate: float, cv: float,
                       margin: float, rho: float = 0.0, alpha: float = 0.05,
                       diff_true: float = 0.0) -> float:
    """Approximate power of the false-alarm non-inferiority test.

    Gamma-Poisson model of ``01_thanh_phan.md`` §4.4 per model:
    ``Var(R) = (rate / h + rate^2 cv^2) / G`` with ``h = hours / G``; the two
    models' cluster rates correlate with ``rho``:
    ``Var(R_o - R_j) = 2 (1 - rho) Var(R)``.
    ``power = Phi((margin - diff_true) / se - z)``.
    """
    if clusters <= 0 or hours <= 0:
        return float("nan")
    h = hours / clusters
    var1 = (rate / h + rate ** 2 * cv ** 2) / clusters
    se = math.sqrt(max(2.0 * (1.0 - rho) * var1, 1e-18))
    return norm_cdf((margin - diff_true) / se - norm_ppf(1 - alpha / 2))
