"""Tier 5 — alert sink: event schema, on-disk store, snapshots, webhook.

The JSON schema of an event is agreed with the backend team and must not
change. Every alert writes ``events/<stamp>_<id>.json`` plus an annotated
``.jpg`` keyframe, notifies in-process subscribers (the WebSocket
broadcaster) and, when configured, POSTs the event to a webhook.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import (BaseModel, Field, field_validator, model_serializer,
                      model_validator)

from .annotate import draw_detections, write_jpeg
from .config import AlertsConfig, CameraConfig, Config, Context, env_secret
from .detector import Detection

log = logging.getLogger(__name__)

SeverityName = Literal["WARNING", "CRITICAL"]
Verification = Literal["VERIFIED", "UNVERIFIED", "SUPPRESSED"]
VerifierStatus = Literal["PENDING", "VERIFIED", "REJECTED", "VLM_TIMEOUT",
                         "VLM_ERROR", "VLM_OFF"]
"""Trạng thái xác minh tự động khi cờ ``verifier.ben_vung`` bật."""

VERIFICATION_CUA: dict[str, Verification] = {
    "PENDING": "UNVERIFIED", "VERIFIED": "VERIFIED", "REJECTED": "SUPPRESSED",
    "VLM_TIMEOUT": "UNVERIFIED", "VLM_ERROR": "UNVERIFIED", "VLM_OFF": "UNVERIFIED"}
"""Ánh xạ trạng thái verifier sang ``verification`` cũ (Literal không đổi)."""

CAN_NGUOI_XAC_THUC = frozenset({"VLM_TIMEOUT", "VLM_ERROR", "VLM_OFF"})
"""Trạng thái mà người trực phải tự xác thực."""

LY_DO = frozenset({"cho_vlm", "timeout", "qua_han_hang_cho", "http_429", "http_4xx",
                   "http_5xx", "loi_mang", "loi_phan_tich", "cau_dao_mo", "vlm_tat"})
"""Mã ``reason`` hợp lệ; không bao giờ chứa body HTTP hay chuỗi lỗi thô."""


class EventBox(BaseModel):
    cls: str
    conf: float
    xyxy: list[float] = Field(min_length=4, max_length=4)


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


class VerifierInfo(BaseModel):
    """Trạng thái xác minh tự động của một event (chỉ có khi cờ bật)."""

    status: VerifierStatus
    needs_human_check: bool
    latency_ms: int | None = None
    """Thời gian VLM trả lời; ``None`` nếu không có câu trả lời."""
    reason: str | None = None
    """Mã ngắn trong :data:`LY_DO`."""

    @field_validator("reason")
    @classmethod
    def _ma_hop_le(cls, v: str | None) -> str | None:
        if v is not None and v not in LY_DO:
            raise ValueError(f"reason không thuộc mã đã định: {v!r}")
        return v

    @model_validator(mode="after")
    def _can_nguoi_khop_trang_thai(self) -> "VerifierInfo":
        if self.needs_human_check != (self.status in CAN_NGUOI_XAC_THUC):
            raise ValueError("needs_human_check phải đúng khi và chỉ khi status là "
                             "VLM_TIMEOUT, VLM_ERROR hoặc VLM_OFF")
        return self

    @classmethod
    def tao(cls, status: VerifierStatus, *, latency_s: float | None = None,
            reason: str | None = None) -> "VerifierInfo":
        """Tạo object với ``needs_human_check`` suy từ ``status``.

        Parameters
        ----------
        status : VerifierStatus
            Trạng thái xác minh.
        latency_s : float, optional
            Độ trễ VLM tính bằng giây; ``None`` nếu không có câu trả lời.
        reason : str, optional
            Mã trong :data:`LY_DO`.
        """
        ms = None if latency_s is None else int(round(latency_s * 1000))
        return cls(status=status, needs_human_check=status in CAN_NGUOI_XAC_THUC,
                   latency_ms=ms, reason=reason)

    @property
    def verification(self) -> Verification:
        """Giá trị ``verification`` cũ tương ứng."""
        return VERIFICATION_CUA[self.status]


class Event(BaseModel):
    """Alert event — schema chốt với backend, không tự đổi.

    ``verifier`` chỉ được thêm (không đổi trường cũ) và chỉ xuất hiện trong JSON
    khi có giá trị, tức khi cờ ``verifier.ben_vung`` bật.
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
    verifier: VerifierInfo | None = None

    @model_serializer(mode="wrap")
    def _bo_verifier_rong(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        if self.verifier is None:
            data.pop("verifier", None)
        return data

    @model_validator(mode="after")
    def _verification_khop_verifier(self) -> "Event":
        if (self.verifier is not None
                and self.verification != self.verifier.verification):
            raise ValueError(f"verification {self.verification} không khớp "
                             f"verifier.status {self.verifier.status}")
        return self


def sample_event() -> Event:
    """Example payload for the backend team (``POST /webhook-test``)."""
    return Event(
        event_id=str(uuid.uuid4()), camera_id="cam01", context="HAM",
        severity="CRITICAL", verification="UNVERIFIED",
        started_at=datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds"),
        video_ts_sec=12.0,
        boxes=[EventBox(cls="fire", conf=0.87, xyxy=[120, 80, 260, 210])],
        vlm=VLMResult(is_fire=True, is_smoke=True, confidence=0.92,
                      description_vi="Khói đen và lửa bốc lên từ yên xe máy.",
                      fire_type="UNCONTROLLED"),
        snapshot_path="events/20261102_120000_sample.jpg",
    )


class WebhookSink:
    """POST events to the team backend without blocking the pipeline."""

    def __init__(self, url: str, token: str | None, timeout_s: float, retries: int):
        self.url, self.token = url, token
        self.timeout_s, self.retries = timeout_s, retries

    def send(self, event: Event) -> None:
        threading.Thread(target=self._post, args=(event,), daemon=True).start()

    def _post(self, event: Event) -> None:
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
        """Đẩy event tới subscriber và webhook.

        Event mang ``verifier`` (cờ bật) luôn được đẩy, kể cả REJECTED với
        ``notify_suppressed = false``: VLM không được gỡ cảnh báo, chỉ người trực
        được bỏ qua.
        """
        if (event.verification == "SUPPRESSED" and not self.notify_suppressed
                and event.verifier is None):
            log.info("event %s SUPPRESSED: chỉ ghi đĩa, không đẩy WS/webhook",
                     event.event_id[:8])
            return
        for fn in self._subscribers:
            try:
                fn(event, kind)
            except Exception as exc:  # noqa: BLE001
                log.warning("subscriber lỗi: %s", exc)
        if self.webhook:
            self.webhook.send(event)

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
               started_at: datetime | None = None,
               verifier: VerifierInfo | None = None) -> Event:
        """Persist one alert (JSON + annotated snapshot) and notify listeners.

        Parameters
        ----------
        image : ndarray or None
            Keyframe (BGR). ``None`` skips the snapshot (unit tests).
        verifier : VerifierInfo, optional
            Trạng thái xác minh khi cờ ``verifier.ben_vung`` bật; ``None`` giữ
            đúng JSON và log cũ.
        """
        started = started_at or datetime.now(timezone.utc).astimezone()
        event_id = str(uuid.uuid4())
        stem = f"{started:%Y%m%d_%H%M%S}_{event_id[:8]}"
        snapshot_rel = ""
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
        event = Event(
            event_id=event_id, camera_id=self.camera.id, context=self.camera.context,
            severity=severity, verification=verification,
            started_at=started.isoformat(timespec="seconds"),
            video_ts_sec=round(video_ts, 2),
            boxes=[EventBox(**d.to_dict()) for d in detections],
            vlm=vlm, snapshot_path=snapshot_rel, verifier=verifier,
        )
        json_path = self.dir / f"{stem}.json"
        json_path.write_text(event.model_dump_json(indent=2), encoding="utf-8")
        with self._lock:
            self._events.append(event)
            self._paths[event_id] = json_path
        log.info("ALERT %s %s %s video %.1fs -> %s", severity, verification,
                 event_id[:8], video_ts, snapshot_rel or "(không snapshot)")
        if verifier is not None:
            _log_verifier(event_id, verifier)
        self._notify(event, "created")
        return event

    def update(self, event_id: str, *, verification: Verification,
               vlm: VLMResult | None,
               verifier: VerifierInfo | None = None) -> Event | None:
        """Patch the VLM verdict onto an event already sent (same ``event_id``).

        The JSON on disk is rewritten in place and subscribers get the event
        again with kind ``"updated"`` (WebSocket ``event_update``); the
        webhook is POSTed again with the same ``event_id`` so the backend can
        upsert. ``severity`` is never touched: the VLM cannot lower it.

        Parameters
        ----------
        verifier : VerifierInfo, optional
            Trạng thái xác minh mới khi cờ bật; ``None`` giữ đúng hành vi cũ.
        """
        if verifier is not None and verifier.verification != verification:
            raise ValueError(f"verification {verification} không khớp "
                             f"verifier.status {verifier.status}")
        moi: dict[str, Any] = {"verification": verification, "vlm": vlm}
        if verifier is not None:
            moi["verifier"] = verifier
        with self._lock:
            idx = next((i for i, e in enumerate(self._events)
                        if e.event_id == event_id), None)
            if idx is None:
                return None
            event = self._events[idx].model_copy(update=moi)
            self._events[idx] = event
            path = self._paths.get(event_id)
        if path is not None:
            path.write_text(event.model_dump_json(indent=2), encoding="utf-8")
        log.info("ALERT UPDATE %s -> %s", event_id[:8], verification)
        if verifier is not None:
            _log_verifier(event_id, verifier)
        self._notify(event, "updated")
        return event

    def renotify(self, event_id: str, kind: str = "escalated") -> Event | None:
        """Push an unchanged event again (escalation): same ``event_id``,
        WebSocket ``event_update`` and webhook POST, nothing rewritten."""
        event = self.get(event_id)
        if event is not None:
            self._notify(event, kind)
        return event


def _log_verifier(event_id: str, v: VerifierInfo) -> None:
    """Một dòng log trạng thái verifier (chỉ khi cờ bật)."""
    log.info("verifier %s: %s%s%s", event_id[:8], v.status,
             f" ({v.reason})" if v.reason else "",
             " — cần người xác thực" if v.needs_human_check else "")


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
