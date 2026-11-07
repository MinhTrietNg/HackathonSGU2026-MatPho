"""Tier 3 — persistence voting: k-of-M state machine per fire/smoke region.

Each heartbeat a region ("track") receives one vote when at least one
fire/smoke detection matches it. A track is confirmed when it has at least
``k_enter`` votes in the last ``window_m`` heartbeats and leaves the
confirmed state when votes drop below ``k_exit`` (hysteresis). The engine
also decides whether a transition deserves an alert, applying the per-track
cooldown, so this whole tier is pure logic and unit-testable without a model.

States:  (IDLE) → CANDIDATE → CONFIRMED → COOLDOWN → (IDLE)
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .config import VotingConfig
from .detector import Detection

log = logging.getLogger(__name__)

ALERT_CLASSES = ("fire", "smoke")
Box = tuple[float, float, float, float]

TransitionObserver = Callable[["VotingEngine", list["TrackEvent"]], None]
_TRANSITION_OBSERVERS: list[TransitionObserver] = []


def add_transition_observer(fn: TransitionObserver) -> None:
    """Register a read-only callback that sees every ``update`` result.

    Used by offline scoring to record transitions that raised no alert
    (e.g. a CONFIRMED silenced by a cooldown). The callback receives the
    engine and the list of events of one heartbeat and must not change
    them. With no observer registered the engine behaves exactly as before.
    Not thread-safe: register only around a single-threaded evaluation run.
    """
    _TRANSITION_OBSERVERS.append(fn)


def remove_transition_observer(fn: TransitionObserver) -> None:
    """Unregister a callback added by :func:`add_transition_observer`."""
    if fn in _TRANSITION_OBSERVERS:
        _TRANSITION_OBSERVERS.remove(fn)


class TrackState(str, Enum):
    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"
    COOLDOWN = "COOLDOWN"


class Severity(str, Enum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return 1 if self is Severity.WARNING else 2


def iou(a: Box, b: Box) -> float:
    """Intersection over union of two ``(x1, y1, x2, y2)`` boxes."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def center_inside(a: Box, b: Box) -> bool:
    """True when the centre of ``a`` lies in ``b`` or vice versa."""
    for inner, outer in ((a, b), (b, a)):
        cx, cy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2
        if outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]:
            return True
    return False


def union(a: Box, b: Box) -> Box:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


@dataclass(slots=True)
class Vote:
    """Detections that matched a track at one heartbeat."""

    seq: int
    ts: float
    detections: list[Detection]
    frame: Any = None
    """The :class:`~firewatch.sources.Frame` of that heartbeat (``None`` in tests)."""

    @property
    def best(self) -> Detection:
        return max(self.detections, key=lambda d: d.conf)


@dataclass
class Track:
    """One fire/smoke region followed across heartbeats."""

    track_id: int
    created_seq: int
    created_ts: float
    box: Box
    window: deque[Vote | None]
    state: TrackState = TrackState.CANDIDATE
    misses: int = 0
    last_ts: float = 0.0
    confirmed_ts: float | None = None
    cooldown_since: float | None = None
    last_alert_ts: float | None = None
    last_alert_severity: Severity | None = None
    pending_alert: bool = False
    """Confirmed but silenced by the scene cooldown; alert when it lifts."""
    muted: bool = False
    """An operator acknowledged an alert of this track (confirm / dismiss):
    STILL_BURNING reminders stop. Escalation or re-ignition clears it."""

    @property
    def votes(self) -> int:
        return sum(1 for v in self.window if v is not None)

    def iter_votes(self):
        return (v for v in self.window if v is not None)

    k_fire: int = 1
    """Set by the engine from config: fire votes needed for CRITICAL."""

    @property
    def fire_votes(self) -> int:
        return sum(1 for v in self.iter_votes()
                   if any(d.cls_name == "fire" for d in v.detections))

    @property
    def severity(self) -> Severity:
        """CRITICAL only when ≥ ``k_fire`` heartbeats in the window saw fire,
        so a single spurious fire box cannot escalate a smoke track."""
        return Severity.CRITICAL if self.fire_votes >= self.k_fire else Severity.WARNING

    @property
    def best_vote(self) -> Vote | None:
        votes = list(self.iter_votes())
        return max(votes, key=lambda v: v.best.conf) if votes else None

    @property
    def latest_vote(self) -> Vote | None:
        for v in reversed(self.window):
            if v is not None:
                return v
        return None


