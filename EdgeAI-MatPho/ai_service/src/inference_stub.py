"""
AI Model Plug-in Slot (Empty Skeleton for AI Team)
==============================================================================
Architecture Contract:
- INPUT : `frame` (np.ndarray, BGR format decoded from RTSP `rtsp://mediamtx:8554/live/{cam_id}`)
- MODEL : Currently empty stub. AI Team loads custom model in `__init__` and runs inference in `predict`.
- OUTPUT: Returns a list of `DetectionResult` -> Automatically forwarded by `main.py` to Cloud Webhook!
==============================================================================
"""

import os
import logging
from dataclasses import dataclass
from typing import List
import numpy as np

logger = logging.getLogger("firewatch-ai.inference")


@dataclass
class DetectionResult:
    """Standardized output of one fire/smoke detection box."""

    class_name: str  # "fire" or "smoke"
    confidence: float  # [0.0, 1.0]
    bbox: List[float]  # [x1, y1, x2, y2]


class MockFireModel:
    """
    Empty AI Model Skeleton (1 Input Frame -> 1 Output DetectionResult List).
    AI Team Instructions:
      1. Place your model weights (e.g., `best.pt`) inside `EdgeAI-MatPho/ai_service/weights/`.
      2. Load your model in `__init__` below.
      3. Implement `predict(frame, conf_threshold)` to return `List[DetectionResult]`.
    """

    def __init__(self, weights_path: str = "/app/weights/best.pt") -> None:
        self.weights_path = weights_path
        self.model = None
        self.is_ready = False

        if os.path.exists(self.weights_path):
            logger.info("Found weights file at %s (Ready for AI team to load model).", self.weights_path)
            # ==================================================================
            # [CHỖ GẮN MODEL CỦA TEAM AI - BƯỚC 1: LOAD WEIGHTS]
            # from ultralytics import YOLO
            # self.model = YOLO(self.weights_path)
            # self.is_ready = True
            # ==================================================================
        else:
            logger.info(
                "AI Skeleton running in EMPTY STUB mode (no weights at %s).",
                self.weights_path,
            )

    def predict(
        self, frame: np.ndarray, conf_threshold: float = 0.60
    ) -> List[DetectionResult]:
        """
        Run inference on a single BGR frame (Input) and return detections (Output).
        """
        if frame is None or frame.size == 0:
            return []

        # ======================================================================
        # [CHỖ GẮN MODEL CỦA TEAM AI - BƯỚC 2: SUY LUẬN (INFERENCE)]
        # if self.is_ready and self.model is not None:
        #     results = self.model.predict(frame, conf=conf_threshold, verbose=False)
        #     detections: List[DetectionResult] = []
        #     for r in results:
        #         for box in r.boxes:
        #             detections.append(
        #                 DetectionResult(
        #                     class_name=r.names[int(box.cls[0])],
        #                     confidence=float(box.conf[0]),
        #                     bbox=[float(v) for v in box.xyxy[0].tolist()],
        #                 )
        #             )
        #     return detections
        # ======================================================================

        return []


FireDetectionModelStub = MockFireModel
