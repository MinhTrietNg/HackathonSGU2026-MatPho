"""Scenarios S0-S4 of the T1 audit, run through the REAL voting engine.

Synthetic box sequences (1 Hz heartbeats, no model) go through
``VotingEngine`` with the voting settings of ``config.yaml``; transitions are
recorded with the read-only observer hook. Each test scores the same run with
the v1 rules (``evalkit.clip_outcomes`` / ``score_events``) and the v2 rules
(``eventmetrics.score_clip``) and states what each gives.

File timings are synthetic but shaped like T1 files: an incident in the
middle of a clip followed by a post-fire scene (``sau_chay``), or a file
that ends at ``t_end`` (20/31 T1 files do).
"""

from __future__ import annotations

import math

from firewatch.config import VotingConfig
from firewatch.detector import Detection
from firewatch.episodes import record_transitions
from firewatch.evalkit import clip_outcomes, score_events
from firewatch.eventmetrics import (ClipLabel, ClipRun, IncidentLabel,
                                    review_list, score_clip)
from firewatch.voting import VotingEngine, _TRANSITION_OBSERVERS

VCFG = VotingConfig(window_m=10, k_enter=6, k_exit=2, k_fire=2, iou_match=0.3,
                    max_misses=10, cooldown_s=60, scene_cooldown_s=60,
                    realert_s=60)
TOL = 30.0
BOXES = [(100.0, 100.0, 200.0, 200.0), (400.0, 100.0, 500.0, 200.0),
         (100.0, 400.0, 200.0, 500.0), (400.0, 400.0, 500.0, 500.0),
         (700.0, 100.0, 800.0, 200.0), (700.0, 400.0, 800.0, 500.0)]
FAR = (900.0, 100.0, 1000.0, 200.0)

# File "dài": sự cố 20-80 s rồi cảnh sau cháy tới hết file 120 s.
LONG = dict(t_start=20.0, t_end=80.0, duration=120.0, sau_chay=[(80.0, 120.0)])
# File "hết ở t_end": sự cố 12-40 s, file dài 40 s.
SHORT = dict(t_start=12.0, t_end=40.0, duration=40.0, sau_chay=[])


def det(cls: str = "fire", box=BOXES[0]) -> list[Detection]:
    return [Detection(cls_name=cls, cls_id=0 if cls == "fire" else 1, conf=0.6,
                      xyxy=box)]


def simulate(duration: float, det_fn):
    """Heartbeats t = 0..floor(duration) through the real engine."""
    eng = VotingEngine(VCFG)
    with record_transitions() as rec:
        for seq, t in enumerate(range(math.floor(duration - 1e-6) + 1)):
            eng.update(seq, float(t), det_fn(float(t)))
    return [t for t in rec if t.alert], list(rec)


def run_file(spec: dict | None, duration: float, det_fn, sau_chay=None):
    alerts, trans = simulate(duration, det_fn)
    if spec is None:
        label = ClipLabel()
    else:
        label = ClipLabel([IncidentLabel(spec["t_start"], spec["t_end"])],
                          list(spec["sau_chay"] if sau_chay is None else sau_chay))
    run = ClipRun("f", duration, label, alerts, trans)
    old = run.to_clip_result()
    old_caught, old_fa = clip_outcomes(old, TOL)
    old_ttd = score_events([old], TOL)["ttd_median_s"]
    return old_caught, old_fa, old_ttd, score_clip(run)


def window(a: float, b: float, cls: str = "fire"):
    return lambda t: det(cls) if a <= t <= b else []


def test_observer_hook_records_and_leaves_engine_unchanged():
    pattern = [det() if t < 70 or 90 <= t < 100 else [] for t in range(130)]
    plain = VotingEngine(VCFG)
    ref = [(e.kind, e.ts, e.alert) for seq, d in enumerate(pattern)
           for e in plain.update(seq, float(seq), d)]
    hooked = VotingEngine(VCFG)
    with record_transitions() as rec:
        got = [(e.kind, e.ts, e.alert) for seq, d in enumerate(pattern)
               for e in hooked.update(seq, float(seq), d)]
    assert got == ref
    assert [(t.kind, t.ts, t.alert) for t in rec] == [r for r in ref if r[0] != "NEW"]
    assert not _TRANSITION_OBSERVERS


def test_s0_box_from_onset_same_under_both_rules():
    old_c, old_fa, old_ttd, new = run_file(LONG, 120.0, window(20, 80))
    assert old_c == [True] and old_fa == 0 and old_ttd == 5.0
    inc = new.incidents[0]
    assert inc.ttd(0) == inc.ttd(30) == 5.0 and inc.at_horizon
    assert new.fa_onsets == [] and not inc.early_hit


def test_s1_box_3s_early_same_under_both_rules():
    old_c, _, old_ttd, new = run_file(LONG, 120.0, window(17, 80))
    assert old_c == [True] and old_ttd == 2.0
    assert new.incidents[0].ttd() == 2.0


def test_s1_box_6s_early_old_misses_new_catches_with_negative_ttd():
    """M-1: v1 calls the early alert a false alarm and then misses the
    incident (cooldown 60 s, file ends at t_end); v2 catches it at -1 s."""
    old_c, old_fa, _, new = run_file(SHORT, 40.0, window(6, 40))
    assert old_c == [False] and old_fa == 1
    inc = new.incidents[0]
    assert inc.caught(0) and inc.caught(30) and inc.ttd() == -1.0
    assert inc.early_hit and new.prefire_onsets == []
    rows = review_list({"m": [new]})
    assert [(r["ly_do"], r["ts"]) for r in rows] == [("som_truoc_moc", 11.0)]


