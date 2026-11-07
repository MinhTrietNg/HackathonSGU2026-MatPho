"""k-of-M voting state machine — pure logic, no model, no video."""

from firewatch.config import VotingConfig
from firewatch.detector import Detection
from firewatch.voting import Severity, TrackState, VotingEngine, iou

BOX = (100.0, 100.0, 200.0, 200.0)


def det(cls="fire", conf=0.8, box=BOX):
    return Detection(cls_name=cls, cls_id=0 if cls == "fire" else 1, conf=conf,
                     xyxy=box)


def cfg(**kw):
    base = dict(window_m=10, k_enter=6, k_exit=2, k_fire=2, iou_match=0.3,
                max_misses=10, cooldown_s=60, scene_cooldown_s=60)
    base.update(kw)
    return VotingConfig(**base)


def run(engine, pattern, cls="fire"):
    """Feed one heartbeat per character: 'x' = detection, '.' = nothing."""
    out = []
    for seq, ch in enumerate(pattern):
        dets = [det(cls)] if ch == "x" else []
        out.extend(engine.update(seq, float(seq), dets))
    return out


def kinds(events):
    return [e.kind for e in events if e.kind != "NEW"]


def test_confirm_after_k_votes_in_window():
    eng = VotingEngine(cfg())
    ev = run(eng, "xxxxxx")
    assert kinds(ev) == ["CONFIRMED"]
    assert ev[-1].ts == 5.0 and ev[-1].alert is True
    assert ev[-1].severity is Severity.CRITICAL


def test_smoke_only_is_warning_and_fire_escalates_after_k_fire_votes():
    eng = VotingEngine(cfg(k_fire=2))
    ev = run(eng, "xxxxxx", cls="smoke")
    assert ev[-1].kind == "CONFIRMED" and ev[-1].severity is Severity.WARNING
    # Một heartbeat có box lửa (nhiễu) chưa đủ: vẫn WARNING, không ESCALATED.
    ev2 = eng.update(6, 6.0, [det("smoke"), det("fire", 0.3)])
    assert kinds(ev2) == [] and eng.tracks[0].severity is Severity.WARNING
    # Heartbeat thứ hai có lửa -> đủ k_fire=2 -> ESCALATED CRITICAL, alert.
    ev3 = eng.update(7, 7.0, [det("smoke"), det("fire", 0.4)])
    assert kinds(ev3) == ["ESCALATED"] and ev3[0].alert is True
    assert ev3[0].severity is Severity.CRITICAL


def test_single_fire_vote_in_confirm_window_stays_warning():
    eng = VotingEngine(cfg(k_fire=2))
    seqs = ["smoke"] * 5 + ["fire"]
    ev = []
    for seq, cls in enumerate(seqs):
        ev += eng.update(seq, float(seq), [det(cls)])
    confirmed = [e for e in ev if e.kind == "CONFIRMED"]
    assert confirmed and confirmed[0].severity is Severity.WARNING


def test_config_rejects_inconsistent_thresholds():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        VotingConfig(window_m=10, k_enter=6, k_exit=0)
    with pytest.raises(ValidationError):
        VotingConfig(window_m=10, k_enter=6, k_exit=7)
    with pytest.raises(ValidationError):
        VotingConfig(window_m=5, k_enter=6, k_exit=2)
    with pytest.raises(ValidationError):
        VotingConfig(window_m=10, k_enter=6, k_exit=2, k_fire=7)
    assert VotingConfig(window_m=10, k_enter=6, k_exit=6).k_exit == 6


def test_one_frame_noise_never_confirms():
    eng = VotingEngine(cfg())
    ev = run(eng, "x.x.x.x.x.x.x.x.x.x.")
    assert "CONFIRMED" not in kinds(ev)


def test_intermittent_fire_still_confirms_k_of_m():
    eng = VotingEngine(cfg())
    ev = run(eng, "xx.xx.xx")  # 6 votes trong 8 heartbeat
    assert kinds(ev) == ["CONFIRMED"]


def test_hysteresis_exit_then_cooldown_suppresses_realert():
    eng = VotingEngine(cfg(cooldown_s=60))
    ev = run(eng, "xxxxxx" + "." * 9)
    # 6 phiếu -> CONFIRMED; sau 9 lần trống còn 0 phiếu -> ENDED (k_exit=2)
    assert kinds(ev) == ["CONFIRMED", "ENDED"]
    track = eng.tracks[0]
    assert track.state is TrackState.COOLDOWN
    # Cháy lại ngay (trong 60 s): RECONFIRMED nhưng KHÔNG alert
    ev2 = run_from(eng, 15, "xxxxxx")
    assert kinds(ev2) == ["RECONFIRMED"] and ev2[-1].alert is False


def test_realert_after_cooldown_elapsed():
    eng = VotingEngine(cfg(cooldown_s=5, scene_cooldown_s=5))
    ev = run(eng, "xxxxxx" + "." * 9)
    assert kinds(ev) == ["CONFIRMED", "ENDED"]
    ev2 = run_from(eng, 15, "xxxxxx")  # ts 15..20, cách alert đầu (5.0) > 5 s
    assert kinds(ev2) == ["RECONFIRMED"] and ev2[-1].alert is True


