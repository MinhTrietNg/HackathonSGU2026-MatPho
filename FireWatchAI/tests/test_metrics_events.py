"""Protocol v2 event metrics (M-1 .. M-6) on hand-built transition lists."""

from __future__ import annotations

import json
import math
import statistics

import pytest

from firewatch.episodes import Transition, confirmed_spans, episode_onsets, signals
from firewatch.evalkit import score_events
from firewatch.eventmetrics import (ClipLabel, ClipRun, IncidentLabel,
                                    ScoringConfig, dump_run, fa_by_stratum,
                                    fa_summary, incident_flags, load_file_meta,
                                    merged_incidents, parse_label, prefire_summary,
                                    runs_from_dump, score_clip, score_runs,
                                    sensitivity_summary, ttd_censored, ttd_common)

ALERTING = {"CONFIRMED", "RECONFIRMED", "ESCALATED", "DEFERRED", "STILL_BURNING"}


def tr(kind: str, ts: float, tid: int = 1, alert: bool | None = None) -> Transition:
    return Transition(kind, ts, tid, "CRITICAL",
                      kind in ALERTING if alert is None else alert)


def mk(trans, dur=100.0, events=((50.0, 70.0),), sau=(), rac=(), clip="f",
       khoi_lua=None) -> ClipRun:
    evs = []
    for i, (a, b) in enumerate(events):
        k, lua = khoi_lua[i] if khoi_lua else (None, None)
        evs.append(IncidentLabel(a, b, "fire", k, lua))
    return ClipRun(clip, dur, ClipLabel(evs, list(sau), list(rac)),
                   [t for t in trans if t.alert], list(trans))


# ------------------------------------------------------------------- M-1
def test_early_window_closed_at_minus_10_open_at_onset():
    inc = score_clip(mk([tr("CONFIRMED", 40.0)])).incidents[0]
    assert inc.caught() and inc.ttd() == -10.0 and inc.early_hit
    on = score_clip(mk([tr("CONFIRMED", 50.0)])).incidents[0]
    assert on.ttd() == 0.0 and not on.early_hit
    out = score_clip(mk([tr("CONFIRMED", 39.5)]))
    assert not out.incidents[0].caught()
    assert [o.ts for o in out.prefire_onsets] == [39.5] and out.prefire_s == 40.0


def test_silent_confirmation_is_a_signal_but_not_in_legacy_view():
    run = mk([tr("CONFIRMED", 55.0, alert=False)])
    assert score_clip(run).incidents[0].ttd() == 5.0
    legacy = ClipRun.from_clip_result(run.to_clip_result())
    assert legacy.transitions is None
    assert not score_clip(legacy).incidents[0].caught()
    assert score_events([run.to_clip_result()], 30.0)["caught"] == 0


def test_prefire_exposure_excludes_rac_and_early_window():
    out = score_clip(mk([], rac=[(0.0, 20.0)]))
    assert out.prefire_s == 20.0 and out.valid_s == 80.0


# ------------------------------------------------------------------- M-2
def test_tolerance_0_and_30():
    inc = score_clip(mk([tr("CONFIRMED", 80.0)])).incidents[0]
    assert not inc.caught(0) and inc.caught(30) and inc.ttd(30) == 30.0
    s = sensitivity_summary([score_clip(mk([tr("CONFIRMED", 80.0)]))])
    assert (s["tol_0"].k, s["tol_30"].k) == (0, 1)


def test_sau_chay_neither_catches_nor_counts_as_false_alarm():
    run = mk([tr("CONFIRMED", 75.0)], sau=[(70.0, 100.0)])
    out = score_clip(run)
    assert not out.incidents[0].caught(30)
    assert out.fa_onsets == [] and [s.ts for s in out.dropped_sau_chay] == [75.0]


def test_rac_ignored_and_removed_from_negative_hours():
    run = mk([tr("CONFIRMED", 12.0)], dur=3600.0, events=(), rac=[(0.0, 1800.0)])
    out = score_clip(run)
    assert out.fa_onsets == [] and [s.ts for s in out.dropped_rac] == [12.0]
    assert out.background_s == 1800.0
    s = fa_summary([out])
    assert s.hours == 0.5 and s.episodes == 0


