"""Helpers that fabricate camera-like sources and inspect block outputs."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av
import numpy as np


def make_source(
    path: Path,
    width: int = 1280,
    height: int = 720,
    fps: int = 25,
    seconds: int = 8,
    codec: str = "libx264",
    gop: int | None = None,
) -> Path:
    """Write a moving-pattern clip that mimics a camera's compressed stream."""
    gop = gop or fps
    out = av.open(str(path), "w")
    stream = out.add_stream(codec, rate=fps)
    stream.width, stream.height, stream.pix_fmt = width, height, "yuv420p"
    if codec == "libx264":
        stream.options = {"preset": "ultrafast", "g": str(gop), "bf": "0"}
    else:
        stream.options = {
            "preset": "ultrafast",
            "x265-params": f"keyint={gop}:log-level=error",
        }
    for i in range(fps * seconds):
        arr = np.zeros((height, width, 3), np.uint8)
        arr[:, :, 0] = (i * 5) % 255
        top = (i * 4) % max(1, height - 40)
        arr[top : top + 40, :, 1] = 255
        frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
        frame.pts = i
        frame.time_base = Fraction(1, fps)
        for packet in stream.encode(frame):
            out.mux(packet)
    for packet in stream.encode(None):
        out.mux(packet)
    out.close()
    return path


def corrupt_packets(src: Path, dst: Path, indices: set[int]) -> Path:
    """Copy ``src`` to ``dst`` replacing the payload of selected packets by noise."""
    rng = np.random.default_rng(1234)
    inp = av.open(str(src))
    in_stream = inp.streams.video[0]
    out = av.open(str(dst), "w")
    out_stream = out.add_stream_from_template(in_stream)
    for i, packet in enumerate(inp.demux(in_stream)):
        if packet.size == 0:
            continue
        if i in indices:
            noise = av.Packet(rng.integers(0, 256, packet.size, np.uint8).tobytes())
            noise.pts, noise.dts = packet.pts, packet.dts
            noise.time_base = packet.time_base
            noise.duration = packet.duration
            packet = noise
        packet.stream = out_stream
        out.mux(packet)
    out.close()
    inp.close()
    return dst


def cut_head(src: Path, dst: Path, skip: int) -> Path:
    """Copy ``src`` without its first ``skip`` packets, like a reader joining late."""
    inp = av.open(str(src))
    in_stream = inp.streams.video[0]
    out = av.open(str(dst), "w")
    out_stream = out.add_stream_from_template(in_stream)
    for i, packet in enumerate(inp.demux(in_stream)):
        if packet.size == 0 or i < skip:
            continue
        packet.stream = out_stream
        out.mux(packet)
    out.close()
    inp.close()
    return dst


@dataclass
class Probe:
    """What a consumer sees when it opens a block output."""

    codec: str
    width: int
    height: int
    packets: int
    keyframes: int
    frames: int
    times: list[float]
    payloads: list[bytes]

    @property
    def duration(self) -> float:
        return self.times[-1] - self.times[0] if len(self.times) > 1 else 0.0


def probe(path: Path) -> Probe:
    """Open ``path`` the way a reader would and gather its properties."""
    with av.open(str(path)) as c:
        v = c.streams.video[0]
        codec, width, height = v.codec_context.name, v.width, v.height
        packets = [p for p in c.demux(v) if p.size]
        payloads = [bytes(p) for p in packets]
        keyframes = sum(1 for p in packets if p.is_keyframe)
    with av.open(str(path)) as c:
        frames = list(c.decode(video=0))
    times = [float(f.time) for f in frames if f.time is not None]
    return Probe(
        codec, width, height, len(packets), keyframes, len(frames), times, payloads
    )


def source_payloads(path: Path) -> list[bytes]:
    """Return the compressed payload of every packet of ``path``."""
    with av.open(str(path)) as c:
        v = c.streams.video[0]
        return [bytes(p) for p in c.demux(v) if p.size]


def mean_luma(path: Path) -> float:
    """Average brightness of the first decoded frame (0 means a black picture)."""
    with av.open(str(path)) as c:
        for frame in c.decode(video=0):
            return float(frame.to_ndarray(format="gray").mean())
    return 0.0
