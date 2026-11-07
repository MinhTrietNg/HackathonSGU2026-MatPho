"""Open input and output containers with options tuned for live RTSP."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import av
from av.container import InputContainer, OutputContainer

from .config import DecoderSettings

_DEFAULT_FPS = 25.0


def is_rtsp(url: str) -> bool:
    """Return ``True`` for ``rtsp://`` and ``rtsps://`` URLs."""
    return url.lower().startswith(("rtsp://", "rtsps://"))


@dataclass(frozen=True)
class StreamInfo:
    """Properties of the probed source video stream."""

    codec: str
    width: int
    height: int
    fps: float

    @classmethod
    def from_stream(cls, stream: av.video.stream.VideoStream) -> StreamInfo:
        """Read properties from an opened input video stream."""
        ctx = stream.codec_context
        if not ctx.width or not ctx.height:
            raise ValueError("source did not report a picture size")
        rate = stream.average_rate or stream.guessed_rate
        fps = float(rate) if rate else _DEFAULT_FPS
        if not 0 < fps <= 120:
            fps = _DEFAULT_FPS
        return cls(ctx.name, ctx.width, ctx.height, fps)


def open_source(url: str, settings: DecoderSettings) -> InputContainer:
    """Open the input URL for demuxing with timeouts."""
    options: dict[str, str] = {}
    if is_rtsp(url):
        options = {
            "rtsp_transport": settings.rtsp_transport,
            "fflags": "nobuffer",
            "flags": "low_delay",
            "analyzeduration": "2000000",
            "probesize": "2000000",
        }
    return av.open(
        url,
        mode="r",
        options=options,
        timeout=(settings.open_timeout_s, settings.read_timeout_s),
    )


def open_sink(url: str, settings: DecoderSettings) -> OutputContainer:
    """Open the output URL for muxing (RTSP publish for rtsp:// URLs)."""
    timeout = (settings.open_timeout_s, settings.read_timeout_s)
    if is_rtsp(url):
        return av.open(
            url,
            mode="w",
            format="rtsp",
            options={"rtsp_transport": settings.rtsp_transport},
            timeout=timeout,
        )
    return av.open(url, mode="w", timeout=timeout)


def to_fraction(value: float) -> Fraction:
    """Convert a frame rate to a small-denominator Fraction."""
    return Fraction(value).limit_denominator(1000)
