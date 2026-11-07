"""Tier 5 — alert sink: event schema, on-disk store, snapshots, webhook.

The JSON schema of an event is agreed with the backend team and must not
change. Every alert writes ``events/<stamp>_<id>.json`` plus an annotated
``.jpg`` keyframe, notifies in-process subscribers (the WebSocket
broadcaster) and, when configured, POSTs the event to a webhook.
"""

from __future__ import annotations

import base64
import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
from pydantic import BaseModel, Field, model_serializer

from .annotate import draw_detections, write_jpeg
from .config import AlertsConfig, CameraConfig, Config, Context, env_secret
from .detector import Detection

log = logging.getLogger(__name__)

SeverityName = Literal["WARNING", "CRITICAL"]
Verification = Literal["VERIFIED", "UNVERIFIED", "SUPPRESSED"]


class EventBox(BaseModel):
    cls: str
    conf: float
    xyxy: list[float] = Field(min_length=4, max_length=4)
    """Pixel trên khung gốc ``frame_w × frame_h`` của event."""
    xyxyn: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0],
                               min_length=4, max_length=4)
    """``xyxy`` chia cho ``frame_w``, ``frame_h``, trong [0, 1]; dùng được trên
    ảnh đã thu nhỏ (``snapshot_base64``) hay khung khác kích thước. Toàn 0 chỉ
    ở event ghi trước khi có trường này."""


def chuan_hoa_box(xyxy: tuple[float, float, float, float] | list[float],
                  w: int, h: int) -> list[float]:
    """``xyxyn`` của một box pixel.

    Parameters
    ----------
    xyxy : tuple of float
        Box pixel ``(x1, y1, x2, y2)`` trên khung ``w × h``.
    w, h : int
        Kích thước khung; ``0`` (chưa có ảnh, chỉ trong unit test) thì trả toàn 0.
    """
    if w <= 0 or h <= 0:
        return [0.0, 0.0, 0.0, 0.0]
    x1, y1, x2, y2 = xyxy
    return [round(min(1.0, max(0.0, v)), 4)
            for v in (x1 / w, y1 / h, x2 / w, y2 / h)]


FireType = Literal["UNCONTROLLED", "CONTROLLED", "UNKNOWN"]


class VLMResult(BaseModel):
    is_fire: bool
    is_smoke: bool
    confidence: float = Field(ge=0, le=1)
    description_vi: str
    fire_type: FireType | None = None
    """Controlled fire (charcoal grill, cooking, burning in a container) vs an
    incident. Advisory only: it never changes ``verification`` or severity —
    only the operator can dismiss. Always ``UNCONTROLLED`` for HAM / TRET."""


