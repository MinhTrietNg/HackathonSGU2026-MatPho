"""Decision rules of protocol v2: better / not worse / leading (M-6).

Our model ``o`` is compared with each competitor ``j`` on the same files:

* ``NI_S(j)``: lower bound of the two-sided ``1 - alpha`` Tango interval of
  ``S_o - S_j`` (paired sensitivity) is above ``-delta_S``;
* ``NI_F(j)``: upper bound of the paired cluster bootstrap interval of
  ``F_o - F_j`` (false-alarm episodes per hour, clusters = physical
  cameras) is below ``delta_F``. When two clusters or fewer carry any false
  alarm the interval is "không ước lượng được"; NI_F then holds only if the
  exact Poisson upper bound of ``F_o`` alone is below ``delta_F`` (``F_j``
  cannot be negative), and superiority on F cannot be claimed;
* superiority p-values, one-sided: exact McNemar for S, bootstrap for F.

``verdict_pair``: TỐT HƠN = NI_S and NI_F and (superior on S or F, Holm over
the two metrics at ``alpha / 2``); KHÔNG KÉM = NI_S and NI_F; else CHƯA ĐẠT.
``verdict_all``: "không kém mọi đối thủ" and "hàng đầu" by intersection-union
(every per-competitor test at its full level), and Holm over all ``N x 2``
individual superiority claims.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from .eventmetrics import ClipOutcome, Meta, incident_flags
from .noninferiority import (NIResult, PairedCounts, holm, intersection_union,
                             mcnemar_one_sided, noninferiority)
from .stats import MIN_CLUSTERS_WITH_EVENTS, rate_ci


PROTOCOL_VERSION = "2.0"
"""Protocol v2.0, locked 04/11/2026 (``docs/giao_thuc_danh_gia_v2.md``)."""
DELTA_S = 0.15
"""Locked non-inferiority margin on sensitivity (difference of proportions)."""
DELTA_F = 1.0
"""Locked non-inferiority margin on false-alarm episodes per hour."""
ALPHA = 0.05
"""Two-sided level of every interval (one-sided tests at ``ALPHA / 2``)."""
PRIMARY_MEASURE = "at_60"
"""Locked primary sensitivity measure (see :func:`incident_flags`)."""


@dataclass(frozen=True, slots=True)
class Margins:
    """Margins fixed in advance and the two-sided level of the intervals.

    Defaults are the values locked in protocol v2.0.
    """

    delta_s: float = DELTA_S
    delta_f: float = DELTA_F
    alpha: float = ALPHA


@dataclass(frozen=True, slots=True)
class FADiff:
    """Paired difference ``F_o - F_j`` (episodes per hour, negative files)."""

    diff: float
    low: float
    high: float
    estimable: bool
    n_clusters: int
    n_clusters_with_events: int
    p_superior: float
    ours_upper_exact: float


def _cluster_arrays(ours: Sequence[ClipOutcome], theirs: Sequence[ClipOutcome],
                    meta: Meta | None, cluster_key: str, source_key: str
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    by_t = {o.clip: o for o in theirs if not o.positive}
    ya: dict[str, float] = {}
    yb: dict[str, float] = {}
    hh: dict[str, float] = {}
    for o in ours:
        if o.positive:
            continue
        if o.clip not in by_t:
            raise ValueError(f"thiếu clip {o.clip} ở model đối chiếu")
        row = (meta or {}).get(o.clip, {})
        g = row.get(cluster_key) or row.get(source_key) or o.clip
        ya[g] = ya.get(g, 0.0) + len(o.fa_onsets)
        yb[g] = yb.get(g, 0.0) + len(by_t[o.clip].fa_onsets)
        hh[g] = hh.get(g, 0.0) + o.background_h
    keys = sorted(hh)
    return (np.array([ya[k] for k in keys]), np.array([yb[k] for k in keys]),
            np.array([hh[k] for k in keys]))


def fa_paired(ours: Sequence[ClipOutcome], theirs: Sequence[ClipOutcome],
              meta: Meta | None = None, cluster_key: str = "camera_vat_ly",
              source_key: str = "nhom_nguon", alpha: float = 0.05,
              n_boot: int = 4000, seed: int = 42) -> FADiff:
    """Paired cluster bootstrap of the false-alarm rate difference.

    Returns
    -------
    FADiff
        ``p_superior`` = share of bootstrap replicates with ``diff >= 0``
        (one-sided, approximate); ``nan`` when not estimable.
    """
    ya, yb, h = _cluster_arrays(ours, theirs, meta, cluster_key, source_key)
    tot = h.sum()
    obs = (ya.sum() - yb.sum()) / tot if tot > 0 else float("nan")
    m = int(((ya + yb) > 0).sum())
    upper_o = rate_ci(int(ya.sum()), float(tot), alpha)[1] if tot > 0 else float(
        "nan")
    nan = float("nan")
    if m < MIN_CLUSTERS_WITH_EVENTS:
        return FADiff(obs, nan, nan, False, len(h), m, nan, upper_o)
    rng = np.random.default_rng(seed)
    draw = rng.integers(0, len(h), size=(n_boot, len(h)))
    d = (ya[draw].sum(1) - yb[draw].sum(1)) / np.maximum(h[draw].sum(1), 1e-12)
    lo, hi = np.quantile(d, alpha / 2), np.quantile(d, 1 - alpha / 2)
    p_sup = (1 + int((d >= 0).sum())) / (n_boot + 1)
    return FADiff(float(obs), float(lo), float(hi), True, len(h), m, p_sup, upper_o)


@dataclass(frozen=True, slots=True)
class PairVerdict:
    """Our model against one competitor."""

    competitor: str
    measure: str
    sens: NIResult
    p_sens_superior: float
    fa: FADiff
    ni_s: bool
    ni_f: bool
    fa_rule: str
    sup_s: bool
    sup_f: bool
    label: str


def verdict_pair(ours: Sequence[ClipOutcome], theirs: Sequence[ClipOutcome],
                 competitor: str, margins: Margins, meta: Meta | None = None,
                 measure: str = PRIMARY_MEASURE, cluster_key: str = "camera_vat_ly",
                 source_key: str = "nhom_nguon", n_boot: int = 4000,
                 seed: int = 42) -> PairVerdict:
    """Apply the pairwise rule of protocol v2 (see module docstring).

    Parameters
    ----------
    ours, theirs : sequence of ClipOutcome
        Outcomes on the same files.
    competitor : str
        Name of ``theirs``.
    margins : Margins
    meta : mapping, optional
        File metadata (``camera_vat_ly`` for clusters).
    measure : str
        Sensitivity measure of :func:`incident_flags` (primary: ``at_60``).
    """
    fo, ft = incident_flags(ours, measure, meta), incident_flags(theirs, measure, meta)
    if set(fo) != set(ft):
        raise ValueError("hai model không được chấm trên cùng sự cố")
    keys = sorted(fo)
    counts = PairedCounts.from_flags([fo[k] for k in keys], [ft[k] for k in keys])
    sens = noninferiority(counts, margins.delta_s, margins.alpha, "tango")
    p_s = mcnemar_one_sided(counts.only_a, counts.only_b)
    fa = fa_paired(ours, theirs, meta, cluster_key, source_key, margins.alpha,
                   n_boot, seed)
    if fa.estimable:
        ni_f, rule = fa.high < margins.delta_f, "bootstrap"
    else:
        ni_f = fa.ours_upper_exact < margins.delta_f
        rule = "poisson_rieng_model_doi"
    half = margins.alpha / 2
    p_f = fa.p_superior if fa.estimable else 1.0
    adj = holm({"S": p_s, "F": p_f}, half)
    sup_s, sup_f = adj["S"][1], adj["F"][1]
    if sens.noninferior and ni_f and (sup_s or sup_f):
        label = "TỐT HƠN"
    elif sens.noninferior and ni_f:
        label = "KHÔNG KÉM"
    else:
        label = "CHƯA ĐẠT"
    return PairVerdict(competitor, measure, sens, p_s, fa, sens.noninferior, ni_f,
                       rule, sup_s, sup_f, label)


@dataclass(frozen=True, slots=True)
class FieldVerdict:
    """Our model against the whole list of competitors."""

    not_worse_all: bool
    leading: bool
    holm_claims: dict[str, tuple[float, float, bool]]
    pairs: list[PairVerdict]


def verdict_all(pairs: Sequence[PairVerdict], alpha: float = 0.05
                ) -> FieldVerdict:
    """Intersection-union over competitors, Holm over individual claims.

    * ``not_worse_all``: NI_S and NI_F against every competitor.
    * ``leading``: TỐT HƠN against every competitor (each pair at its full
      level, intersection-union).
    * ``holm_claims``: ``"<competitor>:S"`` / ``":F"`` ->
      ``(p, p_holm, rejected)`` over all ``N x 2`` superiority claims at
      ``alpha / 2`` one-sided; only rejected claims may be stated one by one.
    """
    raw: dict[str, float] = {}
    for p in pairs:
        raw[f"{p.competitor}:S"] = p.p_sens_superior
        raw[f"{p.competitor}:F"] = p.fa.p_superior if p.fa.estimable else 1.0
    adj = holm(raw, alpha / 2)
    claims = {k: (raw[k], adj[k][0], adj[k][1]) for k in raw}
    return FieldVerdict(
        intersection_union({p.competitor: p.ni_s and p.ni_f for p in pairs}),
        intersection_union({p.competitor: p.label == "TỐT HƠN" for p in pairs}),
        claims, list(pairs))


def verdicts_from_outcomes(outcomes_by_model: Mapping[str, Sequence[ClipOutcome]],
                           ours: str, margins: Margins, meta: Meta | None = None,
                           **kw) -> FieldVerdict:
    """Convenience: compare ``ours`` with every other model of the mapping."""
    pairs = [verdict_pair(outcomes_by_model[ours], outs, name, margins, meta, **kw)
             for name, outs in outcomes_by_model.items() if name != ours]
    return verdict_all(pairs, margins.alpha)
