"""Labels, per-clip runs and their JSON / CSV I/O for protocol v2.

* :class:`ClipLabel` -- one file's label, schema ``t1_dev_v1.1`` (``events``
  with ``t_start``, ``t_end``, ``t_khoi``, ``t_lua``, ``tin_cay``; ``sau_chay``,
  ``rac``); older JSON without the new keys is accepted.
* :class:`ClipRun` -- what one model produced on one file (alerts with their
  kind, every voting transition when recorded) plus the label.
* ``dump_run`` / ``runs_from_dump`` / ``load_runs`` -- ``events_alerts.json``
  with the v1 keys kept and the v2 keys added.
* ``load_file_meta`` -- ``files.csv`` / ``clips_meta.csv`` as a plain mapping
  ``file -> {column: value}``.

Scoring lives in :mod:`firewatch.eventmetrics`.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .episodes import LEGACY_KIND, Transition
from .evalkit import ClipResult, GTEvent

Interval = tuple[float, float]


# ------------------------------------------------------------------ labels
@dataclass(slots=True)
class IncidentLabel:
    """One labelled incident (``events[]`` of the clip JSON)."""

    t_start: float
    t_end: float | None = None
    label: str = "fire"
    t_khoi: float | None = None
    t_lua: float | None = None
    tin_cay: str | None = None


@dataclass(slots=True)
class ClipLabel:
    """Label of one file, schema ``t1_dev_v1.1`` (missing keys = empty)."""

    events: list[IncidentLabel] = field(default_factory=list)
    sau_chay: list[Interval] = field(default_factory=list)
    rac: list[Interval] = field(default_factory=list)
    schema: str | None = None
    nguon_nhan: str | None = None
    clip_id: str | None = None


def _opt_float(v: Any) -> float | None:
    return None if v is None or v == "" else float(v)


def _intervals(raw: Any) -> list[Interval]:
    out: list[Interval] = []
    for item in raw or []:
        a, b = float(item[0]), float(item[1])
        out.append((min(a, b), max(a, b)))
    return out


def parse_label(data: Mapping[str, Any]) -> ClipLabel:
    """Read a clip JSON (v1.0 or v1.1).

    ``t_start`` defaults to the earliest of ``t_khoi`` / ``t_lua`` when absent.

    Raises
    ------
    ValueError
        When an event has none of ``t_start``, ``t_khoi``, ``t_lua``.
    """
    events = []
    for e in data.get("events") or []:
        t_khoi, t_lua = _opt_float(e.get("t_khoi")), _opt_float(e.get("t_lua"))
        ts = _opt_float(e.get("t_start"))
        if ts is None:
            known = [t for t in (t_khoi, t_lua) if t is not None]
            if not known:
                raise ValueError(f"sự kiện thiếu t_start/t_khoi/t_lua: {e}")
            ts = min(known)
        events.append(IncidentLabel(ts, _opt_float(e.get("t_end")),
                                    str(e.get("label") or "fire"), t_khoi, t_lua,
                                    e.get("tin_cay")))
    return ClipLabel(events, _intervals(data.get("sau_chay")),
                     _intervals(data.get("rac")), data.get("schema"),
                     data.get("nguon_nhan"), data.get("clip_id"))


def label_to_dict(label: ClipLabel) -> dict[str, Any]:
    """Inverse of :func:`parse_label` (keys of schema v1.1)."""
    return {"schema": label.schema, "clip_id": label.clip_id,
            "events": [{"t_start": e.t_start, "t_end": e.t_end, "label": e.label,
                        "t_khoi": e.t_khoi, "t_lua": e.t_lua, "tin_cay": e.tin_cay}
                       for e in label.events],
            "sau_chay": [list(iv) for iv in label.sau_chay],
            "rac": [list(iv) for iv in label.rac], "nguon_nhan": label.nguon_nhan}


def merged_incidents(label: ClipLabel) -> list[IncidentLabel]:
    """Merge overlapping / touching events (same rule as ``merge_events``).

    ``t_khoi`` and ``t_lua`` of the merged incident are the earliest known.
    """
    out: list[IncidentLabel] = []
    for ev in sorted(label.events, key=lambda e: e.t_start):
        last = out[-1] if out else None
        if last is not None and ev.t_start <= (
                last.t_end if last.t_end is not None else float("inf")):
            last.t_end = (None if None in (last.t_end, ev.t_end)
                          else max(last.t_end, ev.t_end))
            for attr in ("t_khoi", "t_lua"):
                vals = [v for v in (getattr(last, attr), getattr(ev, attr))
                        if v is not None]
                setattr(last, attr, min(vals) if vals else None)
        else:
            out.append(IncidentLabel(ev.t_start, ev.t_end, ev.label, ev.t_khoi,
                                     ev.t_lua, ev.tin_cay))
    return out


# -------------------------------------------------------------------- runs
@dataclass(slots=True)
class ClipRun:
    """Everything one model produced on one file, plus the file's label.

    Attributes
    ----------
    clip : str
        File stem (key of the metadata mapping).
    duration_s : float
        File length.
    label : ClipLabel
    alerts : list of Transition
        Alerts emitted by the pipeline (kind ``ALERT`` for legacy data).
    transitions : list of Transition or None
        Every voting transition; ``None`` when not recorded (legacy JSON),
        in which case alerts are the only signals and false alarms are
        counted per alert.
    """

    clip: str
    duration_s: float
    label: ClipLabel
    alerts: list[Transition] = field(default_factory=list)
    transitions: list[Transition] | None = None

    @property
    def positive(self) -> bool:
        return bool(self.label.events)

    @classmethod
    def from_clip_result(cls, r: ClipResult) -> ClipRun:
        """Legacy view: only alert times are known."""
        label = ClipLabel([IncidentLabel(g.t_start, g.t_end) for g in r.gt])
        alerts = [Transition(LEGACY_KIND, float(t), alert=True) for t in r.alert_ts]
        return cls(r.clip, float(r.duration_s), label, alerts, None)

    def to_clip_result(self) -> ClipResult:
        """View for the v1 functions of :mod:`firewatch.evalkit`."""
        return ClipResult(self.clip, self.positive, self.duration_s,
                          [GTEvent(e.t_start, e.t_end) for e in self.label.events],
                          [a.ts for a in self.alerts])


def dump_run(run: ClipRun) -> dict[str, Any]:
    """Entry of ``events_alerts.json``: v1 keys kept, v2 keys added."""
    out: dict[str, Any] = {
        "positive": run.positive, "duration_s": run.duration_s,
        "gt": [[e.t_start, e.t_end] for e in run.label.events],
        "alerts": [a.ts for a in run.alerts],
        "alert_events": [a.to_dict() for a in run.alerts],
        "label": label_to_dict(run.label)}
    if run.transitions is not None:
        out["transitions"] = [t.to_dict() for t in run.transitions]
    return out


def runs_from_dump(data: Mapping[str, Any]) -> dict[str, list[ClipRun]]:
    """Clip runs per model from a parsed ``events_alerts.json`` (v1 or v2)."""
    out: dict[str, list[ClipRun]] = {}
    for model, clips in data["models"].items():
        runs = []
        for clip, v in clips.items():
            label = (parse_label(v["label"]) if "label" in v else
                     ClipLabel([IncidentLabel(float(a), _opt_float(b))
                                for a, b in v.get("gt", [])]))
            if "alert_events" in v:
                alerts = [Transition.from_dict(a) for a in v["alert_events"]]
            else:
                alerts = [Transition(LEGACY_KIND, float(t), alert=True)
                          for t in v.get("alerts", [])]
            trs = ([Transition.from_dict(t) for t in v["transitions"]]
                   if v.get("transitions") is not None else None)
            runs.append(ClipRun(clip, float(v["duration_s"]), label, alerts, trs))
        out[model] = runs
    return out


def load_runs(path: str | Path) -> dict[str, list[ClipRun]]:
    """Read ``events_alerts.json`` (old files without v2 keys are accepted)."""
    return runs_from_dump(json.loads(Path(path).read_text(encoding="utf-8")))


def load_file_meta(*paths: str | Path) -> dict[str, dict[str, str]]:
    """Merge CSV tables keyed by ``file`` (``files.csv``) or ``clip``.

    Later tables fill missing columns of earlier ones; missing files are
    skipped.
    """
    meta: dict[str, dict[str, str]] = {}
    for p in paths:
        p = Path(p)
        if not p.is_file():
            continue
        with p.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                key = row.get("file") or row.get("clip")
                if not key:
                    continue
                cur = meta.setdefault(key, {})
                for k, v in row.items():
                    if k and v not in (None, "") and not cur.get(k):
                        cur[k] = v
    return meta
