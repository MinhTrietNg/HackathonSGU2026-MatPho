"""Configuration settings for FireWatch AI Service (Master Spec v4.0)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class AISettings:
    """Runtime configuration read from environment variables."""

    # RTSP Server Endpoint (MediaMTX in Docker network)
    mediamtx_rtsp_url: str = os.getenv("MEDIAMTX_RTSP_URL", "rtsp://mediamtx:8554")

    # Local Edge Backend Controller API
    edge_backend_url: str = os.getenv("EDGE_BACKEND_URL", "http://edge-backend:8000")

    # Cloud Backend REST Webhook Endpoint
    cloud_backend_url: str = os.getenv("CLOUD_BACKEND_URL", "https://api.matpho.vn").rstrip("/")

    # Shared Secret Key for Webhook Authentication
    internal_api_secret_key: str = os.getenv(
        "INTERNAL_API_SECRET_KEY", "secure_internal_key_for_ai_and_worker_communication"
    )

    # Monitored Camera IDs (Comma-separated, or empty for dynamic discovery from edge-backend)
    ai_camera_ids: list[str] = field(
        default_factory=lambda: [
            c.strip()
            for c in os.getenv("AI_CAMERA_IDS", "cam_mock").split(",")
            if c.strip()
        ]
    )

    # Frame Sampling Rate (FPS) for AI Inference (1.0 to 3.0 FPS recommended)
    ai_sampling_fps: float = float(os.getenv("AI_SAMPLING_FPS", "1.0"))

    # Confidence Threshold to Trigger Alert (0.0 to 1.0)
    ai_confidence_threshold: float = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.60"))

    # Debounce cooldown in seconds to prevent spamming webhooks for the same incident
    alert_cooldown_seconds: float = float(os.getenv("ALERT_COOLDOWN_SECONDS", "30.0"))

    # Logging level
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def from_env(cls) -> AISettings:
        return cls()
