"""Voting transitions as data, and false-alarm *episodes* (protocol v2, M-1, M-3).

The pipeline keeps only the alerts that passed the cooldowns. Scoring v2 also
needs the transitions that raised no alert (a CONFIRMED silenced by the scene
cooldown) and the kind of each alert, so that

* every confirmation counts as a detection signal (M-1), and
* false alarms are counted per episode -- the first CONFIRMED of a track plus
  every RECONFIRMED after an ENDED -- instead of per alert, so STILL_BURNING
  reminders and DEFERRED alerts no longer make a long clip look worse (M-3).

:func:`record_transitions` collects the transitions of every
:class:`~firewatch.voting.VotingEngine` through the read-only observer hook of
``voting.py``; it changes nothing in the engine.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any

from .voting import (TrackEvent, VotingEngine, add_transition_observer,
                     remove_transition_observer)

CONFIRM_KINDS = ("CONFIRMED", "RECONFIRMED")
"""Transitions that start an episode (a track enters the confirmed state)."""
ALERT_KINDS = ("CONFIRMED", "RECONFIRMED", "ESCALATED", "DEFERRED", "STILL_BURNING")
"""Transitions that may carry an alert."""
END_KINDS = ("ENDED", "EXPIRED")
LEGACY_KIND = "ALERT"
"""Kind given to alerts read from an old ``events_alerts.json`` (no kind kept)."""


@dataclass(frozen=True, slots=True)
class Transition:
    """One state change of a voting track, reduced to plain data.

    Attributes
    ----------
    kind : str
        ``CONFIRMED``, ``RECONFIRMED``, ``ESCALATED``, ``DEFERRED``,
        ``STILL_BURNING``, ``ENDED``, ``EXPIRED`` or ``ALERT`` (legacy).
    ts : float
        Video timestamp in seconds.
    track_id : int
        Track of the voting engine (``-1`` when unknown).
    severity : str
        ``WARNING`` / ``CRITICAL`` (empty when unknown).
    alert : bool
        True when the engine emitted an alert for this transition.
    """

    kind: str
    ts: float
    track_id: int = -1
    severity: str = ""
    alert: bool = False

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly dict (inverse of :meth:`from_dict`)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Transition:
        """Build from a dict written by :meth:`to_dict` or a pipeline alert.

        Pipeline alert records use ``video_ts_sec`` instead of ``ts``; such
        records are alerts by definition.
        """
        ts = d["ts"] if "ts" in d else d["video_ts_sec"]
        tid = d.get("track_id")
        return cls(kind=str(d.get("kind") or LEGACY_KIND), ts=float(ts),
                   track_id=-1 if tid is None else int(tid),
                   severity=str(d.get("severity") or ""),
                   alert=bool(d.get("alert", "ts" not in d)))


def from_track_events(events: Iterable[TrackEvent]) -> list[Transition]:
    """Convert engine events (``NEW`` dropped) to :class:`Transition`."""
    return [Transition(ev.kind, float(ev.ts), ev.track.track_id,
                       ev.severity.value, bool(ev.alert))
            for ev in events if ev.kind != "NEW"]


@contextmanager
def record_transitions() -> Iterator[list[Transition]]:
    """Collect every non-``NEW`` transition of every engine while active.

    Yields
    ------
    list of Transition
        Filled in place, in the order the engine produced them.

    Examples
    --------
    >>> with record_transitions() as rec:          # doctest: +SKIP
    ...     summary = Pipeline(cfg, "clip.mp4").run()
    """
    out: list[Transition] = []

    def _observe(_engine: VotingEngine, events: list[TrackEvent]) -> None:
        out.extend(from_track_events(events))

    add_transition_observer(_observe)
    try:
        yield out
    finally:
        remove_transition_observer(_observe)


def signals(transitions: Iterable[Transition] | None,
            alerts: Iterable[Transition]) -> list[Transition]:
    """Detection signals: every confirmation plus every alert, sorted by time.

    Parameters
    ----------
    transitions : iterable of Transition or None
        All transitions of the run; ``None`` for a legacy run where only the
        alerts are known (then the alerts are the only signals).
    alerts : iterable of Transition
        Alerts emitted by the pipeline.

    Returns
    -------
    list of Transition
        Unique by ``(kind, ts, track_id)``, sorted by ``ts``.
    """
    pool: dict[tuple[str, float, int], Transition] = {}
    for t in alerts:
        pool[(t.kind, t.ts, t.track_id)] = t
    for t in transitions or ():
        if t.kind in CONFIRM_KINDS or t.alert:
            pool.setdefault((t.kind, t.ts, t.track_id), t)
    return sorted(pool.values(), key=lambda t: (t.ts, t.track_id, t.kind))


def episode_onsets(transitions: Iterable[Transition] | None,
                   alerts: Iterable[Transition] = (),
                   merge_overlapping: bool = False,
                   duration_s: float | None = None) -> list[Transition]:
    """Start of every confirmation episode of a run.

    An episode starts at the first ``CONFIRMED`` of a track or at a
    ``RECONFIRMED`` (which the engine emits only after ``ENDED``).
    ``STILL_BURNING``, ``DEFERRED`` and ``ESCALATED`` belong to the episode
    already open and are not counted, whether or not they raised an alert.

    Parameters
    ----------
    transitions : iterable of Transition or None
        All transitions of the run. ``None`` (legacy run): every alert is
        taken as an onset, which over-counts long false alarms.
    alerts : iterable of Transition
        Used only when ``transitions`` is ``None``.
    merge_overlapping : bool
        Scene variant: an onset while another track of the clip is still
        confirmed joins that episode (one fire split into several boxes).
    duration_s : float, optional
        Clip length; open confirmed intervals end there (needed only with
        ``merge_overlapping``).

    Returns
    -------
    list of Transition
        Onsets sorted by time.
    """
    if transitions is None:
        return sorted(alerts, key=lambda t: t.ts)
    trs = sorted(transitions, key=lambda t: t.ts)
    onsets = [t for t in trs if t.kind in CONFIRM_KINDS]
    if not merge_overlapping:
        return onsets
    # Gộp theo cảnh: các khoảng CONFIRMED chồng nhau (kể cả cùng giây) là một đợt.
    end_of = {(tid, a): b for a, b, tid in confirmed_spans(trs, duration_s)}
    kept: list[Transition] = []
    cur_end = float("-inf")
    for o in onsets:
        b = end_of.get((o.track_id, o.ts), float("inf"))
        if o.ts > cur_end:
            kept.append(o)
            cur_end = b
        else:
            cur_end = max(cur_end, b)
    return kept


def confirmed_spans(transitions: Iterable[Transition],
                    duration_s: float | None = None
                    ) -> list[tuple[float, float, int]]:
    """Intervals ``(start, end, track_id)`` during which a track is confirmed.

    A span opens at ``CONFIRMED`` / ``RECONFIRMED`` and closes at the next
    ``ENDED`` / ``EXPIRED`` of the same track, or at ``duration_s`` (``inf``
    when unknown).
    """
    open_at: dict[int, float] = {}
    out: list[tuple[float, float, int]] = []
    for t in sorted(transitions, key=lambda t: t.ts):
        if t.kind in CONFIRM_KINDS:
            open_at.setdefault(t.track_id, t.ts)
        elif t.kind in END_KINDS and t.track_id in open_at:
            out.append((open_at.pop(t.track_id), t.ts, t.track_id))
    end = float("inf") if duration_s is None else float(duration_s)
    out += [(a, end, tid) for tid, a in open_at.items()]
    return sorted(out)
