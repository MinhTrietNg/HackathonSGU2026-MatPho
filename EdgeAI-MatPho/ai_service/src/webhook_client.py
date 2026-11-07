"""HTTP Webhook Client for pushing AI detection events to Cloud Backend (Master Spec v4.0)."""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

import cv2
import httpx
import numpy as np

from .config import AISettings

logger = logging.getLogger("ai.webhook")


def encode_frame_to_base64_jpeg(frame_bgr: np.ndarray, quality: int = 85) -> str:
    """Encode an OpenCV BGR frame into a clean Base64 JPEG string."""
    success, buffer = cv2.imencode(
        ".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    )
    if not success:
        raise ValueError("Failed to encode frame to JPEG format")
    return base64.b64encode(buffer).decode("utf-8")


class CloudWebhookClient:
    """Dispatches detection events, verification signals, and suppression notices to Cloud Backend."""

    def __init__(self, settings: AISettings) -> None:
        self.settings = settings
        self.headers = {
            "Content-Type": "application/json",
            "X-Internal-Secret": settings.internal_api_secret_key,
        }

    async def report_fire_event(
        self,
        cam_id: str,
        class_name: str,
        confidence: float,
        bbox: list[float],
        frame_bgr: np.ndarray,
        timestamp: float | None = None,
    ) -> bool:
        """KÍCH HOẠT BÁO CHÁY CHÍNH THỨC (FCM Khẩn Cấp + Còi Hú 2 Tầng).

        Gửi Webhook lên Cloud Backend:
        POST /api/v1/internal/ai/fire-events
        """
        ts = timestamp or time.time()
        try:
            image_b64 = encode_frame_to_base64_jpeg(frame_bgr)
        except Exception as exc:
            logger.error("[%s] Error encoding snapshot: %s", cam_id, exc)
            image_b64 = None

        payload: dict[str, Any] = {
            "cam_id": cam_id,
            "class_name": class_name,
            "confidence": round(float(confidence), 3),
            "timestamp": float(ts),
            "bbox": [round(float(coord), 4) for coord in bbox],
            "image_base64": image_b64,
        }

        url = f"{self.settings.cloud_backend_url}/api/v1/internal/ai/fire-events"
        logger.info(
            "[%s] Dispatching FIRE_EVENT to Cloud (%s, confidence=%.2f, bbox=%s)...",
            cam_id,
            class_name,
            confidence,
            bbox,
        )

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(url, json=payload, headers=self.headers)
                if res.status_code in (200, 201, 202):
                    logger.info("[%s] Fire event accepted by Cloud Backend (HTTP %d).", cam_id, res.status_code)
                    return True
                logger.warning(
                    "[%s] Cloud Backend rejected fire event: HTTP %d - %s",
                    cam_id,
                    res.status_code,
                    res.text,
                )
                return False
        except Exception as exc:
            logger.error("[%s] Cloud WAN unreachable (%s) -> Queueing to Edge SQLite offline buffer...", cam_id, exc)
            await self._enqueue_offline_fallback(cam_id, payload)
            return False

    async def _enqueue_offline_fallback(self, cam_id: str, payload: dict[str, Any]) -> bool:
        """Store fire event in local Edge SQLite WAL queue (`POST /api/v1/edge/offline-events`) when WAN is down."""
        fallback_url = f"{self.settings.edge_backend_url}/api/v1/edge/offline-events"
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(
                    fallback_url,
                    json={"cam_id": cam_id, "event_type": "FIRE_DETECTED", "payload": payload},
                    headers=self.headers,
                )
                if res.status_code in (200, 201, 202):
                    logger.info("[%s] Saved fire event to Edge SQLite offline queue (Store-and-Forward).", cam_id)
                    return True
        except Exception as exc:
            logger.error("[%s] Offline SQLite queue fallback also failed: %s", cam_id, exc)
        return False

    async def report_verifying(
        self,
        cam_id: str,
        sign: str = "fire",
        confidence: float = 0.65,
        message: str = "Đang xác minh tín hiệu nghi vấn qua VLM...",
        steps: list[dict[str, Any]] | None = None,
    ) -> bool:
        """PHÁT TÍN HIỆU ĐANG XÁC MINH SỰ CỐ (Viền vàng E2a-E2c trên App).

        Gửi Webhook lên Cloud Backend:
        POST /api/v1/internal/ai/verifying
        """
        default_steps = [
            {"kind": "DETECTED", "name": "Mô hình phát hiện dấu hiệu nghi vấn", "at": time.time()},
            {"kind": "VERIFYING", "name": "Đang đối chiếu khung hình kiểm chứng", "at": time.time()},
        ]
        payload = {
            "cam_id": cam_id,
            "sign": sign,
            "confidence": round(float(confidence), 3),
            "message": message,
            "steps": steps or default_steps,
        }

        url = f"{self.settings.cloud_backend_url}/api/v1/internal/ai/verifying"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(url, json=payload, headers=self.headers)
                return res.status_code in (200, 201, 202)
        except Exception as exc:
            logger.warning("[%s] Failed to send verifying webhook: %s", cam_id, exc)
            return False

    async def report_suppressed(
        self,
        cam_id: str,
        summary: str = "Không phải cháy",
        detail: str = "AI kết luận: Ánh đèn phản chiếu hoặc vật thể bình thường.",
        alert_id: str | None = None,
    ) -> bool:
        """KẾT LUẬN BÁO GIẢ / HẠ CỜ BÁO ĐỘNG (Toast E4 xám trên App).

        Gửi Webhook lên Cloud Backend:
        POST /api/v1/internal/ai/suppressed
        """
        payload = {
            "cam_id": cam_id,
            "alert_id": alert_id,
            "summary": summary,
            "detail": detail,
        }

        url = f"{self.settings.cloud_backend_url}/api/v1/internal/ai/suppressed"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(url, json=payload, headers=self.headers)
                return res.status_code in (200, 201, 202)
        except Exception as exc:
            logger.warning("[%s] Failed to send suppressed webhook: %s", cam_id, exc)
            return False
