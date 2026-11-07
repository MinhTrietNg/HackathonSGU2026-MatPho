"""Mixed fine-tune set builder: label parsing, class mapping, sampling, splits."""

import random
from pathlib import Path

import numpy as np
import pytest

from firewatch.config import Config, FinetuneConfig, FinetuneSource
from firewatch.datamix import (Item, SourceStats, bucket_items, bucket_targets,
                               clip_box, dedupe, load_source, read_voc, read_yolo,
                               sample_bucket, split_by_group, yolo_lines)

VOC = """<annotation><size><width>200</width><height>100</height></size>
<object><name>fire</name><bndbox><xmin>20</xmin><ymin>10</ymin><xmax>60</xmax>
<ymax>50</ymax></bndbox></object>
<object><name>other</name><bndbox><xmin>0</xmin><ymin>0</ymin><xmax>10</xmax>
<ymax>10</ymax></bndbox></object></annotation>"""


def test_voc_maps_classes_and_normalises(tmp_path: Path):
    p = tmp_path / "a.xml"
    p.write_text(VOC, encoding="utf-8")
    st = SourceStats()
    boxes = read_voc(p, {"fire": "fire", "smoke": "smoke", "other": "drop"}, st)
    assert len(boxes) == 1 and boxes[0][0] == "fire"
    assert boxes[0][1:] == pytest.approx((0.2, 0.3, 0.2, 0.4))
    assert st.boxes_in == {"fire": 1, "other": 1} and st.boxes_dropped == {"other": 1}


def test_voc_rejects_entity_declarations(tmp_path: Path):
    p = tmp_path / "evil.xml"
    p.write_text('<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]>' + VOC,
                 encoding="utf-8")
    st = SourceStats()
    assert read_voc(p, {"fire": "fire"}, st) == []
    assert st.boxes_dropped["xml_rejected"] == 1


def test_yolo_remap_swapped_order_and_clip(tmp_path: Path):
    p = tmp_path / "a.txt"
    # Nguồn theo quy ước D-Fire gốc: 0 = smoke, 1 = fire; box thứ 2 tràn biên.
    p.write_text("0 0.5 0.5 0.2 0.2\n1 0.95 0.5 0.2 0.2\n2 0.5 0.5 0.1 0.1\n",
                 encoding="utf-8")
    st = SourceStats()
    boxes = read_yolo(p, {"0": "smoke", "1": "fire"}, st)
    assert [b[0] for b in boxes] == ["smoke", "fire"]
    assert boxes[1][1] == pytest.approx(0.925) and boxes[1][3] == pytest.approx(0.15)
    assert st.unknown_classes == {"2": 1}
    assert yolo_lines(boxes).splitlines()[0].startswith("1 ")   # smoke -> id 1


