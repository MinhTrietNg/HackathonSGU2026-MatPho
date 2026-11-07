"""Human-in-the-loop: ack store, escalation rule, mute of STILL_BURNING, API."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from firewatch.acks import AckStore, EscalationWatcher, due_escalations
from firewatch.alerts import EventStore, sample_event
from firewatch.config import Config, VotingConfig
from firewatch.detector import Detection
from firewatch.server import create_app
from firewatch.voting import VotingEngine


# ------------------------------------------------------------------ store
def test_ack_store_persists_latest_decision_and_notifies(tmp_path: Path):
    path = tmp_path / "acks.json"
    store = AckStore(path)
    seen = []
    store.subscribe(seen.append)
    store.set("e1", "watch")
    store.set("e1", "dismiss_controlled", "bếp than quán nướng")
    assert store.get("e1").action == "dismiss_controlled"
    assert [a.action for a in seen] == ["watch", "dismiss_controlled"]
    again = AckStore(path)                          # nạp lại từ đĩa
    assert again.get("e1").note == "bếp than quán nướng"
    assert json.loads(path.read_text(encoding="utf-8"))["e1"]["action"] == \
        "dismiss_controlled"


# ------------------------------------------------------------- escalation
def test_due_escalations_rule():
    created = {"a": 0.0, "b": 50.0}
    assert due_escalations(created, {}, set(), 119.0, 120) == []
    assert due_escalations(created, {}, set(), 120.0, 120) == ["a"]
    assert due_escalations(created, {"a": 120.0}, set(), 169.0, 120) == []
    assert due_escalations(created, {"a": 120.0}, set(), 170.0, 120) == ["b"]
    assert due_escalations(created, {"a": 120.0, "b": 170.0}, set(), 240.0,
                           120) == ["a"]
    assert due_escalations(created, {}, {"a"}, 500.0, 120) == ["b"]   # a đã ack
    assert due_escalations(created, {}, set(), 999.0, 0) == []        # tắt


class _FakeStore:
    def __init__(self):
        self.subs, self.pushed = [], []

    def subscribe(self, fn):
        self.subs.append(fn)

    def renotify(self, event_id, kind="escalated"):
        self.pushed.append((event_id, kind))


def test_watcher_repeats_until_acked(tmp_path: Path):
    now = [1000.0]
    store, acks = _FakeStore(), AckStore(tmp_path / "acks.json")
    w = EscalationWatcher(store, acks, 120, clock=lambda: now[0])
    crit = sample_event()                           # CRITICAL
    warn = sample_event().model_copy(update={"severity": "WARNING"})
    for fn in store.subs:
        fn(crit, "created")
        fn(warn, "created")
    now[0] += 119
    assert w.tick() == []
    now[0] += 1
    assert w.tick() == [crit.event_id]              # WARNING không bị nhắc
    now[0] += 60
    assert w.tick() == []
    now[0] += 60
    assert w.tick() == [crit.event_id]              # nhắc lại mỗi chu kỳ
    acks.set(crit.event_id, "watch")                # bất kỳ hành động nào cũng dừng
    now[0] += 500
    assert w.tick() == []
    assert store.pushed == [(crit.event_id, "escalated")] * 2


# ------------------------------------------------------------------ voting
BOX = (100.0, 100.0, 200.0, 200.0)


def _feed(engine, start, n, cls="fire"):
    out = []
    for seq in range(start, start + n):
        d = Detection(cls_name=cls, cls_id=0 if cls == "fire" else 1, conf=0.8,
                      xyxy=BOX)
        out += [(e.kind, e.ts) for e in engine.update(seq, float(seq), [d]) if e.alert]
    return out


def _engine():
    return VotingEngine(VotingConfig(window_m=10, k_enter=6, k_exit=2, k_fire=2,
                                     cooldown_s=60, scene_cooldown_s=60,
                                     realert_s=60))


def test_mute_stops_still_burning_but_not_escalation():
    eng = _engine()
    assert _feed(eng, 0, 10, "smoke") == [("CONFIRMED", 5.0)]     # WARNING
    assert eng.mute(1) and not eng.mute(99)
    assert _feed(eng, 10, 60, "smoke") == []                     # không nhắc 65 s
    alerts = _feed(eng, 70, 10, "fire")                          # lửa -> CRITICAL
    assert alerts == [("ESCALATED", 71.0)]                       # leo thang vẫn báo
    assert eng.tracks[0].muted is False                          # và reset ack
    assert _feed(eng, 80, 60, "fire") == [("STILL_BURNING", 131.0)]  # nhắc lại


def test_watch_does_not_mute_in_pipeline_terms():
    from firewatch.acks import MUTING_ACTIONS
    assert MUTING_ACTIONS == {"confirm", "dismiss_controlled"}


# --------------------------------------------------------------------- API
def test_ack_api_and_console(tmp_path: Path):
    cfg = Config(alerts={"events_dir": str(tmp_path / "events")}, root=tmp_path)
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    ev = store.create(severity="CRITICAL", verification="UNVERIFIED", video_ts=3.0,
                      detections=[], image=None)
    client = TestClient(create_app(cfg, store))
    assert client.post("/events/khong-co/ack", json={"action": "confirm"}
                       ).status_code == 404
    assert client.post(f"/events/{ev.event_id}/ack", json={"action": "chay"}
                       ).status_code == 422
    r = client.post(f"/events/{ev.event_id}/ack",
                    json={"action": "dismiss_controlled", "note": "lò nướng"})
    assert r.status_code == 200 and r.json()["action"] == "dismiss_controlled"
    got = client.get(f"/events/{ev.event_id}/ack").json()
    assert got["ack"]["note"] == "lò nướng"
    assert ev.event_id in client.get("/acks").json()
    page = client.get("/console")
    assert page.status_code == 200 and "Console người trực" in page.text
    assert (tmp_path / "events" / "acks.json").is_file()
    # schema event không đổi: ack không nằm trong event
    assert "ack" not in client.get(f"/events/{ev.event_id}").json()
