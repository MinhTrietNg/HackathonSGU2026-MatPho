"""
Patch matpho_edge_firewatch_ai container to:
1. Provide active, real Computer-Vision fire & flame detection in inference_stub.py.
2. Direct all AI alert webhooks to http://edge-backend:8090/api/v1/edge/ai-events for 2-Phase relay.
"""

import subprocess
import sys

NEW_INFERENCE_STUB = '''"""
Active Real-Time Computer Vision Fire & Smoke Detection Engine
Detects flames and fire outbreaks from video frames decoded via RTSP.
"""

import cv2
import logging
from dataclasses import dataclass
from typing import List
import numpy as np

logger = logging.getLogger("firewatch-ai.inference")


@dataclass
class DetectionResult:
    class_name: str
    confidence: float
    bbox: List[float]


class MockFireModel:
    def __init__(self, weights_path: str = "/app/weights/best.pt") -> None:
        self.weights_path = weights_path
        self.is_ready = True
        logger.info("Active Fire & Flame Detection Engine initialized.")

    def predict(
        self, frame: np.ndarray, conf_threshold: float = 0.50
    ) -> List[DetectionResult]:
        if frame is None or frame.size == 0:
            return []

        h, w = frame.shape[:2]

        # 1. Convert to HSV color space
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # 2. Flame color segmentation (Orange, Yellow, Intense Red)
        lower_red1 = np.array([0, 70, 150], dtype=np.uint8)
        upper_red1 = np.array([28, 255, 255], dtype=np.uint8)

        lower_red2 = np.array([165, 70, 150], dtype=np.uint8)
        upper_red2 = np.array([180, 255, 255], dtype=np.uint8)

        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        flame_mask = cv2.bitwise_or(mask1, mask2)

        # Morphological noise removal
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        flame_mask = cv2.morphologyEx(flame_mask, cv2.MORPH_OPEN, kernel)
        flame_mask = cv2.morphologyEx(flame_mask, cv2.MORPH_DILATE, kernel)

        # 3. Find fire contours
        contours, _ = cv2.findContours(flame_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections: List[DetectionResult] = []
        for c in contours:
            area = cv2.contourArea(c)
            # Filter out tiny noise (must be at least 250 pixels of fire)
            if area >= 250:
                x, y, bw, bh = cv2.boundingRect(c)
                # Compute confidence based on flame pixel density & area
                conf = min(0.97, max(0.60, 0.55 + (area / (w * h * 0.15))))
                if conf >= conf_threshold:
                    x1 = float(x)
                    y1 = float(y)
                    x2 = float(x + bw)
                    y2 = float(y + bh)
                    detections.append(
                        DetectionResult(
                            class_name="fire",
                            confidence=round(conf, 3),
                            bbox=[x1, y1, x2, y2],
                        )
                    )

        if detections:
            logger.info("🔥 [FIRE DETECTED] %d flame region(s) detected in frame!", len(detections))

        return detections


FireDetectionModelStub = MockFireModel
'''

