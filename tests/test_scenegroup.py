"""Grouping of public images cut from one clip / camera."""

from pathlib import Path

import cv2
import numpy as np

from firewatch.scenegroup import merge_groups, scene_links, sequence_key, thumbnails


def _scene(seed: int, shift: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = cv2.resize(rng.integers(0, 255, (6, 8), dtype=np.uint8), (160, 120),
                     interpolation=cv2.INTER_CUBIC)
    return np.roll(img, shift, axis=1)


def test_sequence_key():
    assert sequence_key("AoF05098") == ("AoF", 5098)
    assert sequence_key("smoke_CV018975") == ("smoke_CV", 18975)
    assert sequence_key("khong_so") is None


def test_links_join_same_clip_but_not_strangers(tmp_path: Path):
    paths = []
    for name, img in (("AoF00010", _scene(1)), ("AoF00013", _scene(1, 3)),
                      ("AoF00500", _scene(1, 3)), ("WEB00011", _scene(2)),
                      ("WEB00012", np.full((120, 160), 90, np.uint8))):
        p = tmp_path / f"{name}.jpg"
        cv2.imwrite(str(p), img)
        paths.append(p)
    th = thumbnails(paths)
    assert np.isnan(th[4]).all()                       # ảnh phẳng không so được
    corr = float(np.nan_to_num(th[0]) @ np.nan_to_num(th[1])) / 256
    assert 0.90 <= corr < 0.98                          # khung lệch nhẹ
    links = scene_links([p.stem for p in paths], ["d"] * 5, th)
    assert (0, 1) in links                              # cùng chuỗi tên, gần nhau
    assert (1, 2) in links                              # y hệt, dù xa số
    assert (0, 2) not in links                          # xa số, chỉ ~0,96
    assert all(4 not in pair and 3 not in pair for pair in links)
    far = scene_links([p.stem for p in paths], ["d"] * 5, th, seq_window=2)
    assert (0, 1) not in far                           # khoảng số 3 > cửa sổ 2


def test_merge_groups_keeps_old_groups_and_is_order_free():
    groups = ["dfire:a", "dfire:b", "dfire:c", "clip:x", "clip:x"]
    out = merge_groups(groups, [(1, 2)])
    assert out == ["dfire:a", "dfire:b", "dfire:b", "clip:x", "clip:x"]
    out2 = merge_groups(groups, [(4, 0), (2, 1)][::-1])
    assert out2[0] == out2[3] == out2[4] == "clip:x"
    assert out2[1] == out2[2] == "dfire:b"
