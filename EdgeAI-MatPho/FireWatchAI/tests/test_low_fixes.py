"""Regression tests for the low-severity fixes: JPEG writer, AP speed/equality,
event retention, suppressed notifications, webhook 4xx handling."""

import io
import json
import os
import random
import time
import urllib.error
from pathlib import Path

import numpy as np

from firewatch.alerts import Event, EventStore, WebhookSink
from firewatch.annotate import write_jpeg
from firewatch.config import Config
from firewatch.evalkit import average_precision


def test_write_jpeg_handles_unicode_path(tmp_path: Path):
    p = tmp_path / "ảnh cháy xe" / "khung số 1.jpg"
    p.parent.mkdir()
    assert write_jpeg(p, np.zeros((8, 8, 3), dtype=np.uint8), 80) is True
    assert p.stat().st_size > 0
    missing_dir = tmp_path / "khong_ton_tai" / "x.jpg"
    assert write_jpeg(missing_dir, np.zeros((8, 8, 3), dtype=np.uint8)) is False


def _naive_ap(records, n_gt):
    records = sorted(records, key=lambda r: -r[0])
    tp = fp = 0
    precisions, recalls = [], []
    for _, is_tp in records:
        tp += is_tp
        fp += not is_tp
        precisions.append(tp / (tp + fp))
        recalls.append(tp / n_gt)
    ap, prev = 0.0, 0.0
    for i in range(len(records)):
        ap += (recalls[i] - prev) * max(precisions[i:])
        prev = recalls[i]
    return ap


def test_average_precision_matches_naive_and_is_fast():
    rng = random.Random(0)
    for _ in range(20):
        n = rng.randint(1, 60)
        recs = [(rng.random(), rng.random() < 0.6) for _ in range(n)]
        n_gt = max(1, sum(tp for _, tp in recs) + rng.randint(0, 5))
        assert abs(average_precision(recs, n_gt) - _naive_ap(recs, n_gt)) < 1e-12
    big = [(rng.random(), rng.random() < 0.5) for _ in range(50_000)]
    t0 = time.perf_counter()
    average_precision(big, 30_000)
    assert time.perf_counter() - t0 < 1.0


def test_event_retention_prunes_old_files(tmp_path: Path):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    cfg = Config(alerts={"events_dir": str(events_dir)}, root=tmp_path)
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    old = store.create(severity="WARNING", verification="UNVERIFIED", video_ts=1.0,
                       detections=[], image=np.zeros((4, 4, 3), dtype=np.uint8))
    new = store.create(severity="WARNING", verification="UNVERIFIED", video_ts=2.0,
                       detections=[], image=np.zeros((4, 4, 3), dtype=np.uint8))
    ancient = time.time() - 10 * 86400
    for p in events_dir.iterdir():
        if old.event_id[:8] in p.name:
            os.utime(p, (ancient, ancient))
    cfg2 = Config(alerts={"events_dir": str(events_dir), "keep_days": 7},
                  root=tmp_path)
    store2 = EventStore(cfg2.alerts, cfg2.camera, cfg2)
    ids = {e.event_id for e in store2.all()}
    assert ids == {new.event_id}
    assert all(old.event_id[:8] not in p.name for p in events_dir.iterdir())


def test_suppressed_can_be_kept_off_the_wire(tmp_path: Path):
    alerts = {"events_dir": str(tmp_path / "ev"), "notify_suppressed": False}
    cfg = Config(alerts=alerts, root=tmp_path)
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    seen = []
    store.subscribe(lambda e, kind: seen.append((e.verification, kind)))
    store.create(severity="CRITICAL", verification="SUPPRESSED", video_ts=1.0,
                 detections=[], image=None)
    store.create(severity="CRITICAL", verification="UNVERIFIED", video_ts=2.0,
                 detections=[], image=None)
    assert seen == [("UNVERIFIED", "created")]
    assert len(store) == 2                                  # vẫn ghi đĩa cả hai
    assert len(list((tmp_path / "ev").glob("*.json"))) == 2


def test_webhook_does_not_retry_on_4xx(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 422, "Unprocessable", {},
                                     io.BytesIO())

    monkeypatch.setattr("firewatch.alerts.urllib.request.urlopen", fake_urlopen)
    sink = WebhookSink("http://backend.local/hook", token=None, timeout_s=1, retries=3)
    ev = Event(**json.loads(Event.model_validate_json(
        '{"event_id":"e1","camera_id":"c","context":"HAM","severity":"WARNING",'
        '"verification":"UNVERIFIED","started_at":"2026-11-02T00:00:00+07:00",'
        '"video_ts_sec":1.0,"boxes":[],"vlm":null,"snapshot_path":"",'
        '"frame_w":640,"frame_h":360,"frame_ts":1762016400.0}'
    ).model_dump_json()))
    sink._post(ev)
    assert len(calls) == 1

    calls.clear()

    def fake_urlopen_500(req, timeout):
        calls.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 503, "Unavailable", {}, io.BytesIO())

    monkeypatch.setattr("firewatch.alerts.urllib.request.urlopen", fake_urlopen_500)
    sink._post(ev)
    assert len(calls) == 4                                  # 1 + 3 retry với 5xx


def test_pipeline_uses_given_store_even_when_empty(tmp_path: Path):
    """serve chia store với API: store rỗng (falsy vì __len__) vẫn phải được dùng."""
    from firewatch.pipeline import Pipeline
    cfg = Config(alerts={"events_dir": str(tmp_path / "events")}, root=tmp_path)
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    assert len(store) == 0 and not store
    assert Pipeline(cfg, "khong_dung.mp4", store=store)._event_store() is store