def test_parse_label_accepts_v10_and_v11():
    old = parse_label({"events": [{"t_start": 3, "t_end": 9, "label": "fire"}],
                       "duration_s": 30})
    assert old.sau_chay == [] and old.rac == [] and old.events[0].t_khoi is None
    new = parse_label({"schema": "t1_dev_v1.1", "clip_id": "c",
                       "events": [{"t_end": 80, "t_khoi": 12, "t_lua": 20,
                                   "tin_cay": "cao"}],
                       "sau_chay": [[80, 120]], "rac": [[104.5, 100]]})
    assert new.events[0].t_start == 12.0 and new.rac == [(100.0, 104.5)]
    with pytest.raises(ValueError):
        parse_label({"events": [{"t_end": 5}]})


def test_merged_incidents_keep_earliest_phase_marks():
    lab = ClipLabel([IncidentLabel(10, 30, "smoke", 10, None),
                     IncidentLabel(25, 50, "fire", None, 25)])
    (m,) = merged_incidents(lab)
    assert (m.t_start, m.t_end, m.t_khoi, m.t_lua) == (10, 50, 10, 25)


# ------------------------------------------------------------------- M-3
def test_episode_counts_first_confirmation_and_reconfirmation_only():
    trs = [tr("CONFIRMED", 5), tr("STILL_BURNING", 65), tr("ESCALATED", 70),
           tr("STILL_BURNING", 125), tr("ENDED", 150), tr("RECONFIRMED", 170),
           tr("DEFERRED", 200), tr("CONFIRMED", 210, tid=2, alert=False)]
    assert [o.ts for o in episode_onsets(trs)] == [5, 170, 210]
    assert len(signals(trs, [t for t in trs if t.alert])) == 7


def test_scene_merge_variant_joins_split_boxes():
    trs = [tr("CONFIRMED", 5, 1), tr("CONFIRMED", 5, 2, False),
           tr("CONFIRMED", 8, 3, False), tr("ENDED", 20, 1), tr("ENDED", 20, 2),
           tr("ENDED", 21, 3), tr("CONFIRMED", 40, 4)]
    assert len(episode_onsets(trs)) == 4
    assert [o.ts for o in episode_onsets(trs, merge_overlapping=True,
                                         duration_s=60)] == [5, 40]
    assert confirmed_spans(trs, 60)[-1] == (40, 60.0, 4)


def _neg(clip, n_ep, dur=600.0, stills=0):
    trs = []
    for i in range(n_ep):
        trs.append(tr("CONFIRMED", 5 + 100 * i, tid=i + 1))
        trs += [tr("STILL_BURNING", 65 + 100 * i + 60 * j, tid=i + 1)
                for j in range(stills)]
    return mk(trs, dur=dur, events=(), clip=clip)


META = {"a1": {"camera_vat_ly": "camA", "nhom_nguon": "v1", "loai_am": "bt"},
        "a2": {"camera_vat_ly": "camA", "nhom_nguon": "v1", "loai_am": "dn"},
        "b1": {"camera_vat_ly": "camB", "nhom_nguon": "v2", "loai_am": "dn"},
        "c1": {"camera_vat_ly": "camC", "nhom_nguon": "v3", "loai_am": "bt"},
        "d1": {"camera_vat_ly": "camD", "nhom_nguon": "v4", "loai_am": "bt"}}


def test_fa_summary_episodes_sources_and_clusters():
    outs = score_runs([_neg("a1", 1, stills=3), _neg("a2", 0), _neg("b1", 2),
                       _neg("c1", 1), _neg("d1", 0)])
    s = fa_summary(outs, META, n_boot=500)
    assert s.episodes == 4 and s.raw_alerts == 7 and s.hours == pytest.approx(5 / 6)
    assert (s.sources.k, s.sources.n) == (3, 4)
    assert s.bootstrap.estimable and s.bootstrap.n_clusters_with_events == 3
    assert s.negbin.estimable and s.episode_source == "transitions"
    two = fa_summary(outs[:3], META)
    assert not two.bootstrap.estimable and math.isnan(two.bootstrap.lo)
    assert not two.negbin.estimable


