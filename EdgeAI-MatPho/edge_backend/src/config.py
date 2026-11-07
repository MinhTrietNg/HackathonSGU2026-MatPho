"""Runtime configuration and stream naming for EdgeAI-MatPho (Master Spec v4.0)."""

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
    """Tunable parameters of the Edge decode block."""

    edge_device_id: str = "edg_local_01"
    mediamtx_rtsp_url: str = "rtsp://mediamtx:8554"
    mediamtx_api_url: str = "http://mediamtx:9997"
    cloud_backend_url: str = "https://api.matpho.vn"
    cloud_backend_ws_url: str = "wss://api.matpho.vn/api/v1/internal/edge/ws"
    internal_api_secret_key: str = "secure_internal_key_for_ai_and_worker_communication"
    sqlite_db_path: str = "/app/data/edge.db"

    # Streaming path templates (Standardized 100% to live/{cam_id})
    source_path_template: str = "live/{cam_id}"
    app_path_template: str = "live/{cam_id}"
    ai_path_template: str = "live/{cam_id}"

    # RTSP and networking options
    rtsp_transport: str = "tcp"
    open_timeout_s: float = 10.0
    read_timeout_s: float = 5.0
    decode_threads: int = 2
    encode_threads: int = 2

    # AI Sub-stream options (Plug-and-play seam for Team 1)
    enable_ai_branch: bool = False
    ai_fps: float = 3.0
    ai_max_edge: int = 640
    ai_crf: int = 26
    ai_queue_size: int = 2

    # Reconnect backoff parameters
    backoff_initial_s: float = 1.0
    backoff_max_s: float = 30.0
    stable_after_s: float = 30.0
    stop_timeout_s: float = 12.0
    stats_interval_s: float = 30.0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DecoderSettings:
        """Build settings from environment variables."""
        if env is None:
            env = os.environ

        def _str(key: str, default: str) -> str:
            return env.get(key, "").strip() or default

        def _bool(key: str, default: bool) -> bool:
            v = env.get(key, "").strip().lower()
            if not v:
                return default
            return v in ("1", "true", "yes", "on")

        def _float(key: str, default: float) -> float:
            raw = env.get(key, "").strip()
            if not raw:
                return default
            try:
                val = float(raw)
            except ValueError as exc:
                raise ConfigError(f"{key} must be a number: {exc}") from exc
            if val <= 0:
                raise ConfigError(f"{key} must be positive, got {val:g}")
            return val

        def _int(key: str, default: int) -> int:
            raw = env.get(key, "").strip()
            if not raw:
                return default
            try:
                val = int(raw)
            except ValueError as exc:
                raise ConfigError(f"{key} must be an integer: {exc}") from exc
            if val < 0:
                raise ConfigError(f"{key} must be non-negative, got {val}")
            return val

        transport = _str("RTSP_TRANSPORT", "tcp").lower()
        if transport not in _TRANSPORTS:
            raise ConfigError(
                f"RTSP_TRANSPORT must be one of {sorted(_TRANSPORTS)}, got {transport!r}"
            )

        return cls(
            edge_device_id=_str("EDGE_DEVICE_ID", "edg_local_01"),
            mediamtx_rtsp_url=_str("MEDIAMTX_RTSP_URL", "rtsp://mediamtx:8554").rstrip("/"),
            mediamtx_api_url=_str("MEDIAMTX_API_URL", "http://mediamtx:9997").rstrip("/"),
            cloud_backend_url=_str("CLOUD_BACKEND_URL", "https://api.matpho.vn").rstrip("/"),
            cloud_backend_ws_url=_str("CLOUD_BACKEND_WS_URL", "wss://api.matpho.vn/api/v1/internal/edge/ws"),
            internal_api_secret_key=_str("INTERNAL_API_SECRET_KEY", "secure_internal_key_for_ai_and_worker_communication"),
            sqlite_db_path=_str("SQLITE_DB_PATH", "/app/data/edge.db"),
            source_path_template=_str("PATH_SOURCE_TEMPLATE", "live/{cam_id}"),
            app_path_template=_str("PATH_APP_TEMPLATE", "live/{cam_id}"),
            ai_path_template=_str("PATH_AI_TEMPLATE", "live/{cam_id}"),
            rtsp_transport=transport,
            open_timeout_s=_float("RTSP_OPEN_TIMEOUT_S", 10.0),
            read_timeout_s=_float("RTSP_READ_TIMEOUT_S", 5.0),
            decode_threads=_int("DECODE_THREADS", 2),
            encode_threads=_int("ENCODE_THREADS", 2),
            enable_ai_branch=_bool("ENABLE_AI_BRANCH", False),
            ai_fps=_float("SUBSTREAM_TARGET_FPS", 3.0),
            ai_max_edge=_int("SUBSTREAM_MAX_EDGE", 640),
            ai_crf=_int("SUBSTREAM_CRF", 26),
            ai_queue_size=_int("SUBSTREAM_QUEUE_SIZE", 2),
            backoff_initial_s=_float("RECONNECT_BACKOFF_INITIAL_S", 1.0),
            backoff_max_s=_float("RECONNECT_BACKOFF_MAX_S", 30.0),
            stable_after_s=_float("RECONNECT_STABLE_AFTER_S", 30.0),
            stats_interval_s=_float("STATS_INTERVAL_S", 30.0),
            log_level=_str("LOG_LEVEL", "INFO").upper(),
        )


@dataclass(frozen=True)
class StreamSpec:
    """URLs and settings for a single camera session."""

    cam_id: str
    source_url: str
    app_url: str
    ai_url: str

    @classmethod
    def for_camera(
        cls,
        cam_id: str,
        settings: DecoderSettings,
        source_url: str | None = None,
    ) -> StreamSpec:
        """Derive the source, app and ai URLs for a given camera."""
        valid_id = validate_cam_id(cam_id)
        if not source_url:
            src_path = settings.source_path_template.format(cam_id=valid_id)
            source_url = f"{settings.mediamtx_rtsp_url}/{src_path}"

        app_path = settings.app_path_template.format(cam_id=valid_id)
        ai_path = settings.ai_path_template.format(cam_id=valid_id)

        return cls(
            cam_id=valid_id,
            source_url=source_url,
            app_url=f"{settings.mediamtx_rtsp_url}/{app_path}",
            ai_url=f"{settings.mediamtx_rtsp_url}/{ai_path}",
        )
