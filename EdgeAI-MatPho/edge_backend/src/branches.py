"""The two output branches fed by one decoded source.

* **Live branch** (towards the app & AI): lossless remux when the source is H.264,
  otherwise a full-resolution H.264 transcode so every app player (HLS) and AI reader can consume it.
* **AI branch** (optional down-scaled sub-stream): down-scaled, down-sampled H.264
  sub-stream, encoded on its own thread so it can never stall the live branch.
  When ``settings.enable_ai_branch`` is ``False``, :class:`AiBranchStub` is used for Zero-CPU overhead.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Protocol

import av

from .config import DecoderSettings
from .endpoints import StreamInfo
from .scaling import fit_even
from .sinks import CLOCK_HZ, CopySink, H264Sink
from .stats import SessionStats

logger = logging.getLogger("stream-worker.branches")

_STOP = object()
_LIVE_TRANSCODE_CRF = 23


class LiveBranch(Protocol):
    """Interface of the branch that feeds the app (HLS) and direct RTSP consumers."""

    mode: str

    def on_packet(self, packet: av.Packet) -> None:
        """Handle one compressed packet (called after it was decoded)."""

    def on_frame(self, frame: av.VideoFrame, pts: int) -> None:
        """Handle one decoded frame with its 90 kHz timestamp."""

    def close(self) -> None:
        """Release the output."""


class CopyLiveBranch:
    """Forward source packets untouched; zero re-encoding cost."""

    mode = "copy"

    def __init__(
        self,
        url: str,
        in_stream: av.video.stream.VideoStream,
        settings: DecoderSettings,
        stats: SessionStats,
    ) -> None:
        self._sink = CopySink(url, in_stream, settings)
        self._stats = stats

    def on_packet(self, packet: av.Packet) -> None:
        if self._sink.write(packet):
            self._stats.live_packets_out += 1

    def on_frame(self, frame: av.VideoFrame, pts: int) -> None:
        """Unused: the copy branch works on packets."""

    def close(self) -> None:
        self._sink.close()


class TranscodeLiveBranch:
    """Re-encode to H.264 at source resolution (non-H.264 sources like HEVC/H.265)."""

    mode = "transcode"

    def __init__(
        self,
        url: str,
        info: StreamInfo,
        settings: DecoderSettings,
        stats: SessionStats,
    ) -> None:
        width, height = fit_even(info.width, info.height, max(info.width, info.height))
        self._sink = H264Sink(
            url, width, height, info.fps, _LIVE_TRANSCODE_CRF, settings
        )
        self._stats = stats

    def on_packet(self, packet: av.Packet) -> None:
        """Unused: the transcode branch works on frames."""

    def on_frame(self, frame: av.VideoFrame, pts: int) -> None:
        self._sink.write(frame, pts)
        self._stats.live_packets_out += 1

    def close(self) -> None:
        self._sink.close()


def make_live_branch(
    url: str,
    in_stream: av.video.stream.VideoStream,
    info: StreamInfo,
    settings: DecoderSettings,
    stats: SessionStats,
) -> LiveBranch:
    """Choose remux for H.264 sources and transcode for everything else."""
    if info.codec == "h264":
        return CopyLiveBranch(url, in_stream, settings, stats)
    logger.info("source codec %s is not H.264: live branch will transcode", info.codec)
    return TranscodeLiveBranch(url, info, settings, stats)


class AiBranchStub:
    """Zero-CPU stub when ``enable_ai_branch=False`` (AI reads directly from ``live/{cam_id}``)."""

    def __init__(self, *args, **kwargs) -> None:
        self.error: BaseException | None = None
        self._size = (0, 0)

    @property
    def size(self) -> tuple[int, int]:
        return self._size

    @property
    def failed(self) -> bool:
        return False

    def start(self) -> None:
        pass

    def submit(self, frame: av.VideoFrame, t: float) -> bool:
        return True

    def close(self, timeout: float = 5.0) -> None:
        pass


class AiBranch:
    """Down-scaled, down-sampled H.264 sub-stream published on a worker thread."""

    def __init__(
        self,
        url: str,
        info: StreamInfo,
        settings: DecoderSettings,
        stats: SessionStats,
    ) -> None:
        self._url = url
        self._settings = settings
        self._stats = stats
        self._size = fit_even(info.width, info.height, settings.ai_max_edge)
        self._queue: queue.Queue = queue.Queue(maxsize=settings.ai_queue_size)
        self._thread = threading.Thread(
            target=self._run, name="ai-branch", daemon=True
        )
        self._t0: float | None = None
        self.error: BaseException | None = None

    @property
    def size(self) -> tuple[int, int]:
        """Output ``(width, height)``."""
        return self._size

    @property
    def failed(self) -> bool:
        """``True`` once the worker died; the branch must be recreated."""
        return self.error is not None

    def start(self) -> None:
        """Start the worker thread."""
        self._thread.start()

    def submit(self, frame: av.VideoFrame, t: float) -> bool:
        """Hand a frame over without blocking."""
        if self.failed:
            return False
        if self._t0 is None:
            self._t0 = t
        item = (frame, round((t - self._t0) * CLOCK_HZ))
        while True:
            try:
                self._queue.put_nowait(item)
                break
            except queue.Full:
                try:
                    self._queue.get_nowait()
                    self._stats.ai_frames_dropped += 1
                except queue.Empty:
                    pass
        self._stats.ai_frames_submitted += 1
        return True

    def close(self, timeout: float = 5.0) -> None:
        """Let the worker drain the queue, then stop it and wait for it."""
        if not self._thread.is_alive():
            return
        deadline = time.monotonic() + timeout
        try:
            self._queue.put(_STOP, timeout=timeout)
        except queue.Full:
            return
        self._thread.join(max(0.0, deadline - time.monotonic()))

    def _run(self) -> None:
        sink: H264Sink | None = None
        try:
            width, height = self._size
            sink = H264Sink(
                self._url,
                width,
                height,
                self._settings.ai_fps,
                self._settings.ai_crf,
                self._settings,
            )
            while True:
                item = self._queue.get()
                if item is _STOP:
                    break
                frame, pts = item
                sink.write(frame, pts)
                self._stats.ai_frames_encoded += 1
        except BaseException as exc:  # noqa: BLE001 - recorded, then handled by owner
            self.error = exc
            logger.warning("AI branch stopped: %s: %s", type(exc).__name__, exc)
        finally:
            if sink is not None:
                sink.close()