def test_fa_split_by_loai_am_and_cluster_fallback():
    outs = score_runs([_neg("a1", 1), _neg("a2", 0), _neg("b1", 2), _neg("x9", 1)])
    by = fa_by_stratum(outs, META, "loai_am", n_boot=200)
    assert set(by) == {"bt", "dn", "(trống)"}
    assert by["dn"].episodes == 2 and by["bt"].episodes == 1
    assert fa_summary(outs, META, n_boot=200).clusters_from_fallback == 1


def test_legacy_runs_count_alerts_and_are_flagged():
    run = ClipRun.from_clip_result(_neg("a1", 1, stills=3).to_clip_result())
    s = fa_summary([score_clip(run)])
    assert s.episodes == 4 and s.episode_source == "alerts_legacy"


def test_prefire_summary_uses_prefire_exposure():
    outs = score_runs([mk([tr("CONFIRMED", 5)], clip="p1"), mk([], clip="p2")])
    s = prefire_summary(outs)
    assert s.episodes == 1 and s.hours == pytest.approx(80 / 3600)


# ------------------------------------------------------------------- M-5
def _model(ttds: dict[str, float | None]):
    runs = []
    starts = {"e0": 5.0, "e1": 20.0, "e2": 20.0, "e3": 20.0, "e4": 20.0}
    for clip, d in ttds.items():
        a = starts[clip]
        trs = [] if d is None else [tr("CONFIRMED", a + d)]
        runs.append(mk(trs, events=((a, a + 30),), clip=clip))
    return score_runs(runs)


def test_ttd_common_on_intersection_with_true_median():
    a = _model({"e0": 1.0, "e1": 6.0, "e2": 8.0, "e3": 10.0, "e4": 40.0})
    b = _model({"e0": 1.0, "e1": 7.0, "e2": 9.0, "e3": None, "e4": 12.0})
    t = ttd_common({"A": a, "B": b})
    assert t.keys == [("e1", 0), ("e2", 0), ("e4", 0)]
    assert t.median == {"A": 8.0, "B": 9.0}
    alone = ttd_common({"A": a, "B": a})
    assert alone.n == 4 and alone.median["A"] == statistics.median([6, 8, 10, 40])
    # v1: tập riêng của model, trung vị lệch trên khi n chẵn (gồm cả e0).
    old = score_events([r.to_clip_result() for r in [
        mk([tr("CONFIRMED", 20 + d)], events=((20, 50),)) for d in (6, 8, 10, 40)]],
        30.0)
    assert old["ttd_median_s"] == 10.0 and alone.median["A"] == 9.0


def test_ttd_censored_counts_missed_as_censored():
    b = _model({"e0": 1.0, "e1": 7.0, "e2": 9.0, "e3": None, "e4": None})
    c = ttd_censored(b)
    assert (c.n, c.detected, c.censored) == (4, 2, 2)
    assert c.quantiles[0.25] == 7.0 and c.quantiles[0.5] == 9.0
    assert math.isnan(c.quantiles[0.75])


# ------------------------------------------------------------------- M-6
def test_sensitivity_at_60_s():
    run = mk([tr("CONFIRMED", 120.0)], dur=300.0, events=((50.0, 250.0),))
    inc = score_clip(run).incidents[0]
    assert inc.caught(0) and not inc.at_horizon
    assert score_clip(mk([tr("CONFIRMED", 110.0)], dur=300.0,
                         events=((50.0, 250.0),))).incidents[0].at_horizon


def test_early_phase_definition():
    def one(sig_ts, khoi, lua):
        return score_clip(mk([tr("CONFIRMED", sig_ts)], events=((khoi, 90.0),),
                             khoi_lua=[(khoi, lua)])).incidents[0]
    assert one(25.0, 10.0, 30.0).early_phase
    assert not one(30.0, 10.0, 30.0).early_phase
    short = one(12.0, 10.0, 14.0)
    assert not short.early_phase_eligible and not short.early_phase
    outs = [score_clip(mk([tr("CONFIRMED", 25.0)], events=((10.0, 90.0),),
                          khoi_lua=[(10.0, 30.0)], clip="x")),
            score_clip(mk([], events=((10.0, 90.0),), clip="y"))]
    s = sensitivity_summary(outs)
    assert (s["early_phase"].k, s["early_phase"].n) == (1, 1)
    assert incident_flags(outs, "early_phase") == {("x", 0): True}
    with pytest.raises(ValueError):
        incident_flags(outs, "bad")


