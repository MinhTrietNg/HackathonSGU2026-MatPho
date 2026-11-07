"""Hợp đồng webhook đã chốt với backend: hai header xác thực, payload là event đủ."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Iterator

import pytest

from firewatch.alerts import Event, EventStore, EventBox, VLMResult, WebhookSink
from firewatch.config import Config

TRUONG_EVENT = {"event_id", "camera_id", "context", "severity", "verification",
                "started_at", "video_ts_sec", "boxes", "vlm", "snapshot_path"}


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
        boxes=[EventBox(cls="fire", conf=0.87, xyxy=[1, 2, 3, 4])],
        vlm=VLMResult(is_fire=True, is_smoke=False, confidence=0.9,
                      description_vi="Lửa trên yên xe.", fire_type="UNCONTROLLED"),
        snapshot_path="events/x.jpg")


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