class Event(BaseModel):
    """Alert event — schema chốt với backend, không tự đổi.

    Chỉ được thêm trường. ``type`` là loại của lần gửi này; ``snapshot_base64``
    chỉ có trong payload webhook khi ``webhook.gui_anh`` bật, không bao giờ nằm
    trong JSON trên đĩa, REST hay WebSocket.
    """

    event_id: str
    camera_id: str
    context: Context
    severity: SeverityName
    verification: Verification
    started_at: str
    video_ts_sec: float
    boxes: list[EventBox]
    vlm: VLMResult | None = None
    snapshot_path: str
    type: Literal["created", "updated"] = "created"
    """``created`` ở lần gửi đầu; ``updated`` ở mọi lần gửi lại cùng ``event_id``."""
    frame_w: int = 0
    frame_h: int = 0
    """Kích thước khung gốc (pixel) mà ``boxes[].xyxy`` tính trên đó; 0 chỉ ở
    event ghi trước khi có trường này (nạp lại từ đĩa)."""
    frame_ts: float = 0.0
    """Giây Unix (UTC) của khung keyframe; cùng thời điểm với ``started_at``."""
    snapshot_base64: str | None = None
    """JPEG base64 của keyframe gốc (không vẽ box), dưới ``webhook.anh_toi_da_kb``;
    chỉ trong payload webhook khi ``webhook.gui_anh`` bật."""

    @model_serializer(mode="wrap")
    def _bo_truong_rong(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        if self.snapshot_base64 is None:
            data.pop("snapshot_base64", None)
        return data


def sample_event() -> Event:
    """Example payload for the backend team (``POST /webhook-test``)."""
    now = datetime.now(timezone.utc).astimezone()
    return Event(
        event_id=str(uuid.uuid4()), camera_id="cam01", context="HAM",
        severity="CRITICAL", verification="UNVERIFIED",
        started_at=now.isoformat(timespec="seconds"),
        video_ts_sec=12.0,
        boxes=[EventBox(cls="fire", conf=0.87, xyxy=[120, 80, 260, 210],
                        xyxyn=chuan_hoa_box((120, 80, 260, 210), 1280, 720))],
        vlm=VLMResult(is_fire=True, is_smoke=True, confidence=0.92,
                      description_vi="Khói đen và lửa bốc lên từ yên xe máy.",
                      fire_type="UNCONTROLLED"),
        snapshot_path="events/20261102_120000_sample.jpg",
        frame_w=1280, frame_h=720, frame_ts=round(now.timestamp(), 3),
    )


class WebhookSink:
    """POST events to the team backend without blocking the pipeline.

    Mọi lần gửi đi qua **một** thread gửi theo hàng FIFO, nên backend nhận
    đúng thứ tự phát: ``updated`` không bao giờ tới trước ``created`` của cùng
    ``event_id``. Một lần gửi chậm làm chậm các lần sau (tối đa
    ``timeout_s × (retries + 1)`` mỗi lần), không chặn pipeline.
    """

    def __init__(self, url: str, token: str | None, timeout_s: float, retries: int):
        self.url, self.token = url, token
        self.timeout_s, self.retries = timeout_s, retries
        self._hang: queue.SimpleQueue[tuple[Event, str | None]] = queue.SimpleQueue()
        self._luong: threading.Thread | None = None
        self._khoa = threading.Lock()

    def send(self, event: Event, anh_b64: str | None = None) -> None:
        """Xếp một lần gửi; ``anh_b64`` là ``snapshot_base64`` nếu bật."""
        with self._khoa:
            if self._luong is None:
                self._luong = threading.Thread(target=self._gui_lan_luot,
                                               name="webhook", daemon=True)
                self._luong.start()
        self._hang.put((event, anh_b64))

    def _gui_lan_luot(self) -> None:
        while True:
            event, anh_b64 = self._hang.get()
            try:
                self._post(event, anh_b64)
            except Exception:  # noqa: BLE001 - thread gửi không được chết
                log.exception("webhook lỗi không bắt được")

    def _post(self, event: Event, anh_b64: str | None = None) -> None:
        if anh_b64 is not None:
            event = event.model_copy(update={"snapshot_base64": anh_b64})
        body = event.model_dump_json().encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            # Hợp đồng với backend: cùng một token, gửi theo cả hai cách xác thực.
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-Internal-Secret"] = self.token
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(self.url, data=body, headers=headers,
                                             method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    log.info("webhook %s -> HTTP %s", event.event_id[:8], resp.status)
                    return
            except urllib.error.HTTPError as exc:
                # 4xx (trừ 408/429) là lỗi phía ta: gửi lại cũng vậy, không retry.
                if 400 <= exc.code < 500 and exc.code not in (408, 429):
                    log.error("webhook từ chối event %s: HTTP %s (không retry)",
                              event.event_id[:8], exc.code)
                    return
                log.warning("webhook lỗi (%d/%d): HTTP %s", attempt + 1,
                            self.retries + 1, exc.code)
            except Exception as exc:  # noqa: BLE001 - mạng lỗi gì cũng chỉ log
                log.warning("webhook lỗi (%d/%d): %s", attempt + 1, self.retries + 1,
                            exc)
        log.error("webhook bỏ cuộc cho event %s", event.event_id)


class EventStore:
    """Keeps events in memory and on disk; fans out to subscribers."""

    def __init__(self, cfg: AlertsConfig, camera: CameraConfig, root: Config):
        self.dir = root.resolve(cfg.events_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.root = root.root
        self.camera = camera
        self.jpeg_quality = cfg.snapshot_jpeg_quality
        self.save_raw = cfg.save_raw_keyframe
        self.notify_suppressed = cfg.notify_suppressed
        self.gui_anh = root.webhook.gui_anh
        self.anh_toi_da_kb = root.webhook.anh_toi_da_kb
        self._anh_b64: OrderedDict[str, str] = OrderedDict()
        """event_id -> keyframe gốc JPEG base64 (chỉ khi ``webhook.gui_anh``),
        giữ cho tối đa :data:`SO_ANH_GIU` event mới nhất của lần chạy này."""
        self._events: list[Event] = []
        self._paths: dict[str, Path] = {}
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[Event, str], None]] = []
        """Called with ``(event, kind)``; kind is ``"created"``, ``"updated"`` or
        ``"escalated"`` (CRITICAL left unacknowledged, see acks.py)."""
        self.webhook: WebhookSink | None = None
        url = env_secret(cfg.webhook_url_env)
        if url:
            self.webhook = WebhookSink(url, env_secret(cfg.webhook_token_env),
                                       cfg.webhook_timeout_s, cfg.webhook_retries)
            log.info("webhook bật: %s", url)
        if cfg.keep_days > 0:
            self.prune(cfg.keep_days)
        self.load_existing()

    # ---------------------------------------------------------------- storage
    def prune(self, keep_days: float) -> int:
        """Delete event JSON + snapshot files older than ``keep_days``."""
        cutoff = time.time() - keep_days * 86400
        n = 0
        for p in list(self.dir.glob("*.json")) + list(self.dir.glob("*.jpg")):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
                    n += 1
            except OSError as exc:
                log.warning("không xoá được %s: %s", p.name, exc)
        if n:
            log.info("retention: xoá %d file event cũ hơn %.0f ngày", n, keep_days)
        return n

    def load_existing(self) -> int:
        n = 0
        for p in sorted(self.dir.glob("*.json")):
            try:
                ev = Event.model_validate_json(p.read_text(encoding="utf-8"))
                self._events.append(ev)
                self._paths[ev.event_id] = p
                n += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("bỏ qua event hỏng %s: %s", p.name, exc)
        if n:
            log.info("nạp %d event cũ từ %s", n, self.dir)
        return n

    def subscribe(self, fn: Callable[[Event, str], None]) -> None:
        self._subscribers.append(fn)

    def _notify(self, event: Event, kind: str) -> None:
        if event.verification == "SUPPRESSED" and not self.notify_suppressed:
            log.info("event %s SUPPRESSED: chỉ ghi đĩa, không đẩy WS/webhook",
                     event.event_id[:8])
            return
        if kind != "created" and event.type != "updated":
            # Gửi lại nguyên nội dung (nhắc lại): payload vẫn phải ghi là updated.
            event = event.model_copy(update={"type": "updated"})
        for fn in self._subscribers:
            try:
                fn(event, kind)
            except Exception as exc:  # noqa: BLE001
                log.warning("subscriber lỗi: %s", exc)
        if self.webhook:
            self.webhook.send(event, self._anh_b64.get(event.event_id))

    def all(self, limit: int | None = None) -> list[Event]:
        with self._lock:
            items = list(reversed(self._events))
        return items[:limit] if limit else items

    def get(self, event_id: str) -> Event | None:
        with self._lock:
            return next((e for e in self._events if e.event_id == event_id), None)

    def __len__(self) -> int:
        return len(self._events)

    # ----------------------------------------------------------------- create
    def create(self, *, severity: SeverityName, verification: Verification,
               video_ts: float, detections: list[Detection],
               image: np.ndarray | None, vlm: VLMResult | None = None,
               started_at: datetime | None = None) -> Event:
        """Persist one alert (JSON + annotated snapshot) and notify listeners.

        Parameters
        ----------
        image : ndarray or None
            Keyframe (BGR). ``None`` skips the snapshot (unit tests).
        """
        started = started_at or datetime.now(timezone.utc).astimezone()
        event_id = str(uuid.uuid4())
        stem = f"{started:%Y%m%d_%H%M%S}_{event_id[:8]}"
        snapshot_rel = ""
        h, w = image.shape[:2] if image is not None else (0, 0)
        if image is not None:
            banner = (f"{severity} {verification} {video_ts:.1f}s "
                      f"{self.camera.id} {self.camera.context}")
            annotated = draw_detections(image, detections, banner)
            snap = self.dir / f"{stem}.jpg"
            if write_jpeg(snap, annotated, self.jpeg_quality):
                snapshot_rel = _relpath(snap, self.root)
            else:
                log.error("event %s không có snapshot (ghi ảnh thất bại)", event_id[:8])
            if self.save_raw:
                write_jpeg(raw_keyframe_path(snap), image, self.jpeg_quality)
            if self.gui_anh:
                jpeg = nen_jpeg_duoi(image, self.anh_toi_da_kb)
                self._anh_b64[event_id] = base64.b64encode(jpeg).decode("ascii")
                while len(self._anh_b64) > SO_ANH_GIU:
                    self._anh_b64.popitem(last=False)
        event = Event(
            event_id=event_id, camera_id=self.camera.id, context=self.camera.context,
            severity=severity, verification=verification,
            started_at=started.isoformat(timespec="seconds"),
            video_ts_sec=round(video_ts, 2),
            boxes=[EventBox(**d.to_dict(), xyxyn=chuan_hoa_box(d.xyxy, w, h))
                   for d in detections],
            vlm=vlm, snapshot_path=snapshot_rel,
            frame_w=w, frame_h=h, frame_ts=round(started.timestamp(), 3),
        )
        json_path = self.dir / f"{stem}.json"
        json_path.write_text(event.model_dump_json(indent=2), encoding="utf-8")
        with self._lock:
            self._events.append(event)
            self._paths[event_id] = json_path
        log.info("ALERT %s %s %s video %.1fs -> %s", severity, verification,
                 event_id[:8], video_ts, snapshot_rel or "(không snapshot)")
        self._notify(event, "created")
        return event

    def update(self, event_id: str, *, verification: Verification,
               vlm: VLMResult | None) -> Event | None:
        """Patch the VLM verdict onto an event already sent (same ``event_id``).

        The JSON on disk is rewritten in place and subscribers get the event
        again with kind ``"updated"`` (WebSocket ``event_update``); the
        webhook is POSTed again with the same ``event_id`` so the backend can
        upsert.
        """
        with self._lock:
            idx = next((i for i, e in enumerate(self._events)
                        if e.event_id == event_id), None)
            if idx is None:
                return None
            event = self._events[idx].model_copy(
                update={"verification": verification, "vlm": vlm, "type": "updated"})
            self._events[idx] = event
            path = self._paths.get(event_id)
        if path is not None:
            path.write_text(event.model_dump_json(indent=2), encoding="utf-8")
        log.info("ALERT UPDATE %s -> %s", event_id[:8], verification)
        self._notify(event, "updated")
        return event

    def renotify(self, event_id: str, kind: str = "escalated") -> Event | None:
        """Push an unchanged event again (escalation): same ``event_id``,
        WebSocket ``event_update`` and webhook POST, nothing rewritten."""
        event = self.get(event_id)
        if event is not None:
            self._notify(event, kind)
        return event


def raw_keyframe_path(snapshot: Path) -> Path:
    """Clean keyframe (no boxes, no banner) saved next to a snapshot."""
    return snapshot.with_name(f"{snapshot.stem}_goc{snapshot.suffix}")


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def event_to_dict(event: Event) -> dict[str, Any]:
    return event.model_dump(mode="json")


SO_ANH_GIU = 64
"""Số keyframe base64 giữ trong bộ nhớ cho webhook (event mới nhất trước)."""


def nen_jpeg_duoi(image: np.ndarray, toi_da_kb: int) -> bytes:
    """JPEG của ``image`` không quá ``toi_da_kb`` KB.

    Hạ chất lượng 85 → 70 → 55 → 40; vẫn quá thì thu nhỏ một nửa mỗi cạnh rồi
    thử lại, tới khi cạnh dài còn 160 px thì trả bản nhỏ nhất dù quá cỡ.

    Parameters
    ----------
    image : ndarray
        Ảnh BGR.
    toi_da_kb : int
        Cỡ tối đa, KB (1 KB = 1024 byte).
    """
    gioi_han = toi_da_kb * 1024
    img = image
    while True:
        buf = None
        for q in (85, 70, 55, 40):
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
            if ok and buf.nbytes <= gioi_han:
                return buf.tobytes()
        h, w = img.shape[:2]
        if max(h, w) <= 160 or buf is None:
            return buf.tobytes() if buf is not None else b""
        img = cv2.resize(img, (max(1, w // 2), max(1, h // 2)),
                         interpolation=cv2.INTER_AREA)
