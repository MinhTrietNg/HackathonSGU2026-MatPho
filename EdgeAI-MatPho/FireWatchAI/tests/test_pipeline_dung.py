"""``Pipeline.dung()`` và detector dùng chung (nền của chế độ nút biên).

Nguồn live giả hành xử như ``CameraSource``: ``open()`` xoá cờ dừng, vòng đọc
chỉ thoát khi ``close()``. Detector giả thay model thật; ``Detector`` của
pipeline bị chặn để chắc chắn detector được tiêm là thứ được dùng.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pytest

import firewatch.pipeline as pl
from firewatch.config import Config
from firewatch.detector import DetectResult
from firewatch.sources import Frame


class NguonLiveGia:
    """Nguồn live giả: phát khung 100 Hz cho tới khi bị đóng; ``co_khung=False``
    thì không phát khung nào (camera đang kết nối lại), chỉ ``close()`` thoát."""

    is_live = True
    name = "rtsp"

    def __init__(self, khi_mo=None, co_khung: bool = True) -> None:
        self._dong = threading.Event()
        self._co_khung = co_khung
        self._khi_mo = khi_mo
        self.idx = 0

    def __enter__(self) -> "NguonLiveGia":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def open(self) -> None:
        if self._khi_mo is not None:
            self._khi_mo()
        self._dong.clear()            # như CameraSource.open

    def close(self) -> None:
        self._dong.set()

    def __iter__(self):
        while not self._dong.wait(0.01):
            if not self._co_khung:
                continue
            yield Frame(image=np.zeros((48, 64, 3), np.uint8),
                        video_ts=self.idx * 0.25, wall_time=time.time(),
                        index=self.idx)
            self.idx += 1


class DetectorGia:
    keep_ids = [0, 1]
    weights = Path("gia.pt")

    def __init__(self) -> None:
        self.so_lan = 0

    def detect(self, image: np.ndarray) -> DetectResult:
        self.so_lan += 1
        return DetectResult([], 1.0)


def _cau_hinh(tmp: Path) -> Config:
    return Config(output={"dir": tmp / "runs", "save_frames": False},
                  alerts={"events_dir": tmp / "events"},
                  vlm={"enabled": False}, heartbeat={"interval_s": 0.25})


@pytest.fixture
def chan_detector_that(monkeypatch):
    def _cam(*a, **k):
        raise AssertionError("không được dựng Detector khi đã tiêm detector")
    monkeypatch.setattr(pl, "Detector", _cam)


def _chay_nen(p: pl.Pipeline) -> tuple[threading.Thread, list]:
    kq: list = []
    t = threading.Thread(target=lambda: kq.append(p.run()), daemon=True)
    t.start()
    return t, kq


def test_dung_nguon_live_dang_chay(tmp_path, monkeypatch, chan_detector_that):
    nguon, det = NguonLiveGia(), DetectorGia()
    monkeypatch.setattr(pl, "open_source", lambda *a, **k: nguon)
    p = pl.Pipeline(_cau_hinh(tmp_path), "rtsp://gia/live/cam_01", detector=det)
    t, kq = _chay_nen(p)
    han = time.monotonic() + 5
    while det.so_lan < 3 and time.monotonic() < han:
        time.sleep(0.01)
    assert det.so_lan >= 3
    p.dung()
    t.join(5)
    assert not t.is_alive() and p.da_yeu_cau_dung
    assert kq[0].live_source_lost is False
    assert kq[0].heartbeats == det.so_lan


def test_dung_truoc_khi_chay(tmp_path, monkeypatch, chan_detector_that):
    monkeypatch.setattr(pl, "open_source", lambda *a, **k: NguonLiveGia())
    p = pl.Pipeline(_cau_hinh(tmp_path), "rtsp://gia", detector=DetectorGia())
    p.dung()
    t, kq = _chay_nen(p)
    t.join(5)
    assert not t.is_alive()
    assert kq[0].frames_read == 0 and kq[0].live_source_lost is False


def test_dung_trong_luc_dang_mo_nguon(tmp_path, monkeypatch, chan_detector_that):
    """``dung()`` rơi vào lúc ``open()`` đang kết nối: ``open()`` xoá cờ của
    nguồn, pipeline vẫn phải thoát."""
    hop: dict = {}
    nguon = NguonLiveGia(khi_mo=lambda: hop["p"].dung(), co_khung=False)
    monkeypatch.setattr(pl, "open_source", lambda *a, **k: nguon)
    p = pl.Pipeline(_cau_hinh(tmp_path), "rtsp://gia", detector=DetectorGia())
    hop["p"] = p
    t, kq = _chay_nen(p)
    t.join(5)
    assert not t.is_alive()
    assert kq[0].live_source_lost is False


def test_dung_khi_nguon_khong_co_khung(tmp_path, monkeypatch,
                                      chan_detector_that):
    nguon = NguonLiveGia(co_khung=False)
    monkeypatch.setattr(pl, "open_source", lambda *a, **k: nguon)
    p = pl.Pipeline(_cau_hinh(tmp_path), "rtsp://gia", detector=DetectorGia())
    t, kq = _chay_nen(p)
    time.sleep(0.05)
    p.dung()
    t.join(5)
    assert not t.is_alive()
    assert kq[0].heartbeats == 0 and kq[0].live_source_lost is False


def test_dinh_dang_log_doi_duoc(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "DINH_DANG_LOG", "[%(threadName)s] %(message)s")
    fh = pl._attach_file_log(tmp_path / "run.log")
    try:
        assert fh.formatter._fmt == "[%(threadName)s] %(message)s"
    finally:
        import logging
        logging.getLogger().removeHandler(fh)
        fh.close()
