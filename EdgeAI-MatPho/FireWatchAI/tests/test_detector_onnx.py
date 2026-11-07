"""ONNX export cache must follow the .pt weights it came from."""

import os
from pathlib import Path

from firewatch.config import DetectorConfig
from firewatch.detector import Detector, onnx_is_stale


class _FakeYolo:
    """Stand-in for ``ultralytics.YOLO``: export writes ``<stem>.onnx``."""

    calls: list[Path] = []

    def __init__(self, weights: str):
        self.weights = Path(weights)

    def export(self, **kwargs) -> str:
        out = self.weights.with_suffix(".onnx")
        out.write_bytes(b"new")
        _FakeYolo.calls.append(self.weights)
        return str(out)


def _touch(path: Path, mtime: float, data: bytes = b"x") -> None:
    path.write_bytes(data)
    os.utime(path, (mtime, mtime))


def _detector(imgsz: int = 640) -> Detector:
    det = Detector.__new__(Detector)
    det.cfg = DetectorConfig(imgsz=imgsz)
    return det


def test_onnx_is_stale(tmp_path: Path):
    pt, onnx = tmp_path / "model.pt", tmp_path / "model_640.onnx"
    assert not onnx_is_stale(pt, onnx)
    _touch(pt, 1_000)
    assert not onnx_is_stale(pt, onnx)
    _touch(onnx, 2_000)
    assert not onnx_is_stale(pt, onnx)
    _touch(pt, 3_000)
    assert onnx_is_stale(pt, onnx)


def test_replaced_weights_trigger_reexport(tmp_path: Path):
    _FakeYolo.calls = []
    pt, onnx = tmp_path / "model.pt", tmp_path / "model_640.onnx"
    _touch(pt, 1_000)
    _touch(onnx, 2_000, b"old")
    det = _detector()
    assert det._ensure_onnx(pt, _FakeYolo) == onnx
    assert _FakeYolo.calls == [] and onnx.read_bytes() == b"old"

    _touch(pt, 3_000)   # checkpoint mới sau fine-tune
    assert det._ensure_onnx(pt, _FakeYolo) == onnx
    assert _FakeYolo.calls == [pt] and onnx.read_bytes() == b"new"
