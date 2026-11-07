"""AI Model Inference Black-Box Interface.

================================================================================
QUY ƯỚC QUAN TRỌNG DÀNH CHO TEAM AI (BÊN 1):
- Hệ thống Edge coi khối suy luận AI này là một "HỘP ĐEN" (Black Box).
- Bạn có thể sử dụng bất kỳ kiến trúc mô hình nào (YOLOv8, YOLOv11, YOLO26n,
  ViT, CNN, VLM, ONNX Runtime, TensorRT, PyTorch, v.v.).
- Bạn chỉ cần thực thi hàm `predict(frame_bgr)` nhận vào khung hình OpenCV BGR
  và trả về danh sách đối tượng `DetectionResult`.
================================================================================
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import numpy as np

logger = logging.getLogger("ai.model")


@dataclass
class DetectionResult:
    """Kết quả phát hiện từ mô hình AI.

    Attributes
    ----------
    class_name : str
        Nhãn đối tượng: 'fire' (lửa) hoặc 'smoke' (khói).
    confidence : float
        Độ tin cậy từ 0.0 đến 1.0 (ví dụ 0.88).
    bbox : list[float]
        Tọa độ Bounding Box chuẩn hóa [x_min, y_min, x_max, y_max] trong khoảng [0.0, 1.0].
        Ví dụ: [0.15, 0.20, 0.45, 0.60] biểu thị ô chữ nhật có:
          - x_min: 15% chiều rộng ảnh từ mép trái
          - y_min: 20% chiều cao ảnh từ mép trên
          - x_max: 45% chiều rộng ảnh từ mép trái
          - y_max: 60% chiều cao ảnh từ mép trên
    """

    class_name: str
    confidence: float
    bbox: list[float]


class FireDetectionModel(Protocol):
    """Giao diện chuẩn của mô hình phát hiện cháy."""

    def load(self, weights_path: str) -> None:
        """Nạp trọng số mô hình."""
        ...

    def predict(self, frame_bgr: np.ndarray) -> list[DetectionResult]:
        """Thực hiện suy luận trên 1 khung hình BGR (từ OpenCV hoặc PyAV).

        Parameters
        ----------
        frame_bgr : np.ndarray
            Mảng NumPy 3 chiều (Height, Width, 3), hệ màu BGR.

        Returns
        -------
        list[DetectionResult]
            Danh sách các phát hiện cháy / khói (nếu có).
        """
        ...


class MockFireModel:
    """Mô hình giả lập (Stub) dùng để kiểm thử toàn bộ đường ống trước khi ráp Model thật.

    Team AI sẽ thay thế class này bằng class nạp trọng số thật của các bạn
    (ví dụ: class YOLOv8FireModel, class TensorRTFireModel).
    """

    def __init__(self, weights_path: str | None = None) -> None:
        self.weights_path = weights_path
        logger.info("Initializing FireDetectionModel (Weights: %s)...", weights_path or "None (Mock)")

    def load(self, weights_path: str) -> None:
        self.weights_path = weights_path
        logger.info("Loaded AI model weights from %s", weights_path)

    def predict(self, frame_bgr: np.ndarray) -> list[DetectionResult]:
        """Placeholder inference.

        Trong môi trường production, Team AI đặt code suy luận vào đây:
            results = self.model(frame_bgr, conf=0.5)
            ...
        """
        return []
