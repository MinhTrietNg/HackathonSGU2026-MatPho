"""Tier 1 — video sources and the heartbeat sampler.

One ``VideoSource`` interface covers video files, webcams and RTSP streams.
``HeartbeatSampler`` turns the raw frame stream into one frame every ``T``
seconds **of video time** (not wall-clock time), keeping a short ring buffer
of the most recent frames so later tiers can pick a keyframe.
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .config import SourceConfig

log = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".webm", ".ts", ".m4v", ".flv"}


@dataclass(slots=True)
class Frame:
    """One decoded frame with both clocks attached."""

    image: np.ndarray
    video_ts: float
    """Seconds since the start of the stream (file position or time since open)."""
    wall_time: float
    """``time.time()`` when the frame was read."""
    index: int


def infer_kind(spec: str) -> str:
    """Guess the source kind from a CLI ``--source`` string.

    Parameters
    ----------
    spec : str
        ``"0"`` (webcam index), ``rtsp://...``/``http://...`` or a file path.

    Returns
    -------
    str
        ``"webcam"``, ``"rtsp"`` or ``"file"``.
    """
    spec = spec.strip()
    if spec.isdigit():
        return "webcam"
    lowered = spec.lower()
    if lowered.startswith(("rtsp://", "rtsps://", "http://", "https://")):
        return "rtsp"
    return "file"


class VideoSource(ABC):
    """Iterable stream of :class:`Frame`; ``None`` from ``read`` means end."""

    kind: str = "abstract"
    name: str = "source"
    is_live: bool = False

    def __enter__(self) -> "VideoSource":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __iter__(self):
        while (frame := self.read()) is not None:
            yield frame

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read(self) -> Frame | None: ...

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def fps(self) -> float: ...


class FileSource(VideoSource):
    """Video file. Timestamps follow the file, optionally paced to real time."""

    kind = "file"

    def __init__(self, path: str | Path, realtime: bool = False, loop: bool = False):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"không thấy video: {self.path}")
        self.name = self.path.stem
        self.realtime = realtime
        self.loop = loop
        self._cap: cv2.VideoCapture | None = None
        self._fps = 0.0
        self._index = 0
        self._loop_offset = 0.0
        self._t_start_wall = 0.0

    def open(self) -> None:
        self._cap = cv2.VideoCapture(str(self.path))
        if not self._cap.isOpened():
            raise RuntimeError(f"OpenCV không mở được video: {self.path}")
        self._fps = float(self._cap.get(cv2.CAP_PROP_FPS)) or 25.0
        self._index = 0
        self._loop_offset = 0.0
        self._t_start_wall = time.monotonic()
        n = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        log.info(
            "mở file %s: %.2f fps, %d frame (~%.1f s)", self.path.name, self._fps, n,
            n / self._fps,
        )

    @property
    def fps(self) -> float:
        return self._fps

    def read(self) -> Frame | None:
        assert self._cap is not None, "gọi open() trước"
        ok, image = self._cap.read()
        if not ok:
            if not self.loop:
                return None
            self._loop_offset += self._index / self._fps
            self._index = 0
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, image = self._cap.read()
            if not ok:
                return None
        video_ts = self._loop_offset + self._index / self._fps
        self._index += 1
        if self.realtime:
            # Phát lại đúng tốc độ: chờ tới khi đồng hồ thật đuổi kịp timestamp video.
            lag = video_ts - (time.monotonic() - self._t_start_wall)
            if lag > 0:
                time.sleep(lag)
        return Frame(image=image, video_ts=video_ts, wall_time=time.time(),
                     index=self._index - 1)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class CameraSource(VideoSource):
    """Webcam index or RTSP/HTTP URL read by a background thread.

    The reader thread decodes every frame and keeps only the **latest** one,
    so a slow consumer (CPU busier than the camera fps) never builds a
    backlog: each ``read`` returns the newest frame with the time it was
    captured, and older frames are counted in ``dropped``. The thread also
    owns reconnection: forever by default, exponential back-off capped at
    30 s, open/read timeouts so a dead RTSP link cannot hang.
    """

    is_live = True

    def __init__(self, spec: str, reconnect_s: float = 2.0, max_reconnects: int = 0,
                 read_timeout_s: float = 10.0):
        self.spec = spec
        self.kind = infer_kind(spec)
        self.name = f"cam{spec}" if self.kind == "webcam" else "rtsp"
        self.reconnect_s = reconnect_s
        self.max_reconnects = max_reconnects
        self.read_timeout_s = read_timeout_s
        self._cap: cv2.VideoCapture | None = None
        self._fps = 0.0
        self._index = 0
        self._t0 = 0.0
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: tuple[np.ndarray, float, float, int] | None = None
        self._dead = False
        self._last_served = -1
        self.dropped = 0
        """Frames decoded but never handed to the pipeline (consumer slower)."""

    def _connect(self) -> bool:
        if self.kind == "webcam":
            self._cap = cv2.VideoCapture(int(self.spec))
        else:
            ms = int(self.read_timeout_s * 1000)
            # Timeout mở/đọc cho backend FFMPEG: đứt mạng thì read() trả False
            # thay vì treo vô hạn.
            self._cap = cv2.VideoCapture(self.spec, cv2.CAP_FFMPEG, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, ms, cv2.CAP_PROP_READ_TIMEOUT_MSEC, ms])
        if not self._cap.isOpened():
            return False
        self._fps = float(self._cap.get(cv2.CAP_PROP_FPS)) or 0.0
        return True

    def open(self) -> None:
        if not self._connect():
            raise RuntimeError(f"không mở được nguồn live: {self.spec}")
        self._t0 = time.monotonic()
        self._index = 0
        self._stop.clear()
        self._dead = False
        self._thread = threading.Thread(target=self._reader, name=f"reader-{self.name}",
                                        daemon=True)
        self._thread.start()
        log.info("mở nguồn live %s (%s), fps báo %.1f", self.spec, self.kind, self._fps)

    @property
    def fps(self) -> float:
        return self._fps

    def _reader(self) -> None:
        """Decode continuously; publish only the newest frame; reconnect."""
        attempt = 0
        while not self._stop.is_set():
            ok, image = self._cap.read() if self._cap is not None else (False, None)
            if ok:
                attempt = 0
                with self._cond:
                    self._latest = (image, time.monotonic() - self._t0, time.time(),
                                    self._index)
                    self._index += 1
                    self._cond.notify_all()
                continue
            attempt += 1
            if self.max_reconnects and attempt > self.max_reconnects:
                log.error("bỏ cuộc sau %d lần: không nhận được khung từ %s",
                          attempt - 1, self.spec)
                break
            wait = min(self.reconnect_s * 2 ** (attempt - 1), 30.0)
            limit = str(self.max_reconnects) if self.max_reconnects else "∞"
            log.warning("mất khung từ %s, mở lại lần %d/%s sau %.1f s", self.spec,
                        attempt, limit, wait)
            if self._stop.wait(wait):
                break
            if self._cap is not None:
                self._cap.release()
            self._connect()
        with self._cond:
            self._dead = True
            self._cond.notify_all()

    def read(self) -> Frame | None:
        """Block until a frame newer than the last served one exists."""
        with self._cond:
            while True:
                if self._latest is not None and self._latest[3] > self._last_served:
                    image, video_ts, wall, idx = self._latest
                    break
                if self._dead or self._stop.is_set():
                    return None
                self._cond.wait(timeout=1.0)
            if self._last_served >= 0:
                self.dropped += idx - self._last_served - 1
            self._last_served = idx
        return Frame(image=image, video_ts=video_ts, wall_time=wall, index=idx)

    def close(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=max(2.0, self.read_timeout_s))
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self.dropped:
            log.info("%s: bỏ qua %d khung vì pipeline chậm hơn camera", self.spec,
                     self.dropped)


def open_source(spec: str, cfg: SourceConfig, realtime: bool | None = None,
                ) -> VideoSource:
    """Build the right :class:`VideoSource` for a CLI ``--source`` value.

    Parameters
    ----------
    spec : str
        File path, webcam index or stream URL.
    cfg : SourceConfig
        ``source:`` section of ``config.yaml``.
    realtime : bool, optional
        Overrides ``cfg.realtime`` (the ``--realtime`` flag).
    """
    kind = infer_kind(spec) if cfg.kind == "auto" else cfg.kind
    if kind == "file":
        rt = cfg.realtime if realtime is None else realtime
        return FileSource(spec, realtime=rt, loop=cfg.loop)
    return CameraSource(spec, reconnect_s=cfg.reconnect_s,
                        max_reconnects=cfg.max_reconnects,
                        read_timeout_s=cfg.read_timeout_s)


@dataclass(slots=True)
class Heartbeat:
    """One sampled frame plus the ring buffer of frames just before it."""

    seq: int
    frame: Frame
    ring: list[Frame] = field(default_factory=list)


class HeartbeatSampler:
    """Emit one :class:`Heartbeat` every ``interval_s`` seconds of video time.

    The grid is aligned to multiples of ``interval_s`` from the first frame,
    so a 25 fps file with ``T = 1.0`` yields heartbeats at 0, 1, 2 ... s even
    if frames are dropped or the decoder jitters.
    """

    def __init__(self, interval_s: float, ring_buffer: int = 5):
        if interval_s <= 0:
            raise ValueError("interval_s phải > 0")
        self.interval_s = interval_s
        self._ring: deque[Frame] = deque(maxlen=ring_buffer)
        self._next_ts: float | None = None
        self.seq = 0

    def push(self, frame: Frame) -> Heartbeat | None:
        """Feed one frame; return a heartbeat when the grid tick is reached."""
        self._ring.append(frame)
        if self._next_ts is None:
            self._next_ts = frame.video_ts
        if frame.video_ts + 1e-9 < self._next_ts:
            return None
        hb = Heartbeat(seq=self.seq, frame=frame, ring=list(self._ring))
        self.seq += 1
        # Nhảy tới mốc kế tiếp sau frame hiện tại (bỏ qua các mốc đã lỡ).
        while self._next_ts <= frame.video_ts + 1e-9:
            self._next_ts += self.interval_s
        return hb
