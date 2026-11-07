"""Event-level scoring of protocol v2 (``docs/giao_thuc_danh_gia_v2.md``).

Works next to :mod:`firewatch.evalkit`, whose functions keep the v1 rules.
Input per clip is a :class:`ClipRun`: the label (schema ``t1_dev_v1.1``,
older JSON without the new keys is accepted), every alert with its kind and,
when recorded, every voting transition. Rules (each is one finding of the
T1 audit):

* M-1: every confirmation is a detection signal, not only alerts that passed
  the cooldowns; a signal in ``[t_start - early_s, t_start)`` catches the
  incident with TTD <= 0 and goes to the eye-review list; false alarms before
  the incident on positive files are reported separately ("FA trước sự cố").
* M-2: sensitivity at tolerance 0 s and 30 s after ``t_end``; signals inside
  ``sau_chay`` never catch and are never false alarms; ``rac`` is removed
  from scoring and from the negative hours.
* M-3: false alarms counted per episode (:func:`firewatch.episodes.episode_onsets`),
  with the share of source videos having at least one, split by ``loai_am``.
* M-5: TTD on incidents every compared model caught, ``t_start >= 10 s``,
  ``statistics.median``; plus a censored (Kaplan-Meier) distribution.
* M-6 (with :mod:`firewatch.noninferiority`): sensitivity within 60 s and
  sensitivity in the early (smoke-only) phase.

Metadata per file (``files.csv`` of T1-dev v1.1, or ``clips_meta.csv``) is a
plain mapping ``file -> {column: value}``, so any table can be used. Labels,
runs and their I/O are in :mod:`firewatch.eventruns` (re-exported here).
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .episodes import Transition, episode_onsets, signals
# Nhãn, run và đọc/ghi nằm ở eventruns; xuất lại ở đây cho tiện import.
from .eventruns import (ClipLabel, ClipRun, IncidentLabel, Interval,  # noqa: F401
                        dump_run, label_to_dict, load_file_meta, load_runs,
                        merged_incidents, parse_label, runs_from_dump)
from .stats import ClusterRate, cluster_rate_ci, kaplan_meier, km_quantile
from .stats import rate_ci, wilson

Meta = Mapping[str, Mapping[str, str]]
NO_GROUP = "(trống)"


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    """Parameters of protocol v2, fixed before any run.

    Attributes
    ----------
    early_s : float
        Signals up to this many seconds before ``t_start`` catch (TTD <= 0).
    tolerances_s : tuple of float
        Tolerances after ``t_end`` reported for sensitivity.
    main_tolerance_s : float
        Tolerance used for TTD, the horizon cap and the false-alarm exclusion.
    horizon_s : float
        "Sensitivity within ``horizon_s``" counts signals up to
        ``min(t_start + horizon_s, t_end + main_tolerance_s)``.
    min_ttd_start_s : float
        TTD is reported only for incidents with ``t_start`` at least this.
    min_smoke_phase_s : float
        An incident is eligible for the early-phase sensitivity when it has
        ``t_khoi`` and ``t_lua`` with ``t_lua - t_khoi >= min_smoke_phase_s``
        (6 s = k_enter heartbeats at 1 Hz, so a perfect detector can confirm
        before flames).
    merge_scene_episodes : bool
        Count overlapping confirmations of several tracks as one episode
        (secondary variant; the protocol counts per track).
    """

    early_s: float = 10.0
    tolerances_s: tuple[float, ...] = (0.0, 30.0)
    main_tolerance_s: float = 30.0
    horizon_s: float = 60.0
    min_ttd_start_s: float = 10.0
    min_smoke_phase_s: float = 6.0
    merge_scene_episodes: bool = False


# --------------------------------------------------------------- intervals
def _norm(ivs: Iterable[Interval], lo: float, hi: float) -> list[Interval]:
    """Clip to ``[lo, hi]``, drop empty, sort and merge."""
    parts = sorted((max(a, lo), min(b, hi)) for a, b in ivs if min(b, hi) > max(a, lo))
    out: list[Interval] = []
    for a, b in parts:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _subtract(base: list[Interval], cut: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for a, b in base:
        cur = a
        for c, d in cut:
            if d <= cur or c >= b:
                continue
            if c > cur:
                out.append((cur, c))
            cur = max(cur, d)
        if cur < b:
            out.append((cur, b))
    return out


def _length(ivs: Iterable[Interval]) -> float:
    return sum(b - a for a, b in ivs)


def _inside(t: float, ivs: Iterable[Interval]) -> bool:
    return any(a <= t <= b for a, b in ivs)


# ---------------------------------------------------------------- outcomes
@dataclass(slots=True)
class IncidentOutcome:
    """Result of one incident for one model.

    ``first`` maps each tolerance to the first counted signal (``None`` =
    missed at that tolerance). ``window_end_s`` closes the main catch window
    and is the censoring point of a missed incident.
    """

    clip: str
    index: int
    t_start: float
    t_end: float | None
    t_khoi: float | None
    t_lua: float | None
    first: dict[float, Transition | None]
    main_tolerance_s: float
    at_horizon: bool
    early_phase_eligible: bool
    early_phase: bool
    window_end_s: float

    @property
    def key(self) -> tuple[str, int]:
        return self.clip, self.index

    def caught(self, tolerance_s: float | None = None) -> bool:
        tol = self.main_tolerance_s if tolerance_s is None else tolerance_s
        return self.first.get(tol) is not None

    def ttd(self, tolerance_s: float | None = None) -> float | None:
        tol = self.main_tolerance_s if tolerance_s is None else tolerance_s
        s = self.first.get(tol)
        return None if s is None else s.ts - self.t_start

    @property
    def early_hit(self) -> bool:
        """Caught by a signal before ``t_start`` (TTD < 0): eye review."""
        s = self.first.get(self.main_tolerance_s)
        return s is not None and s.ts < self.t_start


@dataclass(slots=True)
class ClipOutcome:
    """Result of one file for one model (seconds; hours via properties)."""

    clip: str
    positive: bool
    duration_s: float
    valid_s: float
    background_s: float
    prefire_s: float
    incidents: list[IncidentOutcome]
    fa_onsets: list[Transition]
    prefire_onsets: list[Transition]
    fa_alerts: list[Transition]
    prefire_alerts: list[Transition]
    dropped_rac: list[Transition]
    dropped_sau_chay: list[Transition]
    episode_source: str

    @property
    def background_h(self) -> float:
        return self.background_s / 3600

    @property
    def prefire_h(self) -> float:
        return self.prefire_s / 3600


def score_clip(run: ClipRun, cfg: ScoringConfig = ScoringConfig()) -> ClipOutcome:
    """Score one file with the v2 rules (see module docstring).

    Parameters
    ----------
    run : ClipRun
    cfg : ScoringConfig

    Returns
    -------
    ClipOutcome
    """
    dur = float(run.duration_s)
    rac = _norm(run.label.rac, 0.0, dur)
    sau = _norm(run.label.sau_chay, 0.0, dur)
    sig = signals(run.transitions, run.alerts)
    dropped_rac = [s for s in sig if _inside(s.ts, rac)]
    dropped_sau = [s for s in sig if not _inside(s.ts, rac) and _inside(s.ts, sau)]
    usable = [s for s in sig if not _inside(s.ts, rac) and not _inside(s.ts, sau)]
    tols = sorted(set(cfg.tolerances_s) | {cfg.main_tolerance_s})
    incidents: list[IncidentOutcome] = []
    protected: list[Interval] = []
    for i, ev in enumerate(merged_incidents(run.label)):
        end = ev.t_end if ev.t_end is not None else dur
        lo = ev.t_start - cfg.early_s
        first: dict[float, Transition | None] = {}
        for tol in tols:
            first[tol] = next((s for s in usable if lo <= s.ts <= end + tol), None)
        h_end = min(ev.t_start + cfg.horizon_s, end + cfg.main_tolerance_s)
        eligible = (ev.t_khoi is not None and ev.t_lua is not None
                    and ev.t_lua - ev.t_khoi >= cfg.min_smoke_phase_s)
        early = eligible and any(lo <= s.ts < ev.t_lua for s in usable)
        incidents.append(IncidentOutcome(
            run.clip, i, ev.t_start, ev.t_end, ev.t_khoi, ev.t_lua, first,
            cfg.main_tolerance_s, any(lo <= s.ts <= h_end for s in usable),
            eligible, early, min(end + cfg.main_tolerance_s, dur)))
        protected.append((lo, end + cfg.main_tolerance_s))
    excluded = _norm(rac + sau + protected, 0.0, dur)
    valid = _subtract([(0.0, dur)], rac)
    background = _subtract([(0.0, dur)], excluded)
    first_lo = min((a for a, _ in protected), default=None)
    prefire = (_subtract(_norm([(0.0, first_lo)], 0.0, dur), excluded)
               if first_lo is not None else [])

    def in_background(t: float) -> bool:
        return (0.0 <= t <= dur and not _inside(t, rac) and not _inside(t, sau)
                and not _inside(t, protected))

    onsets = episode_onsets(run.transitions, run.alerts, cfg.merge_scene_episodes,
                            dur)
    fa = [o for o in onsets if in_background(o.ts)]
    fa_alerts = [a for a in run.alerts if in_background(a.ts)]

    def before_first(t: float) -> bool:
        return first_lo is not None and t < first_lo

    return ClipOutcome(
        run.clip, run.positive, dur, _length(valid), _length(background),
        _length(prefire), incidents, fa, [o for o in fa if before_first(o.ts)],
        fa_alerts, [a for a in fa_alerts if before_first(a.ts)], dropped_rac,
        dropped_sau, "transitions" if run.transitions is not None else "alerts_legacy")


def score_runs(runs: Sequence[ClipRun], cfg: ScoringConfig = ScoringConfig()
               ) -> list[ClipOutcome]:
    """:func:`score_clip` over many files."""
    return [score_clip(r, cfg) for r in runs]


# -------------------------------------------------------------- aggregates
@dataclass(frozen=True, slots=True)
class Proportion:
    """``k / n`` with its Wilson 95 % interval."""

    k: int
    n: int
    low: float
    high: float

    @property
    def rate(self) -> float:
        return self.k / self.n if self.n else float("nan")


def proportion(k: int, n: int) -> Proportion:
    lo, hi = wilson(k, n)
    return Proportion(k, n, lo, hi)


def measure_names(cfg: ScoringConfig = ScoringConfig()) -> list[str]:
    """Names accepted by :func:`incident_flags`, in report order."""
    tols = sorted(set(cfg.tolerances_s) | {cfg.main_tolerance_s})
    return ([f"tol_{tol:g}" for tol in tols] + [f"at_{cfg.horizon_s:g}"]
            + ["early_phase"])


def _flag(inc: IncidentOutcome, measure: str) -> bool | None:
    """Caught flag of one incident; ``None`` when not eligible."""
    if measure.startswith("tol_"):
        return inc.caught(float(measure[4:]))
    if measure.startswith("at_"):
        return inc.at_horizon
    if measure == "early_phase":
        return inc.early_phase if inc.early_phase_eligible else None
    raise ValueError(f"thước đo không hợp lệ: {measure}")


def incident_flags(outcomes: Sequence[ClipOutcome], measure: str,
                   meta: Meta | None = None, group_key: str = "nhom_su_co"
                   ) -> dict[tuple[str, int], bool]:
    """Caught flag per incident for one sensitivity measure.

    Parameters
    ----------
    outcomes : sequence of ClipOutcome
    measure : str
        ``tol_<s>`` (e.g. ``tol_0``, ``tol_30``), ``at_<s>`` (the horizon,
        e.g. ``at_60``) or ``early_phase`` (eligible incidents only).
    meta : mapping, optional
        When a file has ``group_key`` (several files of one incident), its
        incidents are keyed ``(group, index)`` and caught when any file of
        the group catches; otherwise the key is ``(file, index)``.
    group_key : str
        Metadata column naming the incident.
    """
    out: dict[tuple[str, int], bool] = {}
    for o in outcomes:
        grp = _group(meta, o.clip, group_key)
        for inc in o.incidents:
            flag = _flag(inc, measure)
            if flag is None:
                continue
            key = (grp, inc.index) if grp else inc.key
            out[key] = out.get(key, False) or flag
    return out


def caught_fn_for(outcomes: Sequence[ClipOutcome], measure: str = "at_60"):
    """Adapter for ``tiers.sens_cell(caught_fn=...)``.

    Returns ``fn(r, tol) -> list[bool]``: the v2 flags of file ``r.clip``
    (``tol`` is ignored: ``measure`` fixes the window). ``early_phase`` is
    refused because ``sens_cell`` would count ineligible incidents as missed.
    """
    if measure == "early_phase":
        raise ValueError("early_phase chỉ dùng qua sensitivity_summary")
    by = {o.clip: o for o in outcomes}

    def fn(r: Any, _tol: float) -> list[bool]:
        return [bool(_flag(inc, measure)) for inc in by[r.clip].incidents]

    return fn


def fa_fn_for(outcomes: Sequence[ClipOutcome], prefire: bool = False):
    """Adapter for ``tiers.fa_cell(fa_fn=...)``.

    Returns ``fn(r, tol) -> (episodes, hours)`` of file ``r.clip``: false-
    alarm episodes and exposure without ``rac`` / ``sau_chay`` (pre-fire
    part of positive files when ``prefire``).
    """
    by = {o.clip: o for o in outcomes}

    def fn(r: Any, _tol: float) -> tuple[float, float]:
        o = by[r.clip]
        if prefire:
            return float(len(o.prefire_onsets)), o.prefire_h
        return float(len(o.fa_onsets)), o.background_h

    return fn


def sensitivity_summary(outcomes: Sequence[ClipOutcome],
                        cfg: ScoringConfig = ScoringConfig(),
                        meta: Meta | None = None
                        ) -> dict[str, Proportion]:
    """Every sensitivity measure, plus ``early_hits`` (caught with TTD < 0).

    With ``meta``, files of one ``nhom_su_co`` count as one incident.
    """
    out = {}
    for m in measure_names(cfg):
        flags = incident_flags(outcomes, m, meta)
        out[m] = proportion(sum(flags.values()), len(flags))
    incs = [inc for o in outcomes for inc in o.incidents]
    out["early_hits"] = proportion(sum(inc.early_hit for inc in incs), len(incs))
    return out


def _group(meta: Meta | None, clip: str, key: str) -> str | None:
    if not meta:
        return None
    v = meta.get(clip, {}).get(key)
    return v or None


@dataclass(frozen=True, slots=True)
class FASummary:
    """False-alarm episodes per hour over a set of files.

    ``poisson`` is the exact interval assuming independent episodes;
    ``bootstrap`` and ``negbin`` are computed over clusters ``cluster_key``
    (``estimable`` False -> "không ước lượng được"). ``sources`` is the share
    of source videos (``source_key``) with at least one episode.
    ``raw_alerts`` counts alerts in the same exposure (unit of protocol v1).
    """

    files: int
    hours: float
    episodes: int
    rate: float
    poisson: tuple[float, float]
    bootstrap: ClusterRate
    negbin: ClusterRate
    cluster_key: str
    clusters_from_fallback: int
    sources: Proportion
    raw_alerts: int
    episode_source: str


def _fa(sel: Sequence[ClipOutcome], counts: list[int], hours: list[float],
        raw: list[int], meta: Meta | None, cluster_key: str, source_key: str,
        n_boot: int, seed: int) -> FASummary:
    groups, fallback = [], 0
    for o in sel:
        g = _group(meta, o.clip, cluster_key)
        if g is None:
            fallback += 1
            g = _group(meta, o.clip, source_key) or o.clip
        groups.append(g)
    tot_h = sum(hours)
    n_ep = sum(counts)
    src: dict[str, bool] = {}
    for o, c in zip(sel, counts):
        s = _group(meta, o.clip, source_key) or o.clip
        src[s] = src.get(s, False) or c > 0
    kinds = {o.episode_source for o in sel}
    return FASummary(
        len(sel), tot_h, n_ep, n_ep / tot_h if tot_h else float("nan"),
        rate_ci(n_ep, tot_h),
        cluster_rate_ci(counts, hours, groups, "bootstrap", n_boot=n_boot, seed=seed),
        cluster_rate_ci(counts, hours, groups, "negbin"), cluster_key, fallback,
        proportion(sum(src.values()), len(src)), sum(raw),
        kinds.pop() if len(kinds) == 1 else ("mixed" if kinds else "none"))


def fa_summary(outcomes: Sequence[ClipOutcome], meta: Meta | None = None,
               cluster_key: str = "camera_vat_ly", source_key: str = "nhom_nguon",
               n_boot: int = 4000, seed: int = 42) -> FASummary:
    """False-alarm episodes on negative files (``rac`` and ``sau_chay`` out).

    Parameters
    ----------
    outcomes : sequence of ClipOutcome
        Outcomes of one model; positive files are ignored here (see
        :func:`prefire_summary`).
    meta : mapping, optional
        ``file -> {column: value}``. Clips without ``cluster_key`` fall back
        to ``source_key`` then to the file itself (counted in
        ``clusters_from_fallback``).
    """
    sel = [o for o in outcomes if not o.positive]
    return _fa(sel, [len(o.fa_onsets) for o in sel], [o.background_h for o in sel],
               [len(o.fa_alerts) for o in sel], meta, cluster_key, source_key,
               n_boot, seed)


def prefire_summary(outcomes: Sequence[ClipOutcome], meta: Meta | None = None,
                    cluster_key: str = "camera_vat_ly",
                    source_key: str = "nhom_nguon", n_boot: int = 4000,
                    seed: int = 42) -> FASummary:
    """"FA trước sự cố": episodes on the pre-fire part of positive files.

    The pre-fire part is ``[0, first t_start - early_s)`` minus ``rac`` and
    ``sau_chay``; its length is the exposure.
    """
    sel = [o for o in outcomes if o.positive and o.prefire_s > 0]
    return _fa(sel, [len(o.prefire_onsets) for o in sel],
               [o.prefire_h for o in sel], [len(o.prefire_alerts) for o in sel],
               meta, cluster_key, source_key, n_boot, seed)


def fa_by_stratum(outcomes: Sequence[ClipOutcome], meta: Meta | None,
                  key: str = "loai_am", **kw: Any) -> dict[str, FASummary]:
    """:func:`fa_summary` per value of a metadata column (``bt`` / ``dn``)."""
    strata: dict[str, list[ClipOutcome]] = {}
    for o in outcomes:
        if not o.positive:
            strata.setdefault(_group(meta, o.clip, key) or NO_GROUP, []).append(o)
    return {k: fa_summary(v, meta, **kw) for k, v in sorted(strata.items())}


@dataclass(frozen=True, slots=True)
class TTDCommon:
    """TTD on the incidents every listed model caught (``t_start`` >= min)."""

    models: tuple[str, ...]
    keys: list[tuple[str, int]]
    ttd: dict[str, list[float]]
    median: dict[str, float]

    @property
    def n(self) -> int:
        return len(self.keys)


def ttd_common(outcomes_by_model: Mapping[str, Sequence[ClipOutcome]],
               cfg: ScoringConfig = ScoringConfig(),
               models: Sequence[str] | None = None) -> TTDCommon:
    """Time-to-detect on the intersection of caught incidents (M-5).

    Parameters
    ----------
    outcomes_by_model : mapping
        Model -> outcomes on the same files.
    cfg : ScoringConfig
        ``main_tolerance_s`` and ``min_ttd_start_s`` are used.
    models : sequence of str, optional
        Models to intersect (default: all); two for a pairwise comparison.
    """
    names = tuple(models or outcomes_by_model)
    per: dict[str, dict[tuple[str, int], float | None]] = {}
    for m in names:
        per[m] = {inc.key: inc.ttd() for o in outcomes_by_model[m]
                  for inc in o.incidents if inc.t_start >= cfg.min_ttd_start_s}
    keys = sorted(set.intersection(*(set(k for k, v in per[m].items()
                                         if v is not None) for m in names))
                  ) if names else []
    ttd = {m: [float(per[m][k]) for k in keys] for m in names}
    med = {m: statistics.median(v) if v else float("nan") for m, v in ttd.items()}
    return TTDCommon(names, keys, ttd, med)


@dataclass(frozen=True, slots=True)
class CensoredTTD:
    """TTD distribution with missed incidents censored at window end."""

    n: int
    detected: int
    censored: int
    quantiles: dict[float, float]
    times: list[float]
    observed: list[bool]


def ttd_censored(outcomes: Sequence[ClipOutcome],
                 cfg: ScoringConfig = ScoringConfig(),
                 quantiles: Sequence[float] = (0.25, 0.5, 0.75)) -> CensoredTTD:
    """Kaplan-Meier quantiles of TTD (``t_start >= min_ttd_start_s``).

    A missed incident is censored at ``window_end_s - t_start``; a quantile
    the curve never reaches is ``nan`` ("không đạt").
    """
    times, obs = [], []
    for o in outcomes:
        for inc in o.incidents:
            if inc.t_start < cfg.min_ttd_start_s:
                continue
            t = inc.ttd()
            times.append(t if t is not None else inc.window_end_s - inc.t_start)
            obs.append(t is not None)
    qs = {q: km_quantile(times, obs, q) for q in quantiles}
    return CensoredTTD(len(times), sum(obs), len(obs) - sum(obs), qs, times, obs)


def km_curve(c: CensoredTTD) -> list[tuple[float, float, int, int]]:
    """Kaplan-Meier rows ``(t, S(t), at_risk, events)`` of :func:`ttd_censored`."""
    return kaplan_meier(c.times, c.observed)


def review_list(outcomes_by_model: Mapping[str, Sequence[ClipOutcome]]
                ) -> list[dict[str, Any]]:
    """Rows for the eye review: catches before ``t_start`` and signals that
    fell into ``sau_chay`` or ``rac`` (dropped)."""
    rows: list[dict[str, Any]] = []
    for model, outs in outcomes_by_model.items():
        for o in outs:
            for inc in o.incidents:
                if inc.early_hit:
                    s = inc.first[inc.main_tolerance_s]
                    rows.append({"model": model, "clip": o.clip, "su_co": inc.index,
                                 "t_start": inc.t_start, "ts": s.ts, "kind": s.kind,
                                 "ly_do": "som_truoc_moc"})
            for reason, lst in (("trong_sau_chay", o.dropped_sau_chay),
                                ("trong_rac", o.dropped_rac)):
                for s in lst:
                    rows.append({"model": model, "clip": o.clip, "su_co": "",
                                 "t_start": "", "ts": s.ts, "kind": s.kind,
                                 "ly_do": reason})
    return rows
