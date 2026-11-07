"""
FireWatch AI Service - Minimal 1-Input RTSP -> 1-Output Webhook Skeleton
==============================================================================
1. INPUT  : Connects to `rtsp://mediamtx:8554/live/{cam_id}` over TCP & reads frames.
2. MODEL  : Calls `MockFireModel.predict(frame)` in `src/inference_stub.py`.
3. OUTPUT : When a detection is returned, encodes JPEG Base64 & dispatches HTTP Webhook
            to Cloud Backend (`POST /api/v1/internal/ai/fire-events`).
==============================================================================
"""

import os
import cv2
import time
import asyncio
import logging
import threading
from typing import List, Dict, Optional
import httpx

from .config import AISettings, CameraStreamTarget
from .inference_stub import DetectionResult, MockFireModel
from .masking import apply_watch_area_mask
from .webhook_client import CloudWebhookClient

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("firewatch-ai")


class CameraAIWorker:
    """
    Single-camera pipeline:
    [Input RTSP: live/{cam_id}] -> [Optional Watch Area Mask] -> [AI Model Slot] -> [Output Webhook]
    """

    def __init__(
        self,
        target: CameraStreamTarget,
        settings: AISettings,
        model: MockFireModel,
        webhook: CloudWebhookClient,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.target = target
        self.settings = settings
        self.model = model
        self.webhook = webhook
        self.loop = loop
        self.rtsp_url = settings.rtsp_url_for(target.cam_id)
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"ai-worker-{target.cam_id}",
            daemon=True,
        )
        self._last_alert_at: float = 0.0

    def update_watch_area(self, watch_area) -> None:
        self.target.watch_area = watch_area

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def _run_loop(self) -> None:
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        min_interval = 1.0 / max(0.5, self.settings.ai_sampling_fps)

        while not self._stop.is_set():
            logger.info(
                "[cam_id=%s] Opening RTSP Input: %s", self.target.cam_id, self.rtsp_url
            )
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap.release()
                self._stop.wait(3.0)
                continue

            logger.info("[cam_id=%s] RTSP Input connected.", self.target.cam_id)
            last_infer_ts = 0.0

            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    logger.warning(
                        "[cam_id=%s] RTSP stream ended or disconnected. Reconnecting...",
                        self.target.cam_id,
                    )
                    break

                now = time.monotonic()
                if now - last_infer_ts < min_interval:
                    continue
                last_infer_ts = now

                # 1. Full-Frame AI Model Inference Slot (No pre-masking; bbox returned on fire detection)
                detections: List[DetectionResult] = self.model.predict(
                    frame, conf_threshold=self.settings.ai_confidence_threshold
                )

                if not detections:
                    continue

                # 3. Output Webhook Dispatch (with cooldown)
                if now - self._last_alert_at >= self.settings.alert_cooldown_seconds:
                    best = max(detections, key=lambda d: d.confidence)
                    self._last_alert_at = now
                    asyncio.run_coroutine_threadsafe(
                        self.webhook.report_fire_event(
                            cam_id=self.target.cam_id,
                            class_name=best.class_name,
                            confidence=best.confidence,
                            bbox=best.bbox,
                            frame_bgr=frame,
                        ),
                        self.loop,
                    )

            cap.release()
            if not self._stop.is_set():
                self._stop.wait(2.0)


async def main_async() -> None:
    settings = AISettings.from_env()
    model = MockFireModel(weights_path=settings.model_weights_path)
    webhook = CloudWebhookClient(settings=settings)
    loop = asyncio.get_running_loop()

    workers_map: Dict[str, CameraAIWorker] = {}
    for t in settings.camera_streams:
        w = CameraAIWorker(t, settings, model, webhook, loop)
        w.start()
        workers_map[t.cam_id] = w

    logger.info(
        "FireWatch AI Skeleton started with %d RTSP input stream(s) on template '%s'",
        len(workers_map),
        settings.stream_path_template,
    )

    try:
        while True:
            await asyncio.sleep(2.0)
            # Dynamic synchronization of cameras & AI schedule (should_ai_scan_now) from edge-backend SQLite
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    res = await client.get(f"{settings.edge_backend_url}/api/v1/edge/cameras")
                    if res.status_code == 200:
                        cams = res.json().get("cameras", [])
                        for c in cams:
                            cid = c.get("cam_id")
                            if not cid:
                                continue
                            should_scan = bool(c.get("is_active", True)) and bool(
                                c.get("should_ai_scan_now", True)
                            )
                            w_area = c.get("watch_area")

                            if should_scan:
                                if cid in workers_map:
                                    workers_map[cid].update_watch_area(w_area)
                                else:
                                    new_t = CameraStreamTarget(cam_id=cid, watch_area=w_area)
                                    new_w = CameraAIWorker(new_t, settings, model, webhook, loop)
                                    new_w.start()
                                    workers_map[cid] = new_w
                                    logger.info(
                                        "[cam_id=%s] Connected RTSP stream to AI worker (ai_mode=%s).",
                                        cid,
                                        c.get("ai_mode", "ALWAYS"),
                                    )
                            else:
                                # Disconnect RTSP stream from AI immediately when OFF or inside SCHEDULE rest window
                                if cid in workers_map:
                                    old_worker = workers_map.pop(cid)
                                    await asyncio.to_thread(old_worker.stop)
                                    logger.info(
                                        "[cam_id=%s] Disconnected RTSP stream from AI worker (ai_mode=%s, should_ai_scan_now=False).",
                                        cid,
                                        c.get("ai_mode", "OFF"),
                                    )
            except Exception as exc:
                logger.debug("Edge DB camera sync skipped: %s", exc)
    except asyncio.CancelledError:
        pass
    finally:
        for w in workers_map.values():
            w.stop()


if __name__ == "__main__":
    asyncio.run(main_async())
