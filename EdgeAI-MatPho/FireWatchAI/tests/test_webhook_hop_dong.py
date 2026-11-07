"""Hợp đồng webhook đã chốt với backend: hai header xác thực, payload là event đủ,
``type`` created / updated, box có ``xyxyn``, khung có ``frame_w`` / ``frame_h`` /
``frame_ts``, và ``snapshot_base64`` khi ``webhook.gui_anh`` bật."""
from __future__ import annotations

import base64
import json
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
import pytest

from firewatch.alerts import (Event, EventStore, EventBox, VLMResult, WebhookSink,
                              nen_jpeg_duoi)
from firewatch.config import Config
from firewatch.detector import Detection

TRUONG_EVENT = {"event_id", "camera_id", "context", "severity", "verification",
                "started_at", "video_ts_sec", "boxes", "vlm", "snapshot_path",
                "type", "frame_w", "frame_h", "frame_ts"}
TRUONG_BOX = {"cls", "conf", "xyxy", "xyxyn"}
ANH = np.full((360, 640, 3), 128, dtype=np.uint8)
DET = Detection("fire", 0, 0.91, (64.0, 36.0, 320.0, 180.0))


class _MayNhan(BaseHTTPRequestHandler):
    """Backend giả: ghi lại header và body của mỗi POST."""

    nhan: list[tuple[dict[str, str], bytes]] = []

    def do_POST(self) -> None:  # noqa: N802 - tên do http.server quy định
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        _MayNhan.nhan.append((dict(self.headers.items()), body))
        self.send_response(202)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        """Không in log truy cập ra stderr khi chạy test."""


@pytest.fixture()
def may_nhan() -> Iterator[str]:
    """Chạy backend giả trên cổng ngẫu nhiên của localhost, trả về URL."""
    _MayNhan.nhan = []
    server = HTTPServer(("127.0.0.1", 0), _MayNhan)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api/v1/internal/ai/fire-events"
    finally:
        server.shutdown()
        server.server_close()


def _event() -> Event:
    return Event(
        event_id="e-hop-dong", camera_id="cam01", context="NGOAI",
        severity="CRITICAL", verification="VERIFIED",
        started_at="2026-11-07T19:00:00+07:00", video_ts_sec=5.0,
        boxes=[EventBox(cls="fire", conf=0.87, xyxy=[64, 36, 320, 180],
                        xyxyn=[0.1, 0.1, 0.5, 0.5])],
        vlm=VLMResult(is_fire=True, is_smoke=False, confidence=0.9,
                      description_vi="Lửa trên yên xe.", fire_type="UNCONTROLLED"),
        snapshot_path="events/x.jpg", frame_w=640, frame_h=360,
        frame_ts=1762516800.0)


def test_co_token_thi_gui_ca_hai_header_va_event_day_du(may_nhan: str):
    ev = _event()
    WebhookSink(may_nhan, token="bi-mat", timeout_s=2, retries=0)._post(ev)
    assert len(_MayNhan.nhan) == 1
    headers, body = _MayNhan.nhan[0]
    assert headers["Authorization"] == "Bearer bi-mat"
    assert headers["X-Internal-Secret"] == "bi-mat"
    assert headers["Content-Type"] == "application/json"
    payload = json.loads(body)
    assert set(payload) == TRUONG_EVENT
    assert payload == json.loads(ev.model_dump_json())


def test_khong_token_thi_khong_gui_header_xac_thuc(may_nhan: str):
    WebhookSink(may_nhan, token=None, timeout_s=2, retries=0)._post(_event())
    headers, _ = _MayNhan.nhan[0]
    assert "Authorization" not in headers
    assert "X-Internal-Secret" not in headers


