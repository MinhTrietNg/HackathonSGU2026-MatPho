"""Split allocation, AP@50 / P-R-F1 and event scoring on hand-made cases."""

import math

from firewatch.evalkit import (ClipResult, FrameMetrics, GTBox, GTEvent, PredBox,
                               allocate_split, average_precision, match_predictions,
                               merge_events, score_events, stratified_clip_split)


def test_allocate_split_rounding_and_tiny_strata():
    assert allocate_split(10, (0.7, 0.15, 0.15)) == [7, 2, 1]
    assert sum(allocate_split(13, (0.7, 0.15, 0.15))) == 13
    assert allocate_split(1, (0.7, 0.15, 0.15)) == [1, 0, 0]
    assert allocate_split(2, (0.7, 0.15, 0.15))[0] >= 1
    assert allocate_split(0, (0.7, 0.15, 0.15)) == [0, 0, 0]


def test_stratified_split_is_per_clip_and_deterministic():
    items = [(f"c{i}", "HAM/pos") for i in range(10)] + [
        (f"n{i}", "HAM/neg") for i in range(4)]
    a = stratified_clip_split(items, (0.7, 0.15, 0.15), seed=1)
    b = stratified_clip_split(items, (0.7, 0.15, 0.15), seed=1)
    assert a == b and set(a) == {c for c, _ in items}
    pos = [a[f"c{i}"] for i in range(10)]
    assert pos.count("train") == 7 and pos.count("val") == 2 and pos.count("test") == 1


def test_matching_and_ap():
    gts = [GTBox("fire", (0, 0, 100, 100)), GTBox("fire", (200, 200, 300, 300))]
    preds = [PredBox("fire", 0.9, (5, 5, 100, 100)),      # TP
             PredBox("fire", 0.8, (0, 0, 100, 100)),      # trùng GT 1 -> FP
             PredBox("fire", 0.7, (210, 205, 300, 300)),  # TP
             PredBox("smoke", 0.95, (0, 0, 100, 100))]    # class khác, bỏ qua
    rec = match_predictions(preds, gts, "fire")
    assert [tp for _, tp in rec] == [True, False, True]
    ap = average_precision(rec, n_gt=2)
    # recall 0.5 @ p=1.0, recall 1.0 @ p=2/3 -> AP = 0.5*1 + 0.5*(2/3)
    assert math.isclose(ap, 0.5 + 0.5 * 2 / 3)
    assert average_precision([], n_gt=0) == 0.0


def test_frame_metrics_summary():
    fm = FrameMetrics()
    box = (0, 0, 10, 10)
    fm.add([PredBox("fire", 0.9, box), PredBox("smoke", 0.2, box)],
           [GTBox("fire", box), GTBox("smoke", box)])
    s = fm.summary(conf_thr=0.25)
    assert s["fire"]["ap50"] == 1.0 and s["fire"]["recall"] == 1.0
    assert s["smoke"]["ap50"] == 1.0            # AP không phụ thuộc ngưỡng
    assert s["smoke"]["recall"] == 0.0          # nhưng P/R @0.25 thì bỏ box 0.2
    assert s["all"]["ap50"] == 1.0 and s["all"]["n_gt"] == 2


def test_merge_events_and_scoring():
    merged = merge_events([GTEvent(0, 10), GTEvent(0, 10), GTEvent(30, None)])
    assert len(merged) == 2 and merged[1].t_end is None
    results = [
        ClipResult("fire_a", True, 60, [GTEvent(10, 40)], alert_ts=[14.0, 50.0]),
        ClipResult("fire_b", True, 60, [GTEvent(5, None)], alert_ts=[]),
        ClipResult("neg_a", False, 1800, [], alert_ts=[100.0]),
        ClipResult("neg_b", False, 1800, [], alert_ts=[]),
    ]
    m = score_events(results, tolerance_s=5)
    assert m["incidents"] == 2 and m["caught"] == 1 and m["miss_rate"] == 0.5
    assert m["ttd_median_s"] == 4.0
    assert m["false_alarms_neg"] == 1 and m["false_alarms_pos"] == 1
    assert math.isclose(m["neg_hours"], 1.0) and math.isclose(m["fa_per_hour_neg"], 1.0)