def test_skip_class_removes_whole_image(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("0 0.5 0.5 0.2 0.2\n1 0.3 0.3 0.1 0.1\n", encoding="utf-8")
    st = SourceStats()
    assert read_yolo(p, {"0": "fire", "1": "skip"}, st) is None
    p.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    assert len(read_yolo(p, {"0": "fire", "1": "skip"}, st)) == 1


def test_clip_box_drops_degenerate():
    assert clip_box(1.2, 0.5, 0.1, 0.1) is None
    assert clip_box(0.5, 0.5, 0.0, 0.3) is None


def test_bucket_targets_anchor_on_domain_positives():
    ratios = {"pos_domain": 0.35, "neg_domain": 0.35, "base": 0.30}
    avail = {"pos_domain": 100, "neg_domain": 50, "base": 10_000}
    t = bucket_targets(avail, ratios, 0)
    assert t == {"pos_domain": 100, "neg_domain": 50, "base": 86}
    with pytest.raises(ValueError):
        bucket_targets({"neg_domain": 5, "base": 5}, ratios, 0)
    t2 = bucket_targets({"neg_domain": 30, "base": 999}, ratios, 100)
    assert t2 == {"pos_domain": 0, "neg_domain": 30, "base": 30}


def _items(n_groups: int, per: int, bucket: str, source: str = "s") -> list[Item]:
    out = []
    for g in range(n_groups):
        for i in range(per):
            out.append(Item(source, Path(f"/{source}/{g}_{i}.jpg"), [], f"{source}:{g}",
                            bucket))
    return out


def test_split_keeps_groups_whole_per_bucket():
    items = _items(10, 5, "pos_domain") + _items(10, 3, "base", "b")
    split = split_by_group(items, 0.2, random.Random(0))
    for it in items:
        mates = [split[str(o.image)] for o in items if o.group == it.group]
        assert len(set(mates)) == 1
    val_pos = sum(1 for it in items if it.bucket == "pos_domain"
                  and split[str(it.image)] == "val")
    assert val_pos == 10                                     # 2 nhóm × 5 ảnh


def test_group_spanning_two_buckets_lands_in_one_split():
    """Hồi quy: khung cháy (dương) và khung trước-cháy (âm) của cùng một clip
    từng bị chia độc lập theo nhóm vai trò và rơi vào hai split khác nhau."""
    items = []
    for c in range(20):
        g = f"clip:c{c}"
        items += [Item("chay", Path(f"/chay/c{c}_{i}.jpg"), [("fire", .5, .5, .1, .1)],
                       g, "pos_domain") for i in range(5)]
        items += [Item("truoc", Path(f"/truoc/c{c}_{i}.jpg"), [], g, "neg_domain")
                  for i in range(2)]
    for seed in range(5):
        split = split_by_group(items, 0.2, random.Random(seed))
        for c in range(20):
            sp = {split[str(it.image)] for it in items if it.group == f"clip:c{c}"}
            assert len(sp) == 1
        assert any(v == "val" for v in split.values())


def test_split_does_not_balloon_val_with_coarse_groups():
    items = _items(3, 40, "base", "b")        # 3 nhóm to, mục tiêu val 18
    split = split_by_group(items, 0.15, random.Random(0))
    n_val = sum(1 for it in items if split[str(it.image)] == "val")
    assert n_val == 40                                       # đúng 1 nhóm, không phải 2


def test_sample_bucket_spreads_sources():
    items = _items(1, 100, "base", "big") + _items(1, 10, "base", "small")
    picked = sample_bucket(items, 20, random.Random(0))
    by = {s: sum(1 for p in picked if p.source == s) for s in ("big", "small")}
    assert len(picked) == 20 and by["small"] == 10


def test_sample_bucket_splits_evenly_when_both_sources_are_large():
    """Hồi quy: trước đây nguồn nhỏ hơn bị chọn lại liên tục và lấy hết phần."""
    items = _items(1, 2000, "base", "a") + _items(1, 17000, "base", "b")
    picked = sample_bucket(items, 181, random.Random(0))
    by = {s: sum(1 for p in picked if p.source == s) for s in ("a", "b")}
    assert len(picked) == 181 and by == {"a": 90, "b": 91}


def test_dedupe_and_load_source(tmp_path: Path):
    imgs, lbls = tmp_path / "images", tmp_path / "labels"
    imgs.mkdir(), lbls.mkdir()
    import cv2
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    names = ("clipA_00001.0s", "clipA_00002.0s", "clipB_00001.0s", "nolabel")
    for i, name in enumerate(names):
        cv2.imwrite(str(imgs / f"{name}.jpg"), img + 40 * i)   # ảnh khác nhau
    (lbls / "clipA_00001.0s.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    (lbls / "clipA_00002.0s.txt").write_text("", encoding="utf-8")
    (lbls / "clipB_00001.0s.txt").write_text("", encoding="utf-8")
    spec = FinetuneSource(name="t", role="domain", images=imgs, labels=lbls,
                          classes={0: "fire", 1: "smoke"},
                          group_regex=r"^(.*)_\d+\.\d+s$")
    items, st = load_source(spec, lambda p: p)
    assert st.images_seen == 4 and st.images_no_label == 1 and len(items) == 3
    assert {it.group for it in items} == {"t:clipA", "t:clipB"}
    bucket_items(items, "domain")
    assert sorted(it.bucket for it in items) == ["neg_domain", "neg_domain",
                                                 "pos_domain"]
    deduped, n = dedupe(items + [items[0]])
    assert n == 1 and len(deduped) == 3


def test_finetune_config_validation():
    cfg = FinetuneConfig(ratios={"pos_domain": 2, "neg_domain": 2, "base": 1})
    assert cfg.ratios["base"] == pytest.approx(0.2)
    with pytest.raises(ValueError):
        FinetuneConfig(ratios={"pos": 1, "neg_domain": 1, "base": 1})
    assert Config().finetune.sources == []


def test_pool_by_prefix_caps_each_prefix_then_pool(tmp_path):
    from firewatch.datamix import source_images
    for pre, n in {"smoke_": 6, "fire_": 3, "other_": 2}.items():
        for i in range(n):
            (tmp_path / f"{pre}{i}.jpg").write_bytes(b"x")
    spec = FinetuneSource(name="s", role="base", images=tmp_path,
                          classes={"0": "fire"},
                          pool_by_prefix={"smoke_": 2, "fire_": 5})
    got = [p.stem for p in source_images(spec, tmp_path)]
    assert sum(s.startswith("smoke_") for s in got) == 2
    assert sum(s.startswith("fire_") for s in got) == 3
    assert sum(s.startswith("other_") for s in got) == 2
    assert got == sorted(got)
    spec2 = FinetuneSource(name="s", role="base", images=tmp_path,
                           classes={"0": "fire"}, pool_by_prefix={"smoke_": 2}, pool=4)
    assert len(source_images(spec2, tmp_path)) == 4
