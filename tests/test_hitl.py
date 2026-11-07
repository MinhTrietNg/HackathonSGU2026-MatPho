"""Hard-negative export when the operator dismisses a controlled fire."""

import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from firewatch.acks import Ack
from firewatch.alerts import EventStore, VLMResult
from firewatch.config import Config
from firewatch.detector import Detection
from firewatch.hitl import export_hard_negative
from firewatch.server import create_app

IMG = np.full((120, 160, 3), 60, dtype=np.uint8)
DET = Detection(cls_name="fire", cls_id=0, conf=0.7, xyxy=(10.0, 10.0, 60.0, 60.0))


def _setup(tmp_path: Path, raw: bool = True):
    cfg = Config(alerts={"events_dir": str(tmp_path / "events"),
                         "save_raw_keyframe": raw,
                         "hitl_negatives_dir": str(tmp_path / "hitl")},
                 camera={"id": "cam07", "context": "NGOAI"}, root=tmp_path)
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    vlm = VLMResult(is_fire=True, is_smoke=True, confidence=0.8,
                    description_vi="Nghi lửa có kiểm soát: lò than nướng.",
                    fire_type="CONTROLLED")
    ev = store.create(severity="CRITICAL", verification="VERIFIED", video_ts=4.0,
                      detections=[DET], image=IMG, vlm=vlm)
    return cfg, store, ev


def _ack(ev, action):
    return Ack(event_id=ev.event_id, action=action, note="quán nướng đầu hẻm",
               acked_at="2026-11-03T15:00:00+07:00")


def test_export_writes_clean_keyframe_and_metadata(tmp_path: Path):
    cfg, store, ev = _setup(tmp_path)
    assert list((tmp_path / "events").glob("*_goc.jpg"))       # store lưu ảnh sạch
    out = export_hard_negative(ev, _ack(ev, "dismiss_controlled"), tmp_path,
                               tmp_path / "hitl")
    meta = json.loads(out.read_text(encoding="utf-8"))
    assert meta["image_is_raw"] is True and meta["label"] == "negative"
    assert meta["fire_type"] == "CONTROLLED" and meta["context"] == "NGOAI"
    assert meta["operator_note"] == "quán nướng đầu hẻm"
    assert meta["boxes"][0]["cls"] == "fire"
    assert (tmp_path / "hitl" / meta["image"]).is_file()
    assert (tmp_path / "hitl" / meta["image"].replace(".jpg", "_annotated.jpg")
            ).is_file()


def test_export_only_for_dismiss_and_falls_back_to_snapshot(tmp_path: Path):
    cfg, store, ev = _setup(tmp_path, raw=False)
    hitl = tmp_path / "hitl"
    assert export_hard_negative(ev, _ack(ev, "confirm"), tmp_path, hitl) is None
    assert export_hard_negative(ev, _ack(ev, "watch"), tmp_path, hitl) is None
    out = export_hard_negative(ev, _ack(ev, "dismiss_controlled"), tmp_path, hitl)
    assert json.loads(out.read_text(encoding="utf-8"))["image_is_raw"] is False


def test_dismiss_from_api_exports(tmp_path: Path):
    cfg, store, ev = _setup(tmp_path)
    client = TestClient(create_app(cfg, store))
    client.post(f"/events/{ev.event_id}/ack", json={"action": "confirm"})
    assert not (tmp_path / "hitl").exists()
    client.post(f"/events/{ev.event_id}/ack",
                json={"action": "dismiss_controlled", "note": "bếp than"})
    files = sorted(p.name for p in (tmp_path / "hitl").iterdir())
    assert len(files) == 3 and any(f.endswith(".json") for f in files)
