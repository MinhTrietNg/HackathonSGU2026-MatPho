"""Operator acknowledgements (human-in-the-loop) and CRITICAL escalation.

An operator answers an alert from the console with one of three actions:

* ``confirm``            — real incident, being handled;
* ``dismiss_controlled`` — controlled fire (charcoal grill, cooking, burning in
  a container), nothing to do;
* ``watch``              — keep watching, no decision yet.

Acks live in their own JSON file next to the events (``acks.json``): the
event schema agreed with the backend is not touched. ``confirm`` and
``dismiss_controlled`` stop STILL_BURNING reminders of the alert's track
(:meth:`firewatch.voting.VotingEngine.mute`); escalation still alerts and
clears that. Only a human can silence the machine.

Escalation: a CRITICAL event with no ack after ``alerts.escalation_s`` seconds
is pushed again (same ``event_id``, WebSocket ``event_update`` with
``reason: escalation``, webhook POST) and again every ``escalation_s`` until
someone acks it.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .alerts import Event, EventStore

log = logging.getLogger(__name__)

AckAction = Literal["confirm", "dismiss_controlled", "watch"]
MUTING_ACTIONS: frozenset[str] = frozenset({"confirm", "dismiss_controlled"})
ACTION_VI: dict[str, str] = {"confirm": "Xác nhận sự cố",
                             "dismiss_controlled": "Bỏ qua — lửa có kiểm soát",
                             "watch": "Theo dõi"}


class Ack(BaseModel):
    """One operator decision on one event (the latest one wins)."""

    event_id: str
    action: AckAction
    note: str = Field("", max_length=500)
    acked_at: str
    """ISO-8601 wall time of the decision."""


class AckStore:
    """Thread-safe ack registry persisted to one JSON file.

    Parameters
    ----------
    path : Path
        JSON file (``{event_id: ack}``); created on first write.
    """

    def __init__(self, path: Path):
        self.path = path
        self._acks: dict[str, Ack] = {}
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[Ack], None]] = []
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self._acks = {k: Ack(**v) for k, v in raw.items()}
                log.info("nạp %d ack từ %s", len(self._acks), path)
            except Exception as exc:  # noqa: BLE001
                log.warning("bỏ qua file ack hỏng %s: %s", path, exc)

    def subscribe(self, fn: Callable[[Ack], None]) -> None:
        self._subscribers.append(fn)

    def unsubscribe(self, fn: Callable[[Ack], None]) -> None:
        if fn in self._subscribers:
            self._subscribers.remove(fn)

    def get(self, event_id: str) -> Ack | None:
        with self._lock:
            return self._acks.get(event_id)

    def all(self) -> dict[str, Ack]:
        with self._lock:
            return dict(self._acks)

    def acked_ids(self) -> set[str]:
        with self._lock:
            return set(self._acks)

    def set(self, event_id: str, action: AckAction, note: str = "",
            now: datetime | None = None) -> Ack:
        """Record (or replace) the decision for ``event_id`` and notify."""
        when = now or datetime.now(timezone.utc).astimezone()
        ack = Ack(event_id=event_id, action=action, note=note,
                  acked_at=when.isoformat(timespec="seconds"))
        with self._lock:
            self._acks[event_id] = ack
            data = {k: v.model_dump() for k, v in self._acks.items()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(self.path)
        log.info("ACK %s: %s%s", event_id[:8], ACTION_VI[action],
                 f" — {note}" if note else "")
        for fn in list(self._subscribers):
            try:
                fn(ack)
            except Exception as exc:  # noqa: BLE001
                log.warning("subscriber ack lỗi: %s", exc)
        return ack


def due_escalations(created: dict[str, float], last_sent: dict[str, float],
                    acked: set[str], now: float, escalation_s: float) -> list[str]:
    """CRITICAL events to push again now (pure logic, wall-clock seconds).

    Parameters
    ----------
    created : dict
        ``event_id -> time the CRITICAL event was first sent``.
    last_sent : dict
        ``event_id -> time of the last escalation`` (absent: never escalated).
    acked : set of str
        Events an operator has answered (any action stops escalation).
    now, escalation_s : float
        Current time and period; ``escalation_s <= 0`` disables escalation.

    Returns
    -------
    list of str
        Event ids whose last push is at least ``escalation_s`` old.
    """
    if escalation_s <= 0:
        return []
    return [eid for eid, t0 in created.items()
            if eid not in acked and now - last_sent.get(eid, t0) >= escalation_s]


class EscalationWatcher:
    """Re-push unacked CRITICAL events every ``escalation_s`` seconds.

    Subscribes to the event store for new CRITICAL events and runs a small
    daemon thread; :meth:`tick` does one pass and is what tests call with a
    fake clock.
    """

    def __init__(self, store: EventStore, acks: AckStore, escalation_s: float,
                 clock: Callable[[], float] = time.time, period_s: float = 1.0):
        self.store, self.acks = store, acks
        self.escalation_s, self.clock, self.period_s = escalation_s, clock, period_s
        self._created: dict[str, float] = {}
        self._last_sent: dict[str, float] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        store.subscribe(self._on_event)

    def _on_event(self, event: Event, kind: str) -> None:
        # ``updated`` cũng tính: với gom sự cố (cờ verifier.ben_vung) một sự cố
        # mở ở WARNING lên CRITICAL qua updated cùng event_id. Cờ tắt thì
        # updated không đổi mức, nên hành vi cũ giữ nguyên.
        if (kind in ("created", "updated", "su_co")
                and event.severity == "CRITICAL"):
            with self._lock:
                self._created.setdefault(event.event_id, self.clock())

    def tick(self) -> list[str]:
        """Escalate everything that is due; returns the escalated ids."""
        now = self.clock()
        acked = self.acks.acked_ids()
        with self._lock:
            for eid in [e for e in self._created if e in acked]:
                self._created.pop(eid)          # đã có người trả lời: thôi theo dõi
                self._last_sent.pop(eid, None)
            due = due_escalations(self._created, self._last_sent, acked, now,
                                  self.escalation_s)
            for eid in due:
                self._last_sent[eid] = now
        for eid in due:
            log.warning("ESCALATION: event CRITICAL %s chưa ai xác nhận sau %.0fs, "
                        "gửi lại", eid[:8], self.escalation_s)
            self.store.renotify(eid, "escalated")
        return due

    def start(self) -> None:
        if self.escalation_s <= 0:
            log.info("escalation tắt (alerts.escalation_s = 0)")
            return
        threading.Thread(target=self._loop, name="escalation", daemon=True).start()
        log.info("escalation bật: CRITICAL chưa ack sau %.0fs sẽ được gửi lại",
                 self.escalation_s)

    def _loop(self) -> None:
        while not self._stop.wait(self.period_s):
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 - không để thread chết
                log.warning("escalation lỗi: %s", exc)

    def stop(self) -> None:
        self._stop.set()
