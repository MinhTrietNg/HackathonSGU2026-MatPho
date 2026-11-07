"""One connection attempt: demux, decode once when needed, fan out to live and AI."""

from __future__ import annotations

import logging
import threading
import time
from fractions import Fraction

import av

from .branches import AiBranchStub, LiveBranch, make_live_branch
from .config import DecoderSettings, StreamSpec, redact_url
from .endpoints import StreamInfo, open_source
from .sampler import FrameRateSampler
from .sinks import CLOCK_HZ
from .stats import SessionStats

logger = logging.getLogger("edge.pipeline")

MAX_CONSECUTIVE_DECODE_ERRORS = 50
KEYFRAME_WARN_S = 10.0
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
        ai: AiBranchStub,
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

    def push(self, frame: av.VideoFrame) -> None:
        """Route one decoded frame."""
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
            self.ai.submit(frame, t)

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
    """Run one connection until source ends, an error occurs or stop event is set."""
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
    ai: AiBranchStub | None = None
    fanout: _FanOut | None = None
    try:
        in_stream = _pick_video_stream(container)
        in_stream.thread_type = "AUTO"
        in_stream.thread_count = settings.decode_threads
        info = StreamInfo.from_stream(in_stream)

        live = make_live_branch(spec.app_url, in_stream, info, settings, stats)
        ai = AiBranchStub(spec.ai_url, info, settings, stats)
        ai.start()
        fanout = _FanOut(spec, settings, stats, info, in_stream.time_base, live, ai)
        stats.mark_connected(info, live.mode)
        logger.info(
            "[cam_id=%s] connected %s: %s %dx%d @%.1ffps, live=%s, ai_enabled=%s",
            spec.cam_id,
            redact_url(spec.source_url),
            info.codec,
            info.width,
            info.height,
            info.fps,
            live.mode,
            settings.enable_ai_branch,
        )

        errors = 0
        need_key = True
        wait_since = time.monotonic()
        wait_reported = False
        stats.awaiting_keyframe = True
        end_of_stream = False

        # Zero-Copy Optimization:
        # If live branch is Copy and AI branch is disabled, we do NOT decode video packets!
        # This keeps CPU usage < 1% on H.264 streams.
        needs_decode = (live.mode == "transcode") or settings.enable_ai_branch

        for packet in container.demux(in_stream):
            if stop.is_set():
                break
            if packet.size == 0:
                end_of_stream = True
                break
            stats.packets_in += 1
            stats.last_packet_at = time.monotonic()

            frames: list[av.VideoFrame] = []
            if needs_decode:
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
            else:
                # Zero-Copy mode: only tracks keyframes for proper HLS cutting
                if packet.is_keyframe:
                    need_key = False
                    stats.awaiting_keyframe = False

            if need_key:
                now = time.monotonic()
                if not stats.awaiting_keyframe:
                    stats.awaiting_keyframe = True
                    wait_since, wait_reported = now, False
                if not wait_reported and now - wait_since >= KEYFRAME_WARN_S:
                    wait_reported = True
                    logger.warning(
                        "[cam_id=%s] no key frame for %gs: waiting for next I-frame",
                        spec.cam_id,
                        KEYFRAME_WARN_S,
                    )
            else:
                stats.awaiting_keyframe = False

            for frame in frames:
                fanout.push(frame)

            fanout.live.on_packet(packet)

            if (
                fanout.live.mode == "copy"
                and stats.packets_in >= LIVE_STALL_FRAMES
                and stats.live_packets_out == 0
            ):
                raise SourceError(
                    f"{stats.packets_in} packets in but none forwarded to app (check RTSP timestamps)"
                )

        if end_of_stream and not need_key and needs_decode:
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