def test_token_rong_trong_env_coi_nhu_khong_co(may_nhan: str, tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FW_URL_THU", may_nhan)
    monkeypatch.setenv("FW_TOKEN_THU", "   ")
    cfg = Config(alerts={"events_dir": str(tmp_path / "ev"),
                         "webhook_url_env": "FW_URL_THU",
                         "webhook_token_env": "FW_TOKEN_THU"}, root=tmp_path)
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    assert store.webhook is not None and store.webhook.token is None
    store.webhook._post(_event())
    headers, _ = _MayNhan.nhan[0]
    assert "X-Internal-Secret" not in headers


# ------------------------------------------------------------- 3A: trường mới
def _store(tmp_path: Path, url: str, monkeypatch: pytest.MonkeyPatch,
           **webhook) -> EventStore:
    monkeypatch.setenv("FW_URL_THU", url)
    monkeypatch.setenv("FW_TOKEN_THU", "bi-mat")
    cfg = Config(alerts={"events_dir": str(tmp_path / "ev"),
                         "webhook_url_env": "FW_URL_THU",
                         "webhook_token_env": "FW_TOKEN_THU"},
                 webhook=webhook, root=tmp_path)
    return EventStore(cfg.alerts, cfg.camera, cfg)


def _cho_nhan(n: int, giay: float = 3.0) -> list[dict]:
    het = time.monotonic() + giay
    while len(_MayNhan.nhan) < n:
        assert time.monotonic() < het, "backend giả không nhận đủ POST"
        time.sleep(0.01)
    return [json.loads(b) for _, b in _MayNhan.nhan]


def test_created_roi_updated_cung_event_id_va_toa_do(may_nhan, tmp_path,
                                                      monkeypatch):
    store = _store(tmp_path, may_nhan, monkeypatch)
    started = datetime.fromisoformat("2026-11-07T19:00:00+07:00")
    ev = store.create(severity="CRITICAL", verification="UNVERIFIED", video_ts=5.0,
                      detections=[DET], image=ANH, started_at=started)
    _cho_nhan(1)
    store.update(ev.event_id, verification="VERIFIED", vlm=VLMResult(
        is_fire=True, is_smoke=True, confidence=0.9, description_vi="x"))
    dau, sau = _cho_nhan(2)
    assert (dau["type"], sau["type"]) == ("created", "updated")
    assert dau["event_id"] == sau["event_id"] == ev.event_id
    for p in (dau, sau):
        assert set(p) == TRUONG_EVENT, "gui_anh tắt: không có snapshot_base64"
        assert set(p["boxes"][0]) == TRUONG_BOX
        assert (p["frame_w"], p["frame_h"]) == (640, 360)
        assert p["frame_ts"] == started.timestamp()
        assert p["boxes"][0]["xyxy"] == [64.0, 36.0, 320.0, 180.0]
        assert p["boxes"][0]["xyxyn"] == [0.1, 0.1, 0.5, 0.5]
        assert 0 <= p["boxes"][0]["conf"] <= 1
    tren_dia = json.loads(next((tmp_path / "ev").glob("*.json")).read_text("utf-8"))
    assert tren_dia["type"] == "updated" and "snapshot_base64" not in tren_dia


def test_gui_dung_thu_tu_phat(may_nhan, tmp_path, monkeypatch):
    """Một thread gửi FIFO: backend nhận đúng thứ tự created, updated..."""
    store = _store(tmp_path, may_nhan, monkeypatch)
    ids = []
    for i in range(5):
        ev = store.create(severity="CRITICAL", verification="UNVERIFIED",
                          video_ts=float(i), detections=[DET], image=ANH)
        store.update(ev.event_id, verification="UNVERIFIED", vlm=None)
        ids.append(ev.event_id)
    nhan = [(p["event_id"], p["type"]) for p in _cho_nhan(10)]
    assert nhan == [(e, k) for e in ids for k in ("created", "updated")]


def test_nhac_lai_gui_type_updated(may_nhan, tmp_path, monkeypatch):
    store = _store(tmp_path, may_nhan, monkeypatch)
    ev = store.create(severity="CRITICAL", verification="UNVERIFIED", video_ts=1.0,
                      detections=[DET], image=ANH)
    store.renotify(ev.event_id, "escalated")
    assert [p["type"] for p in _cho_nhan(2)] == ["created", "updated"]


def test_gui_anh_bat_thi_co_snapshot_base64_goc_duoi_200kb(may_nhan, tmp_path,
                                                         monkeypatch):
    rng = np.random.default_rng(0)
    nhieu = rng.integers(0, 256, (1080, 1920, 3), dtype=np.uint8)  # khó nén
    store = _store(tmp_path, may_nhan, monkeypatch, gui_anh=True)
    ev = store.create(severity="CRITICAL", verification="UNVERIFIED", video_ts=1.0,
                      detections=[DET], image=nhieu)
    store.update(ev.event_id, verification="UNVERIFIED", vlm=None)
    for p in _cho_nhan(2):
        assert set(p) == TRUONG_EVENT | {"snapshot_base64"}
        jpeg = base64.b64decode(p["snapshot_base64"])
        assert len(jpeg) <= 200 * 1024 and jpeg[:2] == b"\xff\xd8"
        anh = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        h, w = anh.shape[:2]
        assert abs(w / h - 1920 / 1080) < 0.01, "giữ tỉ lệ khung gốc"
    # chỉ trong webhook: không trong JSON trên đĩa, REST hay subscriber
    assert "snapshot_base64" not in store.get(ev.event_id).model_dump()
    assert "snapshot_base64" not in next((tmp_path / "ev").glob("*.json")).read_text(
        "utf-8")


def test_anh_goc_khong_ve_box():
    """Keyframe gửi đi là ảnh gốc: ảnh xám phẳng giữ nguyên sau khi nén."""
    jpeg = nen_jpeg_duoi(ANH, 200)
    anh = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert anh.shape == ANH.shape
    assert np.abs(anh.astype(int) - 128).max() <= 2


def test_nen_jpeg_duoi_thu_nho_khi_can():
    rng = np.random.default_rng(1)
    nhieu = rng.integers(0, 256, (720, 1280, 3), dtype=np.uint8)
    jpeg = nen_jpeg_duoi(nhieu, 50)
    assert len(jpeg) <= 50 * 1024
