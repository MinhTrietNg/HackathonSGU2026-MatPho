"""FireWatch AI Service - Edge Ingestion & Inference Runner (Master Spec v4.0).

Connects to MediaMTX RTSP streams (live/{cam_id}), samples frames at controlled FPS,
applies polygon watch_area masking, invokes black-box AI model, and dispatches fire incident
webhooks to Cloud Backend.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any

import cv2
import httpx
import numpy as np

from .config import AISettings
from .inference_stub import DetectionResult, MockFireModel
from .masking import apply_watch_area_mask
from .webhook_client import CloudWebhookClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [AI-WORKER] %(message)s",
)
logger = logging.getLogger("ai.main")


class CameraMonitorThread(threading.Thread):
    """Monitors one camera stream, performs sampling, watch_area masking, inference, and alert dispatching."""

    def __init__(
        self,
        cam_id: str,
        settings: AISettings,
        model: MockFireModel,
        webhook_client: CloudWebhookClient,
        loop: asyncio.AbstractEventLoop,
        watch_area: list[Any] | None = None,
    ) -> None:
        super().__init__(name=f"ai-cam-{cam_id}", daemon=True)
        self.cam_id = cam_id
        self.settings = settings
        self.model = model
        self.webhook_client = webhook_client
        self.loop = loop
        self.watch_area = watch_area
        self._stop_event = threading.Event()
        self._last_alert_time = 0.0

    def stop(self) -> None:
        self._stop_event.set()

    def update_watch_area(self, watch_area: list[Any] | None) -> None:
        """Dynamically update polygon watch area without restarting stream."""
        self.watch_area = watch_area

    def run(self) -> None:
        # Đường dẫn RTSP: Chuẩn hóa 100% sang live/{cam_id}
        rtsp_url = f"{self.settings.mediamtx_rtsp_url}/live/{self.cam_id}"
        sample_interval = 1.0 / max(0.1, self.settings.ai_sampling_fps)

        logger.info(
            "[%s] Starting AI monitoring thread -> %s (sampling: %.1f FPS, watch_area=%s)",
            self.cam_id,
            rtsp_url,
            self.settings.ai_sampling_fps,
            bool(self.watch_area),
        )

        while not self._stop_event.is_set():
            # Thiết lập FFMPEG qua TCP để chống rụng gói tin mạng
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                logger.warning("[%s] Cannot open RTSP stream. Retrying in 5s...", self.cam_id)
                time.sleep(5)
                continue

            logger.info("[%s] RTSP stream connected successfully! Processing frames...", self.cam_id)
            last_sample_t = 0.0

            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret or frame is None:
                    logger.warning("[%s] Lost video frame from stream. Reconnecting...", self.cam_id)
                    break

                now = time.monotonic()
                if (now - last_sample_t) < sample_interval:
                    continue  # Bỏ qua frame để duy trì tần suất quét mong muốn (1 FPS)

                last_sample_t = now

                # 1. Áp dụng đa giác watch_area để loại bỏ vùng nhiễu (bếp gas, lò sưởi)
                masked_frame = apply_watch_area_mask(frame, self.watch_area)

                # 2. Gọi hàm suy luận của mô hình AI (Hộp đen)
                try:
                    detections: list[DetectionResult] = self.model.predict(masked_frame)
                except Exception as exc:
                    logger.error("[%s] Error during model inference: %s", self.cam_id, exc)
                    continue

                # 3. Xử lý kết quả phát hiện
                for det in detections:
                    if det.confidence >= self.settings.ai_confidence_threshold:
                        current_epoch = time.time()
                        # Kiểm tra thời gian hồi phục để tránh spam webhook liên tục trong 1 sự cố
                        if (current_epoch - self._last_alert_time) >= self.settings.alert_cooldown_seconds:
                            self._last_alert_time = current_epoch
                            logger.warning(
                                "[%s] FIRE DETECTED! Class: %s, Confidence: %.2f",
                                self.cam_id,
                                det.class_name,
                                det.confidence,
                            )
                            # Bắn webhook bất đồng bộ lên Cloud Backend
                            asyncio.run_coroutine_threadsafe(
                                self.webhook_client.report_fire_event(
                                    cam_id=self.cam_id,
                                    class_name=det.class_name,
                                    confidence=det.confidence,
                                    bbox=det.bbox,
                                    frame_bgr=frame,
                                    timestamp=current_epoch,
                                ),
                                self.loop,
                            )

            cap.release()
            time.sleep(2)


async def discover_active_cameras(settings: AISettings) -> list[str]:
    """Tự động hỏi Edge Backend danh sách camera đang chạy."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(f"{settings.edge_backend_url}/api/v1/status")
            if res.status_code == 200:
                data = res.json()
                sessions = data.get("sessions", {})
                active_cams = [cid for cid, s in sessions.items() if s.get("state") == "running"]
                if active_cams:
                    return active_cams
    except Exception as exc:
        logger.debug("Failed to query edge-backend status: %s", exc)
    return settings.ai_camera_ids


async def main() -> None:
    settings = AISettings.from_env()
    logger.info("Initializing FireWatch AI Service (Master Spec v4.0)...")
    logger.info("MediaMTX: %s | Cloud Backend: %s", settings.mediamtx_rtsp_url, settings.cloud_backend_url)

    # 1. Khởi tạo mô hình AI (Trọng số đặt trong /app/weights)
    weights_path = os.getenv("AI_WEIGHTS_PATH", "/app/weights/firewatch_model.pt")
    model = MockFireModel(weights_path=weights_path if os.path.exists(weights_path) else None)

    # 2. Khởi tạo Webhook Client
    webhook_client = CloudWebhookClient(settings)

    # 3. Quản lý luồng giám sát camera
    loop = asyncio.get_running_loop()
    monitored_threads: dict[str, CameraMonitorThread] = {}

    try:
        while True:
            # Phát hiện camera cần giám sát
            cam_list = await discover_active_cameras(settings)

            # Khởi động thread mới cho camera chưa được giám sát
            for cam_id in cam_list:
                if cam_id not in monitored_threads or not monitored_threads[cam_id].is_alive():
                    thread = CameraMonitorThread(cam_id, settings, model, webhook_client, loop)
                    thread.start()
                    monitored_threads[cam_id] = thread

            # Dọn dẹp thread của camera đã dừng
            for cam_id, thread in list(monitored_threads.items()):
                if cam_id not in cam_list:
                    logger.info("[%s] Camera no longer active, stopping AI monitor.", cam_id)
                    thread.stop()
                    thread.join(timeout=2.0)
                    del monitored_threads[cam_id]

            await asyncio.sleep(10)

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Stopping AI Service...")
        for thread in monitored_threads.values():
            thread.stop()


if __name__ == "__main__":
    asyncio.run(main())
