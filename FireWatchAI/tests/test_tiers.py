"""Tier rules, per-tier cells and tables of firewatch.tiers (synthetic data)."""

import csv
import math
from pathlib import Path

import pytest

from firewatch.evalkit import ClipResult, GTEvent
from firewatch.tiers import (FILES_COLUMNS, NO_CONCLUSION, FileRow, assign_tier,
                             composition, fa_cell, heartbeats_in, longest_scene,
                             paired_cell, paired_table, read_files_csv, scoring_window,
                             sens_cell, standard_subsets, tier_table, voting_scorable)


def row(file, duong=True, tang="A", cam=None, group=None, **kw) -> FileRow:
    base = dict(file=file, clip_id=file, nhom_nguon=f"src_{file}",
                camera_vat_ly=cam or f"cam_{file}", nhom_su_co=group or file,
                duong=duong, tang=tang if duong else "am", loai_am="" if duong
                else "bt", mu=False, fa_da_chan_doan=False, ro_ri=frozenset(),
                ngoai_fa_chinh=False, cham_duoc_voting=True, canh_dai_nhat_s=60.0,
                nguon_nhan="tu_dong_v1.0")
    base.update(kw)
    return FileRow(**base)


def pos(clip, alerts, t0=10.0, t1=40.0, dur=60.0):
    return ClipResult(clip, True, dur, [GTEvent(t0, t1)], alerts)


def neg(clip, alerts, dur=3600.0):
    return ClipResult(clip, False, dur, [], alerts)


# ------------------------------------------------------------ tier rule
@pytest.mark.parametrize("args, want", [
    ((False, "vn", True, True), "am"),
    ((True, "vn", True, False), "A"),
    ((True, "cn", True, True), "B"),
    ((True, "cn", True, False), "C"),
    ((True, "vn", False, True), "C"),
    ((True, "us", False, False), "C"),
])
def test_assign_tier(args, want):
    assert assign_tier(*args) == want


def test_heartbeats_match_known_files():
    # 108: cửa sổ 12–21,5 s trong file 21,52 s -> 10 heartbeat (0, 1, 2 ... s)
    t0, t1 = scoring_window(12.0, 21.5, 21.52, 30.0)
    assert heartbeats_in(t0, t1, 21.52) == 10
    t0, t1 = scoring_window(2.0, 7.4, 7.38, 30.0)
    assert heartbeats_in(t0, t1, 7.38) == 6
    assert heartbeats_in(0.0, 6.0, 6.0) == 6        # nhịp 6 s trùng khung cuối: bỏ
    assert heartbeats_in(5.0, 4.0, 10.0) == 0


def test_window_open_end_uses_duration():
    assert scoring_window(5.0, None, 50.0, 30.0) == (5.0, 50.0)


def test_longest_scene_inside_window_only():
    cuts = [3.0, 20.0, 31.0]
    assert longest_scene(cuts, 0.0, 40.0) == 17.0
    assert longest_scene(cuts, 21.0, 30.0) == 9.0
    assert longest_scene([], 2.0, 2.0) == 0.0


def test_voting_scorable_floors():
    assert not voting_scorable(5.9, 40, True, 6.0)
    assert not voting_scorable(30.0, 14, True, 6.0)
    assert voting_scorable(6.0, 15, True, 6.0)
    assert voting_scorable(6.0, 3, False, 6.0)      # sàn heartbeat chỉ cho dương


# ------------------------------------------------------------ files.csv
def write_files(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FILES_COLUMNS) + ["da_chay_boi"])
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in list(FILES_COLUMNS) + ["da_chay_boi"]})


def test_read_files_csv_parses_flags_and_tags(tmp_path):
    p = tmp_path / "files.csv"
    write_files(p, [{"file": "f1", "clip_id": "c1", "duong": "1", "tang": "A",
                     "mu": "0", "ro_ri": "fasdd;matpho_v0.4", "cham_duoc_voting": "1",
                     "canh_dai_nhat_s": "12.5", "da_chay_boi": "m1;m2"},
                    {"file": "f2", "clip_id": "c2", "duong": "0", "tang": "am",
                     "mu": "1", "cham_duoc_voting": "0", "canh_dai_nhat_s": ""}])
    rows = read_files_csv(p)
    assert rows["f1"].ro_ri == {"fasdd", "matpho_v0.4"}
    assert rows["f1"].da_chay_boi == {"m1", "m2"}
    assert rows["f1"].canh_dai_nhat_s == 12.5 and rows["f2"].canh_dai_nhat_s is None
    assert rows["f2"].mu and not rows["f2"].cham_duoc_voting


