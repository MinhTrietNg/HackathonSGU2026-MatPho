"""Runtime configuration and stream naming for the Edge Decode Block.

Everything tunable lives in :class:`DecoderSettings`; one camera is described by
a :class:`StreamSpec` (where to read RTSP input from and where to publish HLS/RTSP outputs to).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit

_CAM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TRANSPORTS = frozenset({"tcp", "udp"})


class ConfigError(ValueError):
    """Raised when settings or a stream definition are invalid."""


def validate_cam_id(cam_id: str) -> str:
    """Return ``cam_id`` if it is safe to embed in an RTSP path."""
    if not _CAM_ID_RE.match(cam_id or ""):
        raise ConfigError(
            f"invalid cam_id {cam_id!r}: only [A-Za-z0-9_-] up to 64 chars allowed"
        )
    return cam_id


def redact_url(url: str) -> str:
    """Mask the password of an RTSP URL so it can be logged safely."""
    try:
        parts = urlsplit(url)
        if parts.password is None:
            return url
        host = parts.hostname or ""
        if ":" in host:  # IPv6 literal
            host = f"[{host}]"
        if parts.port:
            host = f"{host}:{parts.port}"
        netloc = f"{parts.username or ''}:***@{host}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))
    except ValueError:
        return "<invalid-url>"


_URL_CREDENTIALS_RE = re.compile(r"(rtsps?://[^\s:/@]+:)[^\s/]*@", re.IGNORECASE)


def redact_text(text: str) -> str:
    """Mask the password of every RTSP URL found inside free text."""
    return _URL_CREDENTIALS_RE.sub(r"\1***@", text)


@dataclass(frozen=True)
class DecoderSettings:
    """Tunable parameters of the Edge RTSP -> HLS/AI decode block.

    Standardized Routing (Q1 & Q4):
    - Input RTSP: Explicit LAN camera URL (e.g. ``rtsp://192.168.1.x:554/...``) or fallback ``source/{cam_id}``
    - Output App (HLS & AI Input): ``live/{cam_id}`` -> Served as HLS at ``http://<edge>:8888/live/{cam_id}/index.m3u8``
      and RTSP at ``rtsp://mediamtx:8554/live/{cam_id}``.
    - Output AI Sub-stream (optional when ``enable_ai_branch=True``): ``ai/{cam_id}``.
    """

    mediamtx_rtsp_url: str = "rtsp://mediamtx:8554"
    source_path_template: str = "source/{cam_id}"
    app_path_template: str = "live/{cam_id}"
    ai_path_template: str = "ai/{cam_id}"
    rtsp_transport: str = "tcp"
    open_timeout_s: float = 10.0
    read_timeout_s: float = 5.0
    enable_ai_branch: bool = False
    ai_fps: float = 3.0
    ai_max_edge: int = 640
    ai_crf: int = 26
    ai_queue_size: int = 2
    decode_threads: int = 2
    encode_threads: int = 2
    backoff_initial_s: float = 1.0
    backoff_max_s: float = 30.0
    stable_after_s: float = 30.0
    stats_interval_s: float = 30.0
    stream_mode: str = "always_on"
    live_idle_ttl_s: float = 60.0
    edge_public_hls_url: str = ""
    edge_public_webrtc_url: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "mediamtx_rtsp_url", self.mediamtx_rtsp_url.rstrip("/")
        )
        if not self.mediamtx_rtsp_url.startswith(("rtsp://", "rtsps://")):
            raise ConfigError("MEDIAMTX_RTSP_URL must start with rtsp://")
        for name in ("source_path_template", "app_path_template", "ai_path_template"):
            if "{cam_id}" not in getattr(self, name):
                raise ConfigError(f"{name} must contain {{cam_id}}")
        if len({self.source_path_template, self.app_path_template, self.ai_path_template}) != 3:
            raise ConfigError("source, app and ai path templates must differ to prevent stream loopback")
        if self.rtsp_transport not in _TRANSPORTS:
            raise ConfigError(f"rtsp_transport must be one of {sorted(_TRANSPORTS)}")
        if not 0 < self.ai_fps <= 30:
            raise ConfigError("ai_fps must be in (0, 30]")
        if self.ai_max_edge < 64:
            raise ConfigError("ai_max_edge must be >= 64")
        if not 0 <= self.ai_crf <= 51:
            raise ConfigError("ai_crf must be in [0, 51]")
        if self.ai_queue_size < 1:
            raise ConfigError("ai_queue_size must be >= 1")
        if self.decode_threads < 0 or self.encode_threads < 0:
            raise ConfigError("decode_threads and encode_threads must be >= 0")
        if self.open_timeout_s <= 0 or self.read_timeout_s <= 0:
            raise ConfigError("timeouts must be > 0")
        if not 0 < self.backoff_initial_s <= self.backoff_max_s:
            raise ConfigError("backoff must satisfy 0 < initial <= max")
        if self.stream_mode not in ("always_on", "on_demand"):
            raise ConfigError("stream_mode must be 'always_on' or 'on_demand'")
        if self.live_idle_ttl_s < 1.0:
            raise ConfigError("live_idle_ttl_s must be >= 1.0")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DecoderSettings:
        """Build settings from environment variables."""
        env = os.environ if env is None else env

        def pick(key: str, default, cast):
            raw = env.get(key)
            if raw is None or raw == "":
                return default
            try:
                return cast(raw)
            except ValueError as exc:
                raise ConfigError(f"{key}={raw!r} is not a valid value") from exc

        def parse_bool(val: str) -> bool:
            return val.strip().lower() in ("1", "true", "yes", "on")

        d = cls.__dataclass_fields__
        return cls(
            mediamtx_rtsp_url=pick("MEDIAMTX_RTSP_URL", d["mediamtx_rtsp_url"].default, str).rstrip("/"),
            source_path_template=pick("PATH_SOURCE_TEMPLATE", d["source_path_template"].default, str),
            app_path_template=pick("PATH_APP_TEMPLATE", d["app_path_template"].default, str),
            ai_path_template=pick("PATH_AI_TEMPLATE", d["ai_path_template"].default, str),
            rtsp_transport=pick("RTSP_TRANSPORT", d["rtsp_transport"].default, str).lower(),
            open_timeout_s=pick("RTSP_OPEN_TIMEOUT_S", d["open_timeout_s"].default, float),
            read_timeout_s=pick("RTSP_READ_TIMEOUT_S", d["read_timeout_s"].default, float),
            enable_ai_branch=pick("ENABLE_AI_BRANCH", d["enable_ai_branch"].default, parse_bool),
            ai_fps=pick("SUBSTREAM_TARGET_FPS", d["ai_fps"].default, float),
            ai_max_edge=pick("SUBSTREAM_MAX_EDGE", d["ai_max_edge"].default, int),
            ai_crf=pick("SUBSTREAM_CRF", d["ai_crf"].default, int),
            ai_queue_size=pick("SUBSTREAM_QUEUE_SIZE", d["ai_queue_size"].default, int),
            decode_threads=pick("DECODE_THREADS", d["decode_threads"].default, int),
            encode_threads=pick("ENCODE_THREADS", d["encode_threads"].default, int),
            backoff_initial_s=pick("RECONNECT_BACKOFF_INITIAL_S", d["backoff_initial_s"].default, float),
            backoff_max_s=pick("RECONNECT_BACKOFF_MAX_S", d["backoff_max_s"].default, float),
            stable_after_s=pick("RECONNECT_STABLE_AFTER_S", d["stable_after_s"].default, float),
            stats_interval_s=pick("STATS_INTERVAL_S", d["stats_interval_s"].default, float),
            stream_mode=pick("STREAM_MODE", d["stream_mode"].default, str).lower(),
            live_idle_ttl_s=pick("LIVE_IDLE_TTL_S", d["live_idle_ttl_s"].default, float),
            edge_public_hls_url=pick("EDGE_PUBLIC_HLS_URL", d["edge_public_hls_url"].default, str).rstrip("/"),
            edge_public_webrtc_url=pick("EDGE_PUBLIC_WEBRTC_URL", d["edge_public_webrtc_url"].default, str).rstrip("/"),
        )

    @property
    def stop_timeout_s(self) -> float:
        """Upper bound for a session to wind down after a stop request."""
        return self.open_timeout_s + self.read_timeout_s + 10.0

    def url_for(self, template: str, cam_id: str) -> str:
        """Return the full RTSP URL of ``template`` for ``cam_id``."""
        return f"{self.mediamtx_rtsp_url}/{template.format(cam_id=cam_id)}"


@dataclass(frozen=True)
class StreamSpec:
    """One camera handled by the decode block.

    - ``source_url``: Input RTSP stream (LAN camera or MediaMTX source path)
    - ``app_url``: Output RTSP stream published to MediaMTX ``live/{cam_id}`` (auto-converted by MediaMTX to HLS ``/live/{cam_id}/index.m3u8`` for App and RTSP for AI)
    - ``ai_url``: Optional downscaled AI sub-stream ``ai/{cam_id}``
    """

    cam_id: str
    source_url: str = field(repr=False)
    app_url: str
    ai_url: str

    @classmethod
    def for_camera(
        cls,
        cam_id: str,
        settings: DecoderSettings,
        source_url: str | None = None,
    ) -> StreamSpec:
        validate_cam_id(cam_id)
        if source_url is None:
            source_url = settings.url_for(settings.source_path_template, cam_id)
        elif not source_url.startswith(("rtsp://", "rtsps://")):
            raise ConfigError("source_url must start with rtsp://")
        app_url = settings.url_for(settings.app_path_template, cam_id)
        ai_url = settings.url_for(settings.ai_path_template, cam_id)
        if source_url.rstrip("/") in (app_url.rstrip("/"), ai_url.rstrip("/")):
            raise ConfigError("source_url equals an output URL (stream loop)")
        return cls(cam_id, source_url, app_url, ai_url)