def test_long_steady_fire_realerts_every_realert_s():
    eng = VotingEngine(cfg(realert_s=60))
    ev = run(eng, "x" * 130)
    alerts = [(e.kind, e.ts) for e in ev if e.alert]
    assert alerts == [("CONFIRMED", 5.0), ("STILL_BURNING", 65.0),
                      ("STILL_BURNING", 125.0)]


def test_realert_disabled_gives_exactly_one_alert():
    eng = VotingEngine(cfg(realert_s=0))
    ev = run(eng, "x" * 120)
    alerts = [e for e in ev if e.alert]
    assert len(alerts) == 1 and alerts[0].kind == "CONFIRMED"


def test_second_fire_blocked_by_scene_cooldown_alerts_when_it_lifts():
    """Track A báo lúc 5 s; track B xác nhận lúc 25 s bị cooldown cảnh chặn,
    nhưng phải được báo ngay khi cửa sổ 60 s hết (65 s), không câm vĩnh viễn."""
    eng = VotingEngine(cfg(realert_s=0))
    far = (900.0, 100.0, 1000.0, 200.0)
    alerts = []
    for seq in range(80):
        dets = [det("fire")] if seq < 10 else []
        if seq >= 20:
            dets.append(det("fire", box=far))
        alerts += [(e.kind, e.track.track_id, e.ts)
                   for e in eng.update(seq, float(seq), dets) if e.alert]
    assert alerts == [("CONFIRMED", 1, 5.0), ("DEFERRED", 2, 65.0)]
    track_b = next(t for t in eng.tracks if t.track_id == 2)
    assert track_b.pending_alert is False and track_b.last_alert_ts == 65.0


def test_candidate_expires_after_max_misses():
    eng = VotingEngine(cfg(max_misses=3))
    ev = run(eng, "x...")
    assert kinds(ev) == ["EXPIRED"] and eng.tracks == []


def test_two_regions_make_two_tracks_and_overlap_merges():
    eng = VotingEngine(cfg())
    far = (500.0, 500.0, 600.0, 600.0)
    near = (120.0, 120.0, 210.0, 210.0)  # chồng lên BOX
    eng.update(0, 0.0, [det("fire"), det("smoke", box=near), det("fire", box=far)])
    assert len(eng.tracks) == 2


def test_non_alert_classes_are_ignored():
    eng = VotingEngine(cfg())
    ev = run(eng, "xxxxxxxx", cls="car")
    assert ev == [] and eng.tracks == []


def test_big_fire_split_into_many_boxes_gives_one_alert():
    """Một đám cháy lớn tách thành 3 vùng box rời nhau -> 3 track nhưng 1 alert."""
    eng = VotingEngine(cfg())
    boxes = [BOX, (400.0, 100.0, 500.0, 200.0), (700.0, 100.0, 800.0, 200.0)]
    alerts = []
    for seq in range(12):
        dets = [det("fire", box=b) for b in boxes]
        alerts += [e for e in eng.update(seq, float(seq), dets) if e.alert]
    assert len(eng.tracks) == 3
    assert len(alerts) == 1


def test_scene_cooldown_still_lets_critical_escalate():
    eng = VotingEngine(cfg())
    far = (400.0, 100.0, 500.0, 200.0)
    alerts = []
    for seq in range(6):                      # vùng 1 khói -> WARNING
        alerts += [e for e in eng.update(seq, float(seq), [det("smoke")]) if e.alert]
    assert [a.severity for a in alerts] == [Severity.WARNING]
    for seq in range(6, 12):                  # vùng 2 lửa -> CRITICAL dù đang cooldown
        dets = [det("smoke"), det("fire", box=far)]
        alerts += [e for e in eng.update(seq, float(seq), dets) if e.alert]
    assert [a.severity for a in alerts] == [Severity.WARNING, Severity.CRITICAL]


def test_scene_cooldown_disabled_alerts_every_track():
    eng = VotingEngine(cfg(scene_cooldown_s=0))
    far = (400.0, 100.0, 500.0, 200.0)
    alerts = []
    for seq in range(6):
        dets = [det("fire"), det("fire", box=far)]
        alerts += [e for e in eng.update(seq, float(seq), dets) if e.alert]
    assert len(alerts) == 2


def test_iou():
    assert iou(BOX, BOX) == 1.0
    assert iou(BOX, (150, 150, 250, 250)) == 2500 / (20000 - 2500)
    assert iou(BOX, (300, 300, 400, 400)) == 0.0


def run_from(engine, start_seq, pattern, cls="fire"):
    out = []
    for i, ch in enumerate(pattern):
        seq = start_seq + i
        dets = [det(cls)] if ch == "x" else []
        out.extend(engine.update(seq, float(seq), dets))
    return out
