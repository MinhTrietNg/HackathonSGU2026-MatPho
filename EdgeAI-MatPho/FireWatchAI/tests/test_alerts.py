"""Event schema (agreed with the backend) and the on-disk store."""

import json
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from firewatch.alerts import Event, EventStore, VLMResult, sample_event
from firewatch.config import Config
from firewatch.detector import Detection

SCHEMA_KEYS = {"event_id", "camera_id", "context", "severity", "verification",
               "started_at", "video_ts_sec", "boxes", "vlm", "snapshot_path",
               "type", "frame_w", "frame_h", "frame_ts"}


def test_event_schema_keys_are_exactly_the_agreed_ones():
    assert set(sample_event().model_dump().keys()) == SCHEMA_KEYS
    box_keys = set(sample_event().model_dump()["boxes"][0].keys())
    assert box_keys == {"cls", "conf", "xyxy", "xyxyn"}
    # fire_type nằm TRONG object vlm (nullable, backend đọc lỏng); top-level không đổi
    assert set(sample_event().model_dump()["vlm"].keys()) == {
        "is_fire", "is_smoke", "confidence", "description_vi", "fire_type"}


def test_event_rejects_bad_enums():
    good = sample_event().model_dump()
    with pytest.raises(ValidationError):
        Event(**{**good, "severity": "HIGH"})
    with pytest.raises(ValidationError):
        Event(**{**good, "context": "SAN"})
    with pytest.raises(ValidationError):
        Event(**{**good, "verification": "MAYBE"})


def test_store_writes_json_and_snapshot(tmp_path: Path):
    cfg = Config(alerts={"events_dir": str(tmp_path / "events")},
                 camera={"id": "camX", "context": "TRET"}, root=tmp_path)
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    got = []
    store.subscribe(lambda e, kind: got.append((e, kind)))
    img = np.zeros((120, 160, 3), dtype=np.uint8)
    det = Detection("fire", 0, 0.91, (10.0, 20.0, 60.0, 80.0))
    ev = store.create(severity="CRITICAL", verification="UNVERIFIED", video_ts=12.34,
                      detections=[det], image=img)
    assert got == [(ev, "created")] and len(store) == 1
    assert store.get(ev.event_id) is ev
    assert ev.camera_id == "camX" and ev.context == "TRET"
    assert ev.boxes[0].cls == "fire" and ev.video_ts_sec == 12.34
    snap = tmp_path / ev.snapshot_path
    assert snap.is_file() and snap.suffix == ".jpg"
    jsons = list((tmp_path / "events").glob("*.json"))
    assert len(jsons) == 1
    on_disk = json.loads(jsons[0].read_text(encoding="utf-8"))
    assert set(on_disk) == SCHEMA_KEYS and on_disk["event_id"] == ev.event_id


def test_update_patches_verdict_in_place_and_notifies(tmp_path: Path):
    cfg = Config(alerts={"events_dir": str(tmp_path / "events")}, root=tmp_path)
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    kinds = []
    store.subscribe(lambda e, kind: kinds.append(kind))
    ev = store.create(severity="CRITICAL", verification="UNVERIFIED", video_ts=3.0,
                      detections=[], image=None)
    vlm = VLMResult(is_fire=False, is_smoke=False, confidence=0.8, description_vi="x")
    upd = store.update(ev.event_id, verification="SUPPRESSED", vlm=vlm)
    assert upd is not None and upd.event_id == ev.event_id
    assert store.get(ev.event_id).verification == "SUPPRESSED"
    assert kinds == ["created", "updated"]
    on_disk = json.loads(next((tmp_path / "events").glob("*.json"))
                         .read_text(encoding="utf-8"))
    assert on_disk["verification"] == "SUPPRESSED"
    assert on_disk["vlm"]["is_fire"] is False
    assert len(list((tmp_path / "events").glob("*.json"))) == 1   # ghi đè, không thêm
    assert store.update("khong-co", verification="VERIFIED", vlm=None) is None


def test_store_reloads_existing_events(tmp_path: Path):
    cfg = Config(alerts={"events_dir": str(tmp_path / "events")}, root=tmp_path)
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    store.create(severity="WARNING", verification="UNVERIFIED", video_ts=1.0,
                 detections=[], image=None)
    again = EventStore(cfg.alerts, cfg.camera, cfg)
    assert len(again) == 1 and again.all()[0].severity == "WARNING"


def test_event_cu_tren_dia_van_nap_duoc(tmp_path: Path):
    """JSON ghi trước khi có type / frame_* / xyxyn vẫn được nạp lại."""
    d = tmp_path / "events"
    d.mkdir()
    (d / "20261102_000000_cu.json").write_text(
        '{"event_id":"cu","camera_id":"c","context":"HAM","severity":"WARNING",'
        '"verification":"UNVERIFIED","started_at":"2026-11-02T00:00:00+07:00",'
        '"video_ts_sec":1.0,"boxes":[{"cls":"fire","conf":0.5,"xyxy":[1,2,3,4]}],'
        '"vlm":null,"snapshot_path":""}', encoding="utf-8")
    cfg = Config(alerts={"events_dir": str(d)}, root=tmp_path)
    ev = EventStore(cfg.alerts, cfg.camera, cfg).get("cu")
    assert ev is not None and ev.type == "created" and ev.frame_w == 0
