"""Output writers: a lossless remuxer (CopySink) and an H.264 encoder (H264Sink)."""

from __future__ import annotations

import logging
from fractions import Fraction

import av

from .config import DecoderSettings
from .endpoints import open_sink, to_fraction

logger = logging.getLogger("edge.sinks")

CLOCK_HZ = 90_000
_CLOCK_TB = Fraction(1, CLOCK_HZ)


def _close_quietly(container: av.container.OutputContainer) -> None:
    """Close container and log, rather than raise, any failure."""
    try:
        container.close()
    except (av.FFmpegError, OSError) as exc:
        logger.debug("error while closing output: %s", exc)


class CopySink:
    """Remux compressed packets 1:1 into MediaMTX without re-encoding (Zero-Copy)."""

    def __init__(
        self,
        url: str,
        in_stream: av.video.stream.VideoStream,
        settings: DecoderSettings,
    ) -> None:
        self._out = open_sink(url, settings)
        self._stream = self._out.add_stream_from_template(in_stream)
        self._started = False
        self._last_dts: int | None = None
        self.packets_written = 0
        self.packets_dropped = 0

    def write(self, packet: av.Packet) -> bool:
        """Mux packet; return False if dropped (e.g. non-monotonic DTS)."""
        if not self._started:
            if not packet.is_keyframe:
                return False
            self._started = True
        if packet.dts is None or (
            self._last_dts is not None and packet.dts <= self._last_dts
        ):
            self.packets_dropped += 1
            return False
        self._last_dts = packet.dts
        packet.stream = self._stream
        self._out.mux(packet)
        self.packets_written += 1
        return True

    def close(self) -> None:
        """Finish output (RTSP TEARDOWN)."""
        _close_quietly(self._out)


class H264Sink:
    """Encode frames to H.264 (libx264, low latency) and mux them."""

    def __init__(
        self,
        url: str,
        width: int,
        height: int,
        fps: float,
        crf: int,
        settings: DecoderSettings,
        gop_seconds: float = 1.0,
    ) -> None:
        self._out = open_sink(url, settings)
        self._width = width
        self._height = height
        stream = self._out.add_stream("libx264", rate=to_fraction(fps))
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.codec_context.time_base = _CLOCK_TB
        stream.options = {
            "preset": "veryfast",
            "tune": "zerolatency",
            "crf": str(crf),
            "g": str(max(1, round(fps * gop_seconds))),
            "threads": str(settings.encode_threads),
        }
        self._stream = stream
        self._last_pts = -1
        self.frames_written = 0

    def write(self, frame: av.VideoFrame, pts: int) -> None:
        """Scale, encode and mux one frame."""
        scaled = frame.reformat(
            width=self._width,
            height=self._height,
            format="yuv420p",
            interpolation="AREA",
        )
        self._last_pts = max(pts, self._last_pts + 1)
        scaled.pts = self._last_pts
        scaled.time_base = _CLOCK_TB
        scaled.pict_type = av.video.frame.PictureType.NONE
        for packet in self._stream.encode(scaled):
            self._out.mux(packet)
        self.frames_written += 1

    def close(self) -> None:
        """Flush encoder and finish output."""
        try:
            for packet in self._stream.encode(None):
                self._out.mux(packet)
        except (av.FFmpegError, OSError) as exc:
            logger.debug("error while flushing encoder: %s", exc)
        _close_quietly(self._out)
