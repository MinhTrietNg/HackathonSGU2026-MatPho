"""Synthetic-copy selection and train / val list files."""

from pathlib import Path

from firewatch.trainlists import (clip_repeats, epoch_mix, unit, wants_copy,
                                  write_lists)


def _row(name, split, bucket, variant="goc", clip="", camera="", context="",
         fire=1, source="dfire_train"):
    return {"_name": name, "image": f"images/{split}/{name}.jpg", "split": split,
            "bucket": bucket, "variant": variant, "clip_id": clip, "camera": camera,
            "context": context, "n_fire": fire, "n_smoke": 0, "source": source}


def test_copies_go_to_a_share_of_base_and_all_domain():
    base = [_row(f"b{i}", "train", "base") for i in range(2000)]
    share = sum(wants_copy(r, "xam", 0.3) for r in base) / len(base)
    assert 0.26 < share < 0.34
    both = sum(wants_copy(r, "xam", 0.3) and wants_copy(r, "cam", 0.3) for r in base)
    assert both < 0.15 * len(base)                    # hai loại rơi vào ảnh khác nhau
    assert not wants_copy(_row("v", "val", "base"), "xam", 1.0)
    assert wants_copy(_row("d", "train", "pos_domain"), "xam", 0.0)
    assert wants_copy(_row("d", "val", "neg_domain"), "cam", 0.0)
    assert not wants_copy(_row("d", "val", "neg_domain"), "cam", 0.0, False)
    assert unit("a", "xam") == unit("a", "xam") != unit("a", "cam")


def test_repeats_favour_cctv_and_skip_news():
    rows = ([_row(f"t{i}", "train", "pos_domain", clip="tin", camera="tin_tuc",
                  context="ngoai") for i in range(50)]
            + [_row(f"c{i}", "train", "pos_domain", clip="cam", camera="cctv",
                    context="ngoai") for i in range(3)]
            + [_row(f"h{i}", "train", "pos_domain", clip="ham", camera="tin_tuc",
                    context="ham") for i in range(10)]
            + [_row("v", "val", "pos_domain", clip="cam", camera="cctv")])
    rep = clip_repeats(rows, 20, {"cctv": 4, "ham": 4}, default_cap=1)
    assert rep == {"tin": 1, "cam": 4, "ham": 2}


def test_news_basement_clip_is_capped_at_two():
    rows = ([_row(f"h{i}", "train", "pos_domain", clip="ham_tin", camera="tin_tuc",
                  context="ham") for i in range(4)]
            + [_row(f"c{i}", "train", "pos_domain", clip="ham_cctv", camera="cctv",
                    context="ham") for i in range(4)]
            + [_row(f"q{i}", "train", "pos_domain", clip="tay", camera="quay_tay",
                    context="ngoai") for i in range(4)])
    caps = {"cctv": 4, "ham": 4, "tret": 4, "quay_tay": 2}
    assert clip_repeats(rows, 20, caps, 1) == {"ham_tin": 4, "ham_cctv": 4, "tay": 2}
    rep = clip_repeats(rows, 20, caps, 1, camera_max={"tin_tuc": 2})
    assert rep == {"ham_tin": 2, "ham_cctv": 4, "tay": 2}


def test_lists_keep_val_to_originals(tmp_path: Path):
    rows = [_row("a", "train", "base"), _row("a_xam", "train", "base", "xam_ir"),
            _row("d", "train", "pos_domain", clip="cam", camera="cctv"),
            _row("n", "train", "neg_domain", fire=0),
            _row("vb", "val", "base"), _row("vd", "val", "pos_domain", clip="x"),
            _row("vd_xam", "val", "pos_domain", "xam_ir", clip="x")]
    n = write_lists(tmp_path, rows, {"cam": 3}, neg_domain_repeat=2)
    assert n == {"train.txt": 7, "val.txt": 2, "val_domain.txt": 1,
                 "val_domain_bien_the.txt": 1}
    train = (tmp_path / "train.txt").read_text().split()
    assert train.count("./images/train/d.jpg") == 3
    assert train.count("./images/train/n.jpg") == 2
    assert (tmp_path / "val.txt").read_text().split() == [
        "./images/val/vb.jpg", "./images/val/vd.jpg"]
    mix = epoch_mix(rows, {"cam": 3})
    assert mix == {"dung_mien": 60.0, "dfire_train": 40.0}
