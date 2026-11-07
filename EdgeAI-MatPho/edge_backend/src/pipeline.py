"""One connection attempt: demux, decode once, fan out to live (HLS) and optional AI branches."""

from __future__ import annotations

import logging
import threading
import time
from fractions import Fraction

import av

from .branches import AiBranch, AiBranchStub, LiveBranch, make_live_branch
from .config import DecoderSettings, StreamSpec, redact_url
from .endpoints import StreamInfo, open_source
from .sampler import FrameRateSampler
from .sinks import CLOCK_HZ
from .stats import SessionStats

logger = logging.getLogger("stream-worker.pipeline")

# Consecutive undecodable packets tolerated before the connection is recycled.
MAX_CONSECUTIVE_DECODE_ERRORS = 50
# Delay between a failure of the AI branch and its rebuild (also between rebuilds).
AI_RESTART_INTERVAL_S = 5.0
# Waiting this long for a key frame is reported.
KEYFRAME_WARN_S = 10.0
# Decoded frames without a single packet forwarded to the app mean the live branch is discarding everything.
LIVE_STALL_FRAMES = 100


class SourceError(RuntimeError):
    """The source cannot be used (no video, changed format, too many errors)."""


class _FanOut:
    """Distribute decoded frames to the live and AI branches."""

    def __init__(
        self,
        spec: StreamSpec,
        settings: DecoderSettings,
        stats: SessionStats,
        info: StreamInfo,
        time_base: Fraction,
        live: LiveBranch,
        ai: AiBranch | AiBranchStub,
    ) -> None:
        self._spec = spec
        self._settings = settings
        self._stats = stats
        self._info = info
        self._time_base = time_base
        self.live = live
        self.ai = ai
        self._sampler = FrameRateSampler(settings.ai_fps)
        self._wall0 = time.monotonic()
        self._base_t: float | None = None
        self._ai_retry_at: float | None = None

    def push(self, frame: av.VideoFrame) -> None:
        """Route one decoded frame; the frame is owned by the AI branch after."""
        info = self._info
        if (frame.width, frame.height) != (info.width, info.height):
            raise SourceError(f"picture size changed to {frame.width}x{frame.height}")
        self._stats.frames_decoded += 1

        if frame.pts is None:
            t = time.monotonic() - self._wall0
        else:
            t = float(frame.pts * self._time_base)
        if self._base_t is None:
            self._base_t = t
        self.live.on_frame(frame, round((t - self._base_t) * CLOCK_HZ))

        if self._settings.enable_ai_branch and self._sampler.accept(t):
            self._rebuild_ai_if_needed()
            self.ai.submit(frame, t)

    def _rebuild_ai_if_needed(self) -> None:
        if not self._settings.enable_ai_branch:
            return
        if not self.ai.failed:
            self._ai_retry_at = None
            return
        now = time.monotonic()
        if self._ai_retry_at is None:
            self._ai_retry_at = now + AI_RESTART_INTERVAL_S
            return
        if now < self._ai_retry_at:
            return
        logger.warning(
            "[cam_id=%s] rebuilding AI branch: %s", self._spec.cam_id, self.ai.error
        )
        self.ai.close()
        self.ai = AiBranch(self._spec.ai_url, self._info, self._settings, self._stats)
        self.ai.start()
        self._stats.ai_restarts += 1
        self._ai_retry_at = None

    def close(self) -> None:
        self.ai.close()
        self.live.close()


def _pick_video_stream(container: av.container.InputContainer):
    if not container.streams.video:
        raise SourceError("source has no video stream")
    return container.streams.video[0]


def run_attempt(
    spec: StreamSpec,
    settings: DecoderSettings,
    stats: SessionStats,
    stop: threading.Event,
) -> None:
    """Run one connection until the source ends, an error occurs or ``stop``."""
    try:
        _run(spec, settings, stats, stop)
    except av.error.ExitError as exc:
        raise TimeoutError(
            f"no data from source within {settings.read_timeout_s:g}s "
            f"(open timeout {settings.open_timeout_s:g}s)"
        ) from exc


def _run(
    spec: StreamSpec,
    settings: DecoderSettings,
    stats: SessionStats,
    stop: threading.Event,
) -> None:
    container = open_source(spec.source_url, settings)
    live: LiveBranch | None = None
    ai: AiBranch | AiBranchStub | None = None
    fanout: _FanOut | None = None
    try:
        in_stream = _pick_video_stream(container)
        in_stream.thread_type = "AUTO"
        in_stream.thread_count = settings.decode_threads
        info = StreamInfo.from_stream(in_stream)

        live = make_live_branch(spec.app_url, in_stream, info, settings, stats)
        if settings.enable_ai_branch:
            ai = AiBranch(spec.ai_url, info, settings, stats)
            ai.start()
        else:
            ai = AiBranchStub()
        fanout = _FanOut(spec, settings, stats, info, in_stream.time_base, live, ai)
        stats.mark_connected(info, live.mode)
        logger.info(
            "[cam_id=%s] connected %s: %s %dx%d @%.1ffps, live=%s, ai_branch=%s",
            spec.cam_id, redact_url(spec.source_url), info.codec, info.width,
            info.height, info.fps, live.mode, settings.enable_ai_branch,
        )

        errors = 0
        need_key = True
        wait_since = time.monotonic()
        wait_reported = False
        stats.awaiting_keyframe = True
        end_of_stream = False
        for packet in container.demux(in_stream):
            if stop.is_set():
                break
            if packet.size == 0:
                end_of_stream = True
                break
            stats.packets_in += 1
            stats.last_packet_at = time.monotonic()

            frames: list[av.VideoFrame] = []
            if packet.is_keyframe or not need_key:
                try:
                    frames = in_stream.decode(packet)
                    errors = 0
                    need_key = False
                except av.FFmpegError as exc:
                    errors += 1
                    stats.decode_errors += 1
                    need_key = True
                    in_stream.codec_context.flush_buffers()
                    if errors > MAX_CONSECUTIVE_DECODE_ERRORS:
                        raise SourceError(
                            f"{errors} consecutive decode errors, last: {exc}"
                        ) from exc

            if need_key:
                now = time.monotonic()
                if not stats.awaiting_keyframe:
                    stats.awaiting_keyframe = True
                    wait_since, wait_reported = now, False
                if not wait_reported and now - wait_since >= KEYFRAME_WARN_S:
                    wait_reported = True
                    logger.warning(
                        "[cam_id=%s] no key frame for %gs: output starts at the "
                        "camera's next I-frame (check its I-frame interval)",
                        spec.cam_id, KEYFRAME_WARN_S,
                    )
            else:
                stats.awaiting_keyframe = False

            for frame in frames:
                fanout.push(frame)
            fanout.live.on_packet(packet)
            if (
                fanout.live.mode == "copy"
                and stats.frames_decoded >= LIVE_STALL_FRAMES
                and stats.live_packets_out == 0
            ):
                raise SourceError(
                    f"{stats.frames_decoded} frames decoded but none forwarded "
                    "to the app stream (packets without usable DTS?)"
                )

        if end_of_stream and not need_key:
            for frame in in_stream.decode(None):
                fanout.push(frame)
    finally:
        if fanout is not None:
            fanout.close()
        else:
            if ai is not None:
                ai.close()
            if live is not None:
                live.close()
        container.close()
