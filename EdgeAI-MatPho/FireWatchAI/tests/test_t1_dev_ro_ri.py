"""Leak flags of the team's own models and the main-set tier column of T1-dev."""

from pathlib import Path

import pytest

from firewatch.tiers import leaked, main_tier, parse_tags, read_files_csv

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog"
FILES = CATALOG / "t1_dev_v1.1_files.csv"
SOURCES = CATALOG / "t1_dev_v1.1_nguon_train.csv"


def _tags() -> dict[str, frozenset[str]]:
    import csv
    with SOURCES.open(encoding="utf-8") as fh:
        return {r["model"]: parse_tags(r["nguon_train"]) for r in csv.DictReader(fh)}


@pytest.mark.skipif(not (FILES.is_file() and SOURCES.is_file()),
                    reason="chưa có bảng files/nguon_train của T1-dev v1.1")
def test_clip_100_is_leaked_for_every_model_trained_on_fasdd():
    files = read_files_csv(FILES)
    row = next(f for f in files.values() if f.clip_id.endswith("-100"))
    tags = _tags()
    for model in ("team_yolo26n_fasdd", "team_yolo26n_full_v121",
                  "team_yolo26n_full_v12"):
        assert "fasdd" in tags[model]
        assert leaked(row, tags[model]) is True
    assert leaked(row, tags["yolo26n_coco"]) is False


def test_main_tier_is_empty_outside_the_main_set():
    assert main_tier("A", "1") == ""
    assert main_tier("A", True) == ""
    assert main_tier("A", "0") == "A"
    assert main_tier("am", "") == "am"


@pytest.mark.skipif(not FILES.is_file(), reason="chưa có files.csv của T1-dev v1.1")
def test_files_table_has_main_tier_column_consistent_with_tiers():
    import csv
    with FILES.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if "tang_chinh" not in rows[0]:
        pytest.skip("bảng files.csv dựng trước khi có cột tang_chinh")
    for r in rows:
        assert r["tang_chinh"] == main_tier(r["tang"], r["loai_khoi_bo_chinh"])
    outside = {r["file"] for r in rows if r["loai_khoi_bo_chinh"] == "1"}
    assert {r["file"] for r in rows if r["tang_chinh"] == ""} == outside
