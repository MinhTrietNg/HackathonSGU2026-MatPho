"""Configuration settings for FireWatch AI Service Skeleton (1 Input RTSP -> 1 Output Webhook)."""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Union

WatchAreaInput = Union[Dict[str, float], List[List[float]]]


@dataclass
class CameraStreamTarget:
    """Single camera target for AI RTSP ingestion."""

    cam_id: str
    watch_area: Optional[WatchAreaInput] = None


@dataclass
class AISettings:
    """Runtime configuration read from environment variables."""

    # 1. Input RTSP Server Endpoint (MediaMTX in Docker network)
    mediamtx_rtsp_url: str = field(
        default_factory=lambda: os.getenv("MEDIAMTX_RTSP_URL", "rtsp://mediamtx:8554").rstrip("/")
    )
    stream_path_template: str = field(
        default_factory=lambda: os.getenv("STREAM_PATH_TEMPLATE", "live/{cam_id}")
    )

    # 2. Local Edge Backend Controller API (for offline fallback)
    edge_backend_url: str = field(
        default_factory=lambda: os.getenv("EDGE_BACKEND_URL", os.getenv("EDGE_BACKEND_API_URL", "http://edge-backend:8090")).rstrip("/")
    )

    # 3. Output Cloud Backend REST Webhook Endpoint
    cloud_backend_url: str = field(
        default_factory=lambda: os.getenv("CLOUD_BACKEND_URL", os.getenv("CLOUD_BACKEND_API_URL", "https://api.matpho.vn")).rstrip("/")
    )

    # Shared Secret Key for Webhook Authentication
    internal_api_secret_key: str = field(
        default_factory=lambda: os.getenv(
            "INTERNAL_API_SECRET_KEY", "secure_internal_key_for_ai_and_worker_communication"
        )
    )

    # Monitored Camera IDs
    ai_camera_ids: list[str] = field(
        default_factory=lambda: [
            c.strip()
            for c in os.getenv("AI_CAMERA_IDS", "cam_01").split(",")
            if c.strip()
        ]
    )

    # Frame Sampling Rate (FPS) for AI Inference (1.0 to 3.0 FPS recommended)
    ai_sampling_fps: float = field(
        default_factory=lambda: float(os.getenv("AI_SAMPLING_FPS", os.getenv("AI_TARGET_FPS", "1.0")))
    )

    # Confidence Threshold to Trigger Alert (0.0 to 1.0)
    ai_confidence_threshold: float = field(
        default_factory=lambda: float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.60"))
    )

    # Debounce cooldown in seconds to prevent spamming webhooks for the same incident
    alert_cooldown_seconds: float = field(
        default_factory=lambda: float(os.getenv("ALERT_COOLDOWN_SECONDS", os.getenv("AI_ALERT_COOLDOWN_S", "30.0")))
    )

    # Weights path for AI Team model
    model_weights_path: str = field(
        default_factory=lambda: os.getenv("AI_MODEL_WEIGHTS_PATH", "/app/weights/best.pt")
    )

    # Logging level
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper()
    )

    def rtsp_url_for(self, cam_id: str) -> str:
        """Return the standardized RTSP input URL: `rtsp://mediamtx:8554/live/{cam_id}`."""
        return f"{self.mediamtx_rtsp_url}/{self.stream_path_template.format(cam_id=cam_id)}"

    @property
    def camera_streams(self) -> List[CameraStreamTarget]:
        raw_json = os.getenv("AI_CAMERA_STREAMS", "").strip()
        if raw_json:
            try:
                items = json.loads(raw_json)
                if isinstance(items, list):
                    return [
                        CameraStreamTarget(
                            cam_id=str(x["cam_id"]),
                            watch_area=x.get("watch_area"),
                        )
                        for x in items
                        if isinstance(x, dict) and "cam_id" in x
                    ]
            except Exception:
                pass
        return [CameraStreamTarget(cam_id=cid) for cid in self.ai_camera_ids]

    @classmethod
    def from_env(cls) -> AISettings:
        return cls()


AIServiceSettings = AISettings
