"""Decision rules of protocol v2 (better / not worse / leading) and the report."""

from __future__ import annotations

import pytest

from firewatch.claims import (Margins, fa_paired, verdict_all, verdict_pair,
                              verdicts_from_outcomes)
from firewatch.episodes import Transition
from firewatch.eventmetrics import ClipLabel, ClipRun, IncidentLabel, score_runs
from firewatch.eventreport import metrics_v2_md

CAMS = ["camA", "camB", "camC", "camD", "camE"]
META = {f"n{i}": {"camera_vat_ly": CAMS[i % 5], "nhom_nguon": f"v{i % 5}",
                  "loai_am": "dn" if i % 2 else "bt"} for i in range(20)}


def _model(caught: list[bool], fa: list[int], neg_s: float = 1800.0):
    """Positive files p0..: caught at 5 s or not; negative files n0..: FA count."""
    runs = []
    for i, c in enumerate(caught):
        trs = [Transition("CONFIRMED", 25.0, 1, "CRITICAL", True)] if c else []
        runs.append(ClipRun(f"p{i}", 60.0, ClipLabel([IncidentLabel(20.0, 50.0)]),
                            [t for t in trs if t.alert], trs))
    for i, k in enumerate(fa):
        trs = [Transition("CONFIRMED", 10.0 + 60 * j, j + 1, "WARNING", True)
               for j in range(k)]
        runs.append(ClipRun(f"n{i}", neg_s, ClipLabel(), list(trs), trs))
    return score_runs(runs)


FA_SPREAD = [1, 0, 1, 0, 1, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
M = Margins(delta_s=0.15, delta_f=1.0)


def test_much_better_model_is_called_better():
    ours = _model([True] * 40, FA_SPREAD)
    theirs = _model([True] * 20 + [False] * 20, FA_SPREAD)
    v = verdict_pair(ours, theirs, "doi_thu", M, META, n_boot=1000)
    assert v.ni_s and v.ni_f and v.sup_s and v.label == "TỐT HƠN"
    assert v.fa.estimable and v.fa.diff == 0.0


def test_identical_models_on_40_incidents_are_only_not_worse():
    a = _model([True] * 30 + [False] * 10, FA_SPREAD)
    v = verdict_pair(a, a, "ban_sao", M, META, n_boot=1000)
    assert v.label == "KHÔNG KÉM" and not v.sup_s and not v.sup_f
    assert v.sens.low > -0.15


def test_identical_models_on_6_incidents_fail_the_ni_rule():
    """v1 rule: only_base (0) <= only_cand (0) -> "không kém". v2: the Tango
    interval is too wide at n = 6 for a 15-point margin -> CHƯA ĐẠT."""
    a = _model([True] * 5 + [False], FA_SPREAD)
    v = verdict_pair(a, a, "ban_sao", M, META, n_boot=500)
    assert v.sens.counts.only_a == v.sens.counts.only_b == 0      # v1: qua
    assert not v.ni_s and v.label == "CHƯA ĐẠT"


def test_fa_not_estimable_falls_back_to_our_exact_upper_bound():
    zero = [0] * 20
    theirs_fa = [3] + [0] * 19                       # FA dồn vào 1 camera
    ours = _model([True] * 40, zero)
    d = fa_paired(ours, _model([True] * 40, theirs_fa), META)
    assert not d.estimable and d.n_clusters_with_events == 1
    v = verdict_pair(ours, _model([True] * 40, theirs_fa), "x", M, META)
    assert v.fa_rule == "poisson_rieng_model_doi" and v.ni_f and not v.sup_f
    short = _model([True] * 40, zero, neg_s=60.0)    # 20 phút âm: cận trên 11/giờ
    v2 = verdict_pair(short, _model([True] * 40, theirs_fa, neg_s=60.0), "x", M,
                      META)
    assert not v2.ni_f and v2.label == "CHƯA ĐẠT"


def test_more_false_alarms_fail_ni_on_fa():
    ours = _model([True] * 40, [6, 5, 6, 5, 6] + [4] * 15)
    theirs = _model([True] * 40, FA_SPREAD)
    v = verdict_pair(ours, theirs, "y", M, META, n_boot=1000)
    assert v.fa.estimable and v.fa.low > 0 and not v.ni_f


def test_field_verdict_intersection_union_and_holm():
    by = {"ours": _model([True] * 40, FA_SPREAD),
          "weak": _model([True] * 20 + [False] * 20, FA_SPREAD),
          "twin": _model([True] * 40, FA_SPREAD)}
    f = verdicts_from_outcomes(by, "ours", M, META, n_boot=500)
    assert f.not_worse_all and not f.leading
    assert f.holm_claims["weak:S"][2] and not f.holm_claims["twin:S"][2]
    only = verdict_all([p for p in f.pairs if p.competitor == "weak"])
    assert only.leading
    assert not verdict_all([]).not_worse_all


def test_report_section_renders_every_part():
    by = {"ours": _model([True] * 4 + [False], [1, 0, 0, 0, 0, 1]),
          "other": _model([True] * 3 + [False] * 2, [0, 0, 0, 0, 0, 0])}
    md = "\n".join(metrics_v2_md(by, META, margins=M, ours="ours"))
    for part in ("Độ nhạy theo sự cố", "Báo nhầm theo đợt", "`loai_am`",
                 "FA trước sự cố", "Kaplan–Meier", "So sánh cặp",
                 "Kết luận theo giao thức v2", "không ước lượng được",
                 "Danh sách xem mắt"):
        assert part in md, part
    assert "| ours | 5/5" not in md and "4/5 = 80 %" in md
    assert "Cảnh báo" not in md
    bare = "\n".join(metrics_v2_md(by, {}))
    assert "**Cảnh báo:** 6 file âm thiếu `camera_vat_ly`" in bare


def test_margins_must_be_non_negative():
    from firewatch.noninferiority import PairedCounts, noninferiority
    with pytest.raises(ValueError):
        noninferiority(PairedCounts(1, 0, 0, 0), -0.1)