@dataclass(slots=True)
class TrackEvent:
    """A state transition (or new track) produced by one ``update`` call."""

    kind: str
    """NEW | CONFIRMED | RECONFIRMED | ESCALATED | DEFERRED | STILL_BURNING |
    ENDED | EXPIRED"""
    track: Track
    seq: int
    ts: float
    severity: Severity
    alert: bool = False
    """True when the engine wants an alert emitted for this transition."""


class VotingEngine:
    """k-of-M voting over tracks; see module docstring."""

    def __init__(self, cfg: VotingConfig):
        self.cfg = cfg
        self.tracks: list[Track] = []
        self._next_id = 1
        self.last_scene_alert_ts: float | None = None
        self.last_scene_severity: Severity | None = None

    # ---------------------------------------------------------------- matching
    def _score(self, track: Track, det: Detection) -> float:
        s = iou(track.box, det.xyxy)
        if s >= self.cfg.iou_match:
            return s
        if center_inside(track.box, det.xyxy):
            return max(s, 1e-3)
        return 0.0

    def _assign(self, detections: list[Detection]) -> dict[int, list[Detection]]:
        """Greedy assignment, strongest detections first. New tracks are
        created on the fly so overlapping fire+smoke boxes of one event
        land in the same track."""
        assigned: dict[int, list[Detection]] = {}
        for det in sorted(detections, key=lambda d: d.conf, reverse=True):
            best_t, best_s = None, 0.0
            for t in self.tracks:
                s = self._score(t, det)
                if s > best_s:
                    best_t, best_s = t, s
            if best_t is None:
                best_t = Track(self._next_id, -1, 0.0, det.xyxy,
                               deque(maxlen=self.cfg.window_m), k_fire=self.cfg.k_fire)
                self._next_id += 1
                self.tracks.append(best_t)
            assigned.setdefault(best_t.track_id, []).append(det)
        return assigned

    # ------------------------------------------------------------------ update
    def update(self, seq: int, ts: float, detections: list[Detection],
               frame: Any = None) -> list[TrackEvent]:
        """Feed one heartbeat and return the transitions it caused.

        Parameters
        ----------
        seq, ts : int, float
            Heartbeat sequence number and video timestamp (seconds).
        detections : list of Detection
            All detections of the heartbeat; non fire/smoke classes are ignored.
        frame : Any, optional
            Heartbeat frame, stored on the vote so alerts can use it as keyframe.
        """
        cfg = self.cfg
        events: list[TrackEvent] = []
        alert_dets = [d for d in detections if d.cls_name in ALERT_CLASSES]
        before = {t.track_id for t in self.tracks}
        assigned = self._assign(alert_dets)

        for t in self.tracks:
            dets = assigned.get(t.track_id)
            if dets:
                box = dets[0].xyxy
                for d in dets[1:]:
                    box = union(box, d.xyxy)
                if t.track_id in before:
                    # Làm mượt: nửa hộp cũ, nửa hộp mới -> theo kịp lửa lan.
                    t.box = tuple((o + n) / 2 for o, n in zip(t.box, box))
                else:
                    t.box = box
                    t.created_seq, t.created_ts = seq, ts
                    events.append(TrackEvent("NEW", t, seq, ts, Severity.WARNING))
                t.window.append(Vote(seq, ts, dets, frame))
                t.misses = 0
            else:
                t.window.append(None)
                t.misses += 1
            t.last_ts = ts

        for t in list(self.tracks):
            ev = self._transition(t, seq, ts)
            if ev is not None:
                events.append(ev)
        for ev in events:
            if ev.kind != "NEW":
                log.info("[video %7.2fs] track#%d %s votes %d/%d sev %s alert=%s",
                         ts, ev.track.track_id, ev.kind, ev.track.votes, cfg.window_m,
                         ev.severity.value, ev.alert)
        for fn in tuple(_TRANSITION_OBSERVERS):
            fn(self, events)
        return events

    def _transition(self, t: Track, seq: int, ts: float) -> TrackEvent | None:
        cfg = self.cfg
        votes, sev = t.votes, t.severity
        if t.state is TrackState.CANDIDATE:
            if votes >= cfg.k_enter:
                t.state, t.confirmed_ts = TrackState.CONFIRMED, ts
                return TrackEvent("CONFIRMED", t, seq, ts, sev, self._alert(t, sev, ts))
            if t.misses >= cfg.max_misses:
                self.tracks.remove(t)
                return TrackEvent("EXPIRED", t, seq, ts, sev)
        elif t.state is TrackState.CONFIRMED:
            if votes < cfg.k_exit:
                t.state, t.cooldown_since = TrackState.COOLDOWN, ts
                t.pending_alert = False
                return TrackEvent("ENDED", t, seq, ts, sev)
            if (t.last_alert_severity is not None
                    and sev.rank > t.last_alert_severity.rank):
                t.muted = False                # leo thang: người trực phải xem lại
                return TrackEvent("ESCALATED", t, seq, ts, sev, self._alert(t, sev, ts))
            if t.pending_alert:
                # Bị cooldown cảnh chặn lúc xác nhận: báo ngay khi cửa sổ mở lại.
                if self._alert(t, sev, ts):
                    return TrackEvent("DEFERRED", t, seq, ts, sev, True)
            elif (cfg.realert_s > 0 and not t.muted and t.last_alert_ts is not None
                    and ts - t.last_alert_ts >= cfg.realert_s
                    and self._alert(t, sev, ts)):
                return TrackEvent("STILL_BURNING", t, seq, ts, sev, True)
        elif t.state is TrackState.COOLDOWN:
            if votes >= cfg.k_enter:
                t.state, t.confirmed_ts = TrackState.CONFIRMED, ts
                t.muted = False                # cháy lại sau khi tắt: báo lại từ đầu
                return TrackEvent("RECONFIRMED", t, seq, ts, sev,
                                  self._alert(t, sev, ts))
            idle_for = ts - (t.cooldown_since or ts)
            if t.misses >= cfg.max_misses and idle_for >= cfg.cooldown_s:
                self.tracks.remove(t)
                return TrackEvent("EXPIRED", t, seq, ts, sev)
        return None

    def _alert(self, t: Track, sev: Severity, ts: float) -> bool:
        """Apply per-track and per-scene cooldown; escalation always alerts."""
        track_ok = (t.last_alert_ts is None
                    or ts - t.last_alert_ts >= self.cfg.cooldown_s
                    or (t.last_alert_severity is not None
                        and sev.rank > t.last_alert_severity.rank))
        scene_ok = (self.last_scene_alert_ts is None
                    or self.cfg.scene_cooldown_s <= 0
                    or ts - self.last_scene_alert_ts >= self.cfg.scene_cooldown_s
                    or (self.last_scene_severity is not None
                        and sev.rank > self.last_scene_severity.rank))
        ok = track_ok and scene_ok
        if ok:
            t.last_alert_ts, t.last_alert_severity = ts, sev
            self.last_scene_alert_ts, self.last_scene_severity = ts, sev
            t.pending_alert = False
        elif track_ok:
            # Track đủ điều kiện nhưng cảnh vừa báo: KHÔNG ghi last_alert_ts (sẽ
            # làm track câm vĩnh viễn); giữ cờ chờ để báo khi cooldown cảnh hết.
            t.pending_alert = True
        return ok

    def mute(self, track_id: int) -> bool:
        """Stop STILL_BURNING reminders of a track after an operator ack.

        Escalation and re-confirmation still alert and clear the flag; the
        machine itself never silences a first alert. Returns False when the
        track no longer exists.
        """
        for t in self.tracks:
            if t.track_id == track_id:
                t.muted = True
                return True
        return False

    # ----------------------------------------------------------------- queries
    @property
    def confirmed(self) -> list[Track]:
        return [t for t in self.tracks if t.state is TrackState.CONFIRMED]
