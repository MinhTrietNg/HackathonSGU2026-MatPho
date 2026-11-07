"""The output branches fed by one decoded source.

* Live branch (towards App): Lossless remux for H.264 (Zero-Copy), otherwise
  full-resolution H.264 transcode for non-H.264 sources.
* AI branch stub (towards Edge AI): Reserved plug-and-play seam for Team 1.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Protocol

import av

from .config import DecoderSettings
from .endpoints import StreamInfo
from .scaling import fit_even
from .sinks import CLOCK_HZ, CopySink, H264Sink
from .stats import SessionStats

logger = logging.getLogger("edge.branches")

_STOP = object()
_LIVE_TRANSCODE_CRF = 23


class LiveBranch(Protocol):
    """Interface of the branch that feeds the mobile app via MediaMTX."""

    mode: str

    def on_packet(self, packet: av.Packet) -> None:
        """Handle one compressed packet."""

    def on_frame(self, frame: av.VideoFrame, pts: int) -> None:
        """Handle one decoded frame with its 90 kHz timestamp."""

    def close(self) -> None:
        """Release the output sink."""


class CopyLiveBranch:
    """Forward source packets untouched; zero re-encoding cost (CPU < 1%)."""

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
        pass

    def close(self) -> None:
        self._sink.close()


class TranscodeLiveBranch:
    """Re-encode to H.264 at source resolution for non-H.264 sources."""

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
        pass

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
    logger.info("Source codec %s is not H.264: Live branch will transcode to H.264", info.codec)
    return TranscodeLiveBranch(url, info, settings, stats)


class AiBranchStub:
    """Seam for the AI sub-stream.

    When enable_ai_branch=False (default), it safely drops submitted frames
    without consuming CPU or RAM, while providing the exact interface needed
    when Team 1 plugs in the AI Model.
    """

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
        self.error: BaseException | None = None
        self._enabled = settings.enable_ai_branch
        self._queue: queue.Queue = queue.Queue(maxsize=settings.ai_queue_size)
        self._thread: threading.Thread | None = None
        self._t0: float | None = None

        if self._enabled:
            self._thread = threading.Thread(
                target=self._run, name="ai-branch", daemon=True
            )

    @property
    def size(self) -> tuple[int, int]:
        return self._size

    @property
    def failed(self) -> bool:
        return self.error is not None

    def start(self) -> None:
        if self._enabled and self._thread:
            self._thread.start()

    def submit(self, frame: av.VideoFrame, t: float) -> bool:
        if not self._enabled:
            return True
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

    def _run(self) -> None:
        sink: H264Sink | None = None
        try:
            sink = H264Sink(
                self._url,
                *self._size,
                self._settings.ai_fps,
                self._settings.ai_crf,
                1.0,
            )
            while True:
                item = self._queue.get()
                if item is _STOP:
                    break
                frame, pts = item
                sink.write(frame, pts)
                self._stats.ai_frames_encoded += 1
        except BaseException as exc:
            self.error = exc
            logger.warning("AI sub-stream worker died: %s", exc)
        finally:
            if sink is not None:
                sink.close()

    def close(self, timeout: float = 5.0) -> None:
        if not self._enabled or not self._thread:
            return
        try:
            self._queue.put_nowait(_STOP)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put(_STOP)
        self._thread.join(timeout)
