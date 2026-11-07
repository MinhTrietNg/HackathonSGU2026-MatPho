"""Tier 2 — YOLO26n wrapper (PyTorch ``.pt`` or exported ONNX, CPU only).

The detector reads its weights from config: the fine-tuned ``best.pt`` when
present, otherwise the stock weights (downloaded on first use). When the
loaded model has none of the configured class names (stock COCO weights),
all classes are kept so Phase 1 still shows boxes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import Config, DetectorConfig

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Detection:
    """One bounding box in pixel coordinates."""

    cls_name: str
    cls_id: int
    conf: float
    xyxy: tuple[float, float, float, float]

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.xyxy
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.xyxy
        return (x1 + x2) / 2, (y1 + y2) / 2

    def to_dict(self) -> dict:
        return {"cls": self.cls_name, "conf": round(self.conf, 4),
                "xyxy": [round(v, 1) for v in self.xyxy]}


@dataclass(slots=True)
class DetectResult:
    detections: list[Detection]
    infer_ms: float

    def by_class(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.detections:
            counts[d.cls_name] = counts.get(d.cls_name, 0) + 1
        return counts


def resolve_weights(cfg: DetectorConfig, root: Config) -> Path:
    """Pick ``weights`` if it exists, else ``fallback_weights`` (auto-download)."""
    primary = root.resolve(cfg.weights)
    if primary.is_file():
        log.info("dùng weights fine-tune: %s", primary)
        return primary
    fallback = root.resolve(cfg.fallback_weights)
    log.warning("không thấy %s, dùng weights gốc %s (tự tải nếu chưa có)",
                primary, fallback)
    fallback.parent.mkdir(parents=True, exist_ok=True)
    return fallback


def onnx_is_stale(weights: Path, onnx_path: Path) -> bool:
    """Tell whether an exported ONNX file predates its ``.pt`` weights.

    Parameters
    ----------
    weights : Path
        Source ``.pt`` checkpoint.
    onnx_path : Path
        ONNX file previously exported from ``weights``.

    Returns
    -------
    bool
        ``True`` when both files exist and the ONNX file is older, i.e. the
        checkpoint was replaced (e.g. after fine-tuning) and the ONNX graph
        would still hold the old model.
    """
    if not (weights.is_file() and onnx_path.is_file()):
        return False
    return onnx_path.stat().st_mtime < weights.stat().st_mtime


class Detector:
    """Thin wrapper around ``ultralytics.YOLO`` with config-driven settings."""

    def __init__(self, cfg: DetectorConfig, root: Config):
        from ultralytics import YOLO  # import chậm, chỉ khi cần

        self.cfg = cfg
        weights = resolve_weights(cfg, root)
        if cfg.backend == "onnx":
            weights = self._ensure_onnx(weights, YOLO)
        self.weights = weights
        self.model = YOLO(str(weights), task="detect")
        # Chuẩn hoá tên class: thường hoá + alias, để checkpoint ngoài (HF) dùng
        # "Fire"/"Smoke" hay thứ tự id khác vẫn khớp fire/smoke của pipeline.
        self.names: dict[int, str] = {
            int(k): cfg.class_aliases.get(
                v, cfg.class_aliases.get(v.lower(), v.lower()))
            for k, v in self.model.names.items()}
        self.keep_ids: list[int] | None = self._class_filter(cfg.classes)
        if cfg.warmup:
            dummy = np.zeros((cfg.imgsz, cfg.imgsz, 3), dtype=np.uint8)
            self.detect(dummy)
            log.info("warm-up xong (%s, imgsz %d, %s)", weights.name, cfg.imgsz,
                     cfg.device)

    def _ensure_onnx(self, weights: Path, yolo_cls) -> Path:
        """Export ``weights`` to ONNX once (next to it) and return that path."""
        if weights.suffix == ".onnx":
            return weights
        # Export tĩnh theo imgsz -> mỗi imgsz một file, không dùng nhầm kích thước.
        onnx_path = weights.with_name(f"{weights.stem}_{self.cfg.imgsz}.onnx")
        stale = onnx_is_stale(weights, onnx_path)
        if stale:
            log.info("%s cũ hơn %s -> export lại", onnx_path.name, weights.name)
        if stale or not onnx_path.is_file():
            log.info("export ONNX %s -> %s", weights.name, onnx_path.name)
            # simplify=False: tránh ultralytics tự pip-install onnxslim lúc chạy.
            exported = yolo_cls(str(weights)).export(
                format="onnx", imgsz=self.cfg.imgsz, dynamic=False, simplify=False)
            Path(exported).replace(onnx_path)   # ultralytics đặt tên theo file .pt
        return onnx_path

    def _class_filter(self, wanted: list[str]) -> list[int] | None:
        inv = {name: i for i, name in self.names.items()}
        ids = [inv[n] for n in wanted if n in inv]
        if not ids:
            log.warning("weights không có class %s (có: %d class, ví dụ %s); "
                        "giữ MỌI class — chỉ để kiểm tra khung xương",
                        wanted, len(self.names), list(self.names.values())[:5])
            return None
        missing = [n for n in wanted if n not in inv]
        if missing:
            log.warning("weights thiếu class %s, chỉ lọc %s", missing,
                        [self.names[i] for i in ids])
        return ids

    def detect(self, image: np.ndarray) -> DetectResult:
        """Run one inference on a BGR image and return filtered boxes."""
        t0 = time.perf_counter()
        by_class = self.cfg.conf_by_class
        conf_floor = min([self.cfg.conf_threshold, *by_class.values()])
        res = self.model.predict(
            image, imgsz=self.cfg.imgsz, conf=conf_floor,
            iou=self.cfg.iou_nms, max_det=self.cfg.max_det, device=self.cfg.device,
            classes=self.keep_ids, verbose=False,
        )[0]
        infer_ms = (time.perf_counter() - t0) * 1000
        dets: list[Detection] = []
        if res.boxes is not None and len(res.boxes):
            xyxy = res.boxes.xyxy.cpu().numpy()
            conf = res.boxes.conf.cpu().numpy()
            cls = res.boxes.cls.cpu().numpy().astype(int)
            for b, c, k in zip(xyxy, conf, cls):
                name = self.names.get(int(k), str(k))
                if float(c) < by_class.get(name, self.cfg.conf_threshold):
                    continue
                dets.append(Detection(name, int(k), float(c),
                                      tuple(float(v) for v in b)))
        return DetectResult(dets, infer_ms)