def test_s1_box_6s_early_old_ttd_pushed_to_59s_new_minus_1():
    old_c, old_fa, old_ttd, new = run_file(LONG, 120.0, window(14, 80))
    assert old_c == [True] and old_fa == 1 and old_ttd == 59.0
    assert new.incidents[0].ttd() == -1.0 and new.fa_onsets == []


def test_s1_box_20s_early_reported_as_prefire_false_alarm():
    """Confirmation 15 s before the onset (outside the 10 s window): v2 reports
    it as "FA trước sự cố" with its own exposure (10 s of pre-fire video)."""
    old_c, old_fa, old_ttd, new = run_file(LONG, 120.0, window(0, 80))
    assert old_c == [True] and old_fa == 1 and old_ttd == 45.0
    assert [o.ts for o in new.prefire_onsets] == [5.0]
    assert new.prefire_s == 10.0 and new.incidents[0].ttd() == 45.0


def test_s1k_smoke_early_then_fire():
    """Smoke box 10 s early then fire: v1 catches only through the
    escalation (TTD 1 s, one FA); v2 catches at -5 s with no FA."""
    def fn(t):
        return det("smoke") if 2 <= t < 12 else det() if 12 <= t <= 40 else []

    old_c, old_fa, old_ttd, new = run_file(SHORT, 40.0, fn)
    assert old_c == [True] and old_fa == 1 and old_ttd == 1.0
    assert new.incidents[0].ttd() == -5.0 and new.fa_onsets == []


def test_s2_reaction_only_after_t_end():
    """M-2: v1 counts a reaction to the post-fire scene as a catch (TTD 66 s).
    v2 with ``sau_chay`` labelled: no catch, no false alarm, eye review."""
    old_c, old_fa, old_ttd, new = run_file(LONG, 120.0, window(81, 110, "smoke"))
    assert old_c == [True] and old_fa == 0 and old_ttd == 66.0
    inc = new.incidents[0]
    assert not inc.caught(0) and not inc.caught(30) and not inc.at_horizon
    assert new.fa_onsets == [] and [s.ts for s in new.dropped_sau_chay] == [86.0]


def test_s2_without_sau_chay_label_only_tolerance_30_still_counts():
    _, _, _, new = run_file(LONG, 120.0, window(81, 110, "smoke"), sau_chay=[])
    inc = new.incidents[0]
    assert inc.caught(30) and not inc.caught(0) and not inc.at_horizon


def test_s3_scene_cuts_are_not_fixed_by_the_metric():
    """M-4 is a data issue: both rules miss when the scene cuts every 5 s and
    catch when it cuts every 6 s (``build_t1_dev.py`` flags such files)."""
    def cuts(c):
        return lambda t: det(box=BOXES[int((t - 20) // c) % 6]) if 20 <= t <= 80 else []
    old5, _, _, new5 = run_file(LONG, 120.0, cuts(5))
    old6, _, _, new6 = run_file(LONG, 120.0, cuts(6))
    assert old5 == [False] and not new5.incidents[0].caught()
    assert old6 == [True] and new6.incidents[0].caught()


def test_s4_always_alarm_positive_file():
    """Always-alarm model, short incident then post-fire scene: v1 catches
    through a STILL_BURNING reminder inside the tolerance; v2 does not (the
    reminder falls in ``sau_chay``) and reports one pre-fire false alarm."""
    spec = dict(t_start=30.0, t_end=40.0, duration=100.0, sau_chay=[(40.0, 100.0)])
    old_c, old_fa, old_ttd, new = run_file(spec, 100.0, lambda t: det())
    assert old_c == [True] and old_fa == 1 and old_ttd == 35.0
    assert not new.incidents[0].caught(30) and not new.incidents[0].at_horizon
    assert len(new.prefire_onsets) == 1


def test_s4_always_alarm_negative_files_alerts_vs_episodes():
    """M-3: one false track over a 292 s clip is 5 alerts in v1, 1 episode in
    v2; a 120 s clip 2 alerts vs 1 episode."""
    for dur, n_alerts in ((292.0, 5), (120.0, 2), (40.0, 1)):
        _, old_fa, _, new = run_file(None, dur, lambda t: det("smoke"))
        assert old_fa == n_alerts
        assert len(new.fa_onsets) == 1 and len(new.fa_alerts) == n_alerts


def test_m1_confirmation_silenced_by_scene_cooldown_counts_as_catch():
    """A false track elsewhere alerts at 5 s; the real fire confirms at 35 s
    but the scene cooldown silences it and the file ends at 40 s. v1 misses
    the incident; v2 records the silent CONFIRMED and catches it (TTD 5)."""
    def fn(t):
        return (det(box=FAR) if t < 10 else []) + (det() if 30 <= t <= 40 else [])
    spec = dict(t_start=30.0, t_end=40.0, duration=40.0, sau_chay=[])
    old_c, old_fa, _, new = run_file(spec, 40.0, fn)
    assert old_c == [False] and old_fa == 1
    inc = new.incidents[0]
    assert inc.ttd() == 5.0 and inc.first[30.0].alert is False
    assert [o.ts for o in new.prefire_onsets] == [5.0]