# ---------------------------------------------------------- dump / load
def test_dump_roundtrip_and_legacy_json(tmp_path):
    run = mk([tr("CONFIRMED", 45.0), tr("STILL_BURNING", 105.0)], dur=120.0,
             sau=[(70.0, 120.0)])
    d = dump_run(run)
    assert {"positive", "duration_s", "gt", "alerts"} <= set(d)
    back = runs_from_dump({"models": {"m": {"f": json.loads(json.dumps(d))}}})["m"][0]
    assert back.label.sau_chay == [(70.0, 120.0)]
    assert back.transitions == run.transitions
    assert score_clip(back).incidents[0].ttd() == -5.0
    legacy = {"models": {"m": {"f": {"positive": True, "duration_s": 120.0,
                                     "gt": [[50.0, 70.0]], "alerts": [45.0]}}}}
    old = runs_from_dump(legacy)["m"][0]
    assert old.transitions is None and score_clip(old).episode_source == "alerts_legacy"


def test_load_file_meta_merges_tables(tmp_path):
    (tmp_path / "files.csv").write_text(
        "file,clip_id,camera_vat_ly,loai_am\nf1,c1,camA,dn\n", encoding="utf-8")
    (tmp_path / "clips_meta.csv").write_text(
        "clip,clip_id,nhom_nguon,camera\nf1,c1,v1,cctv\nf2,c2,v2,cctv\n",
        encoding="utf-8")
    meta = load_file_meta(tmp_path / "files.csv", tmp_path / "clips_meta.csv",
                          tmp_path / "missing.csv")
    assert meta["f1"] == {"file": "f1", "clip_id": "c1", "camera_vat_ly": "camA",
                          "loai_am": "dn", "clip": "f1", "nhom_nguon": "v1",
                          "camera": "cctv"}
    assert meta["f2"]["nhom_nguon"] == "v2"


def test_files_of_one_incident_count_once_with_metadata():
    outs = [score_clip(mk([tr("CONFIRMED", 55.0)], clip="cam1")),
            score_clip(mk([], clip="cam2")), score_clip(mk([], clip="solo"))]
    meta = {"cam1": {"nhom_su_co": "vu7"}, "cam2": {"nhom_su_co": "vu7"}}
    assert incident_flags(outs, "tol_30") == {("cam1", 0): True, ("cam2", 0): False,
                                              ("solo", 0): False}
    assert incident_flags(outs, "tol_30", meta) == {("vu7", 0): True,
                                                    ("solo", 0): False}
    s = sensitivity_summary(outs, meta=meta)
    assert (s["tol_30"].k, s["tol_30"].n) == (1, 2)


def test_adapters_for_tier_tables():
    from types import SimpleNamespace

    from firewatch.eventmetrics import caught_fn_for, fa_fn_for
    outs = [score_clip(mk([tr("CONFIRMED", 80.0)], clip="p")),
            score_clip(_neg("n", 2, stills=2)),
            score_clip(mk([tr("CONFIRMED", 5.0)], clip="q"))]
    caught = caught_fn_for(outs, "tol_0")
    assert caught(SimpleNamespace(clip="p"), 30.0) == [False]
    assert caught_fn_for(outs, "tol_30")(SimpleNamespace(clip="p"), 0.0) == [True]
    fa = fa_fn_for(outs)
    assert fa(SimpleNamespace(clip="n"), 30.0) == (2.0, pytest.approx(600 / 3600))
    assert fa_fn_for(outs, prefire=True)(SimpleNamespace(clip="q"), 30.0) == (
        1.0, pytest.approx(40 / 3600))
    with pytest.raises(ValueError):
        caught_fn_for(outs, "early_phase")


def test_scoring_config_changes_early_window():
    run = mk([tr("CONFIRMED", 44.0)])
    assert score_clip(run).incidents[0].caught()
    assert not score_clip(run, ScoringConfig(early_s=5.0)).incidents[0].caught()