def test_read_files_csv_rejects_bad_tier_and_missing_column(tmp_path):
    p = tmp_path / "files.csv"
    write_files(p, [{"file": "f1", "tang": "D"}])
    with pytest.raises(ValueError, match="tầng"):
        read_files_csv(p)
    p.write_text("file,clip_id\nf1,c1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="thiếu cột"):
        read_files_csv(p)


# ------------------------------------------------------------ cells
def test_sens_cell_counts_incident_once_and_excludes():
    files = {"a_d1": row("a_d1", group="vu1"), "a_d2": row("a_d2", group="vu1"),
             "b": row("b", ro_ri=frozenset({"fasdd"}))}
    res = [pos("a_d1", []), pos("a_d2", [15.0]), pos("b", [])]
    c = sens_cell(res, files, lambda f: f.duong, 30.0)
    assert (c["k"], c["n"]) == (1, 2)
    lo, hi = c["ci"]
    assert 0 < lo < 0.5 < hi < 1
    c2 = sens_cell(res, files, lambda f: f.duong, 30.0,
                   exclude=lambda f: "fasdd" in f.ro_ri)
    assert (c2["k"], c2["n"]) == (1, 1)


def test_fa_cell_clusters_by_camera_and_flags_not_estimable():
    files = {"n1": row("n1", duong=False, cam="camX"),
             "n2": row("n2", duong=False, cam="camX"),
             "n3": row("n3", duong=False, cam="camY")}
    res = [neg("n1", [5.0, 500.0]), neg("n2", [7.0]), neg("n3", [])]
    c = fa_cell(res, files, lambda f: not f.duong, 30.0)
    assert c["fa"] == 3 and math.isclose(c["hours"], 3.0)
    assert c["n_cam"] == 2 and c["n_cam_fa"] == 1
    assert not c["estimable"] and math.isnan(c["ci"][0])
    files.update({f"m{i}": row(f"m{i}", duong=False) for i in range(4)})
    res += [neg(f"m{i}", [100.0]) for i in range(4)]
    c = fa_cell(res, files, lambda f: not f.duong, 30.0)
    assert c["estimable"] and c["ci"][0] <= c["rate"] <= c["ci"][1]


def test_hooks_replace_the_measure():
    files = {"p": row("p"), "n": row("n", duong=False)}
    res = [pos("p", []), neg("n", [1.0, 2.0])]
    c = sens_cell(res, files, lambda f: f.duong, 30.0,
                  caught_fn=lambda r, tol: [True])
    assert c["k"] == 1
    f = fa_cell(res, files, lambda f: not f.duong, 30.0,
                fa_fn=lambda r, tol: (1.0, 0.5))
    assert f["fa"] == 1 and f["hours"] == 0.5


def test_paired_cell_mcnemar_on_common_incidents():
    a = {"caught": {"x": True, "y": True, "z": False}}
    b = {"caught": {"x": False, "y": True, "z": True, "w": True}}
    p = paired_cell(a, b)
    assert (p["n"], p["only_a"], p["only_b"]) == (3, 1, 1)
    assert p["p"] == 1.0


# ------------------------------------------------------------ tables
def fixture_set():
    files = {"a1": row("a1", tang="A"), "a2": row("a2", tang="A"),
             "b1": row("b1", tang="B", ro_ri=frozenset({"fasdd"})),
             "c1": row("c1", tang="C"),
             "c2": row("c2", tang="C", cham_duoc_voting=False, canh_dai_nhat_s=4.0),
             "m1": row("m1", tang="A", mu=True),
             "n1": row("n1", duong=False, cam="k1", fa_da_chan_doan=True),
             "n2": row("n2", duong=False, cam="k2", loai_am="dn"),
             "n3": row("n3", duong=False, cam="k3", ngoai_fa_chinh=True)}
    base = [pos("a1", [12.0]), pos("a2", []), pos("b1", [12.0]), pos("c1", [12.0]),
            pos("c2", [12.0]), pos("m1", []), neg("n1", [10.0]), neg("n2", []),
            neg("n3", [5.0])]
    cand = [pos("a1", [12.0]), pos("a2", [12.0]), pos("b1", []), pos("c1", [12.0]),
            pos("c2", []), pos("m1", [12.0]), neg("n1", []), neg("n2", []),
            neg("n3", [])]
    return files, {"base": base, "cand": cand}


def test_tier_table_has_every_tier_with_n_and_pooled_row_flagged():
    files, per = fixture_set()
    md, cells = tier_table(per, files, 30.0, {"base": frozenset({"fasdd"})})
    text = "\n".join(md)
    for s in standard_subsets():
        assert s.title in text
    assert NO_CONCLUSION in text
    pooled = next(line for line in md if line.startswith("| Toàn bộ"))
    assert pooled.rstrip().endswith("KHÔNG |")
    # tầng A: a1, a2, m1 (m1 mù cũng là A) -> base bắt 1/3, cand 3/3
    assert (cells["base"]["A"]["sens"]["k"], cells["base"]["A"]["sens"]["n"]) == (1, 3)
    assert cells["cand"]["A"]["sens"]["k"] == 3
    # c2 không chấm được: ra khỏi tầng C, vào hàng tham khảo
    assert cells["base"]["C"]["sens"]["n"] == 1
    assert cells["base"]["khong_cham"]["sens"]["n"] == 1
    # FA chính bỏ n3 (ngoài FA chính); bỏ chẩn đoán bỏ thêm n1
    assert cells["base"]["am"]["fa"]["fa"] == 1
    assert cells["base"]["am_bo_cd"]["fa"]["n_files"] == 1
    assert cells["base"]["am_dn"]["fa"]["n_files"] == 1
    # rò rỉ: chỉ base (train fasdd) bị bỏ b1
    assert cells["base"]["B_bo_ro_ri"]["sens"]["n"] == 0
    assert cells["cand"]["B_bo_ro_ri"]["sens"]["n"] == 1
    assert cells["base"]["mu"]["sens"]["n"] == 1


def test_paired_table_lists_tiers_and_conclusion_column():
    files, per = fixture_set()
    _, cells = tier_table(per, files, 30.0)
    md = paired_table(cells, "base", "cand")
    assert md[0].startswith("| Tầng | Sự cố chung")
    row_a = next(line for line in md if line.startswith("| Tầng A"))
    assert "| 3 | 0 | 2 |" in row_a
    assert next(line for line in md if line.startswith("| Toàn bộ")).endswith(
        "KHÔNG |")


def test_composition_counts_files_incidents_hours_cameras():
    files, _ = fixture_set()
    dur = {"n1": 3600.0, "n2": 1800.0, "n3": 900.0}
    md = composition(files, dur)
    a = next(line for line in md if line.startswith("| Tầng A"))
    assert "| 3 | 3 (3/6" in a
    am = next(line for line in md if line.startswith("| Âm — FA chính"))
    assert "| 2 | 1.500 | 2 |" in am