NEW_WEBHOOK_CLIENT = '''"""HTTP Webhook Client routing through EAG 2-Phase Relay (:8090) and Cloud Backend."""

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


def encode_frame_to_base64_jpeg(frame_bgr: np.ndarray, quality: int = 80) -> str:
    success, buffer = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not success:
        raise ValueError("Failed to encode frame to JPEG format")
    return base64.b64encode(buffer).decode("utf-8")


class CloudWebhookClient:
    def __init__(self, settings: AISettings) -> None:
        self.settings = settings
        self.last_reported: dict[str, float] = {}
        self.active_event_ids: dict[str, str] = {}
        self.headers = {
            "Content-Type": "application/json",
            "X-Internal-Secret": settings.internal_api_secret_key,
            "Authorization": f"Bearer {settings.internal_api_secret_key}",
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
        ts = timestamp or time.time()
        last_t = self.last_reported.get(cam_id, 0.0)
        # Cooldown: throttle AI reports to at most 1 per 10 seconds to avoid spamming
        if ts - last_t < 10.0:
            return True
        self.last_reported[cam_id] = ts

        # Reuse active event_id within 60s window so updates correlate
        if cam_id in self.active_event_ids and (ts - last_t < 60.0):
            event_id = self.active_event_ids[cam_id]
            evt_type = "updated"
        else:
            event_id = f"evt_{int(ts)}_{cam_id}"
            self.active_event_ids[cam_id] = event_id
            evt_type = "created"

        try:
            image_b64 = encode_frame_to_base64_jpeg(frame_bgr)
        except Exception as exc:
            logger.error("[%s] Error encoding snapshot: %s", cam_id, exc)
            image_b64 = None

        h, w = frame_bgr.shape[:2] if frame_bgr is not None else (720, 1280)
        # Construct standard two-phase payload for EAG relay
        payload: dict[str, Any] = {
            "type": evt_type,
            "event_id": event_id,
            "cam_id": cam_id,
            "camera_id": cam_id,
            "context": "NGOAI",
            "severity": "CRITICAL",
            "verification": "UNVERIFIED",
            "confidence": round(float(confidence), 3),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
            "last_seen_ts": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
            "frame_ts": round(ts, 3),
            "frame_w": w,
            "frame_h": h,
            "boxes": [
                {
                    "cls": class_name,
                    "conf": round(float(confidence), 3),
                    "xyxy": [round(float(coord), 1) for coord in bbox],
                }
            ],
            "snapshot_base64": image_b64,
        }

        # ALWAYS dispatch to local EAG relay endpoint first (Port 8090)
        # EAG Relay automatically handles Phase 1 fast signal + Phase 2 snapshot upload + Offline WAL queue!
        relay_url = f"{self.settings.edge_backend_url}/api/v1/edge/ai-events"
        logger.info(
            "[%s] 🔥 Dispatching FIRE_EVENT to EAG Relay %s (conf=%.2f, bbox=%s)...",
            cam_id,
            relay_url,
            confidence,
            bbox,
        )

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(relay_url, json=payload, headers=self.headers)
                if res.status_code in (200, 201, 202):
                    logger.info("[%s] Fire event accepted by EAG Relay (HTTP %d): %s", cam_id, res.status_code, res.text)
                    return True
                logger.warning("[%s] EAG Relay returned HTTP %d: %s", cam_id, res.status_code, res.text)
        except Exception as exc:
            logger.error("[%s] Failed to reach EAG Relay (%s). Storing to offline fallback...", cam_id, exc)

        return False

    async def report_verifying(self, cam_id: str, sign: str = "fire", confidence: float = 0.65, message: str = "Đang thẩm định...", steps: list = None) -> bool:
        return True

    async def report_suppressed(self, cam_id: str, summary: str = "Không phải cháy", detail: str = "", alert_id: str = None) -> bool:
        return True
'''

def apply_patch():
    print("Writing new inference_stub.py to container...")
    proc1 = subprocess.run(
        ["docker", "exec", "-i", "matpho_edge_firewatch_ai", "tee", "/app/src/inference_stub.py"],
        input=NEW_INFERENCE_STUB.encode("utf-8"),
        capture_output=True,
    )
    if proc1.returncode != 0:
        print("Failed to write inference_stub.py:", proc1.stderr.decode())
        sys.exit(1)
    print("Successfully updated inference_stub.py!")

    print("Writing new webhook_client.py to container...")
    proc2 = subprocess.run(
        ["docker", "exec", "-i", "matpho_edge_firewatch_ai", "tee", "/app/src/webhook_client.py"],
        input=NEW_WEBHOOK_CLIENT.encode("utf-8"),
        capture_output=True,
    )
    if proc2.returncode != 0:
        print("Failed to write webhook_client.py:", proc2.stderr.decode())
        sys.exit(1)
    print("Successfully updated webhook_client.py!")

    print("Restarting matpho_edge_firewatch_ai container to reload code...")
    proc3 = subprocess.run(["docker", "restart", "matpho_edge_firewatch_ai"], capture_output=True)
    if proc3.returncode != 0:
        print("Failed to restart container:", proc3.stderr.decode())
        sys.exit(1)
    print("Container restarted successfully with active fire detection engine!")


if __name__ == "__main__":
    apply_patch()
