"""``docs/mau_event.json`` là hợp đồng với backend: phải khớp đúng schema event.

File mẫu được xuất từ payload webhook của một lần chạy thật bằng
``tools/xuat_mau_event.py``. Test này hỏng khi schema thêm hay bớt trường mà
file mẫu chưa được xuất lại.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from firewatch.alerts import Event, EventBox

MAU = Path(__file__).resolve().parents[1] / "docs" / "mau_event.json"


def test_mau_event_co_dung_tap_truong_cua_schema():
    d = json.loads(MAU.read_text(encoding="utf-8"))
    assert set(d) == set(Event.model_fields)
    for box in d["boxes"]:
        assert set(box) == set(EventBox.model_fields)
    ev = Event.model_validate(d)
    assert json.loads(ev.model_dump_json()) == d, "mẫu phải đi lại nguyên vẹn"


def test_mau_event_gia_tri_hop_le():
    ev = Event.model_validate_json(MAU.read_text(encoding="utf-8"))
    assert ev.type == "created"
    assert ev.frame_w > 0 and ev.frame_h > 0 and ev.frame_ts > 0
    assert ev.boxes
    for b in ev.boxes:
        assert b.cls in ("fire", "smoke") and 0 <= b.conf <= 1
        x1, y1, x2, y2 = b.xyxy
        assert 0 <= x1 < x2 <= ev.frame_w and 0 <= y1 < y2 <= ev.frame_h
        # xyxy trong JSON đã làm tròn 0,1 px, nên so với dung sai nhỏ
        mong = [x1 / ev.frame_w, y1 / ev.frame_h, x2 / ev.frame_w, y2 / ev.frame_h]
        assert all(abs(a - b_) < 1e-3 for a, b_ in zip(b.xyxyn, mong))
    jpeg = base64.b64decode(ev.snapshot_base64)
    assert jpeg[:2] == b"\xff\xd8" and len(jpeg) <= 200 * 1024
