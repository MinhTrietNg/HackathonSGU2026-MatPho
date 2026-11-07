"""Payload webhook của FireWatch phải qua được model Pydantic thật của backend.

Backend (``backend/src/models/fire_alert.py``) kiểm mọi event bằng
``AIFireEventPayload``; payload sai kiểu thì trả 422 và cảnh báo mất. Cổng nút
biên (``EdgeAI-MatPho/edge_backend``) chuyển nguyên payload lên đó và gửi ảnh
riêng bằng ``AISnapshotUploadPayload``.

Model thật được nạp từ thư mục ``backend/`` cạnh ``FireWatchAI/`` (repo gốc) hoặc
cạnh ``EdgeAI-MatPho/`` (khi FireWatchAI nằm ở ``EdgeAI-MatPho/ai_service``).
Không thấy thì các test dùng model thật được bỏ qua; test kiểu trường thời gian
vẫn chạy.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType

import pytest

from firewatch.alerts import Event, gio_iso, sample_event

GOC = Path(__file__).resolve().parents[1]
MAU = GOC / "docs" / "mau_event.json"
TEN_GOI = "_backend_models_hop_dong"


def _thu_muc_model() -> Path | None:
    for cha in (GOC.parent, GOC.parent.parent):
        d = cha / "backend" / "src" / "models"
        if (d / "fire_alert.py").is_file() and (d / "common.py").is_file():
            return d
    return None


def _nap_model() -> ModuleType | None:
    """Nạp ``fire_alert`` của backend như một gói riêng (thư mục không có
    ``__init__.py``, ``fire_alert`` import tương đối ``.common``)."""
    d = _thu_muc_model()
    if d is None:
        return None
    if f"{TEN_GOI}.fire_alert" in sys.modules:
        return sys.modules[f"{TEN_GOI}.fire_alert"]
    goi = ModuleType(TEN_GOI)
    goi.__path__ = [str(d)]
    sys.modules[TEN_GOI] = goi
    for ten in ("common", "fire_alert"):
        spec = importlib.util.spec_from_file_location(f"{TEN_GOI}.{ten}",
                                                      d / f"{ten}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[f"{TEN_GOI}.fire_alert"]


BE = _nap_model()
can_backend = pytest.mark.skipif(BE is None, reason="không thấy backend/src/models")


def _payload_co_bat() -> dict:
    """Payload webhook của một event cờ bật (đủ trường sự cố và verifier)."""
    ev = Event.model_validate(json.loads(MAU.read_text(encoding="utf-8")))
    return json.loads(ev.model_dump_json())


def _payload_co_tat() -> dict:
    return json.loads(sample_event().model_dump_json())


@can_backend
@pytest.mark.parametrize("tao", [_payload_co_bat, _payload_co_tat],
                         ids=["co_bat", "co_tat"])
def test_payload_qua_model_backend(tao):
    d = tao()
    p = BE.AIFireEventPayload.model_validate(d)
    assert p.event_id == d["event_id"] and p.camera_id == d["camera_id"]
    assert p.type == d["type"]
    assert len(p.boxes) == len(d["boxes"])


@can_backend
def test_payload_updated_ended_qua_model_backend():
    d = _payload_co_bat()
    d.update(type="updated", status="ended", luot_xac_minh=2)
    d.pop("snapshot_base64", None)
    p = BE.AIFireEventPayload.model_validate(d)
    assert (p.type, p.status, p.luot_xac_minh) == ("updated", "ended", 2)
    assert p.last_seen_ts == d["last_seen_ts"]


@can_backend
def test_anh_qua_model_upload_cua_backend():
    """Cổng nút biên tách ảnh và gửi bằng body này (pha 2)."""
    d = _payload_co_bat()
    body = {"event_id": d["event_id"], "cam_id": d["camera_id"],
            "camera_id": d["camera_id"],
            "frame_ts": d.get("frame_ts") or d.get("last_seen_ts"),
            "frame_w": d["frame_w"], "frame_h": d["frame_h"],
            "boxes": d["boxes"], "snapshot_base64": d["snapshot_base64"]}
    BE.AISnapshotUploadPayload.model_validate(body)


def test_truong_thoi_gian_la_chuoi_iso():
    """Backend khai báo ``started_at`` và ``last_seen_ts`` là chuỗi."""
    d = _payload_co_bat()
    for k in ("started_at", "last_seen_ts"):
        assert isinstance(d[k], str), k
        assert datetime.fromisoformat(d[k]).tzinfo is not None, k


def test_event_cu_ghi_giay_unix_duoc_doi_khi_nap():
    d = _payload_co_tat()
    d.update(status="open", last_seen_ts=1794065417.059, luot_xac_minh=1)
    ev = Event.model_validate(d)
    assert ev.last_seen_ts == gio_iso(1794065417.059)
    assert abs(datetime.fromisoformat(ev.last_seen_ts).timestamp()
               - 1794065417.059) < 1e-3
