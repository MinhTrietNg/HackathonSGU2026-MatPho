"""Đồ giả cho test verifier bền vững: đồng hồ do test đẩy, VLM điều khiển được,
và hàm dựng một hệ (store, pipeline, bộ điều phối) với cờ bật.

Không phải file test (pytest không thu thập). Fixture ``he`` trong
``conftest.py`` bọc :func:`dung_he` và :func:`don_he`. Worker của bộ điều phối
vẫn là luồng thật, nên test chờ bằng :func:`cho` (tối đa 2 s giờ thật) cho tới
khi worker xử lý xong một bước.
"""

from __future__ import annotations

import heapq
import itertools
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from firewatch.alerts import Event, EventStore, VLMResult
from firewatch.pipeline import Pipeline, RunSummary
from firewatch.vlm import VerificationService, VerifyRequest, VLMVerifier
from firewatch.xac_minh_nen import VeHen

import kich_ban_verifier as kb

DEN = np.zeros((120, 160, 3), dtype=np.uint8)
TRANG = np.full((120, 160, 3), 255, dtype=np.uint8)
HOP = (10.0, 20.0, 60.0, 80.0)


class DongHoGia:
    """Đồng hồ do test đẩy; việc tới hạn chạy ngay trên luồng của test."""

    def __init__(self) -> None:
        self.t = 0.0
        self._heap: list[tuple[float, int, VeHen, Callable[[], None]]] = []
        self._dem = itertools.count()
        self._khoa = threading.Lock()

    def bay_gio(self) -> float:
        return self.t

    def hen(self, luc: float, viec: Callable[[], None]) -> VeHen:
        ve = VeHen()
        with self._khoa:
            heapq.heappush(self._heap, (luc, next(self._dem), ve, viec))
        return ve

    def dong(self) -> None:
        with self._khoa:
            self._heap.clear()

    def tien_toi(self, t: float) -> None:
        """Đẩy đồng hồ tới ``t``, chạy lần lượt mọi việc tới hạn."""
        while True:
            with self._khoa:
                if not self._heap or self._heap[0][0] > t:
                    break
                luc, _, ve, viec = heapq.heappop(self._heap)
            self.t = max(self.t, luc)
            if not ve.da_huy:
                viec()
        self.t = t


@dataclass
class LuotGoi:
    """Một lượt gọi VLM giả: test quyết khi nào và trả lời gì."""

    timeout_s: float | None
    frame_jpeg: bytes
    tra_loi: threading.Event = field(default_factory=threading.Event)
    ket_qua: VLMResult | None = None
    loi: BaseException | None = None
    da_xong: threading.Event = field(default_factory=threading.Event)

    def tra(self, ket_qua: VLMResult) -> None:
        self.ket_qua = ket_qua
        self.tra_loi.set()

    def nem(self, loi: BaseException) -> None:
        """Lượt này kết thúc bằng lỗi ``loi`` (HTTP 5xx, 429, mạng...)."""
        self.loi = loi
        self.tra_loi.set()


class VlmDieuKhien(VLMVerifier):
    """VLM giả chặn ở mỗi lượt gọi cho tới khi test gọi ``tra`` hoặc ``nem``."""

    name = "dieu_khien"

    def __init__(self) -> None:
        self.luot: list[LuotGoi] = []
        self._khoa = threading.Lock()

    def verify(self, frame_jpeg, crop_jpeg, context, severity, first_jpeg=None,
               timeout_s=None):
        g = LuotGoi(timeout_s, frame_jpeg)
        with self._khoa:
            self.luot.append(g)
        try:
            if not g.tra_loi.wait(5.0):
                raise TimeoutError("test không trả lời")
            if g.loi is not None:
                raise g.loi
            return g.ket_qua
        finally:
            g.da_xong.set()

    def giai_phong(self) -> None:
        for g in list(self.luot):
            if not g.tra_loi.is_set():
                g.tra(kb.CHAY)


def cho(dieu_kien: Callable[[], bool], giay: float = 2.0) -> None:
    """Chờ giờ thật tới khi ``dieu_kien`` đúng (worker là luồng thật)."""
    het = time.monotonic() + giay
    while not dieu_kien():
        assert time.monotonic() < het, "quá hạn chờ worker"
        time.sleep(0.005)


def dung_he(tmp: Path, *, max_workers: int = 1, hang: int = 8, grace_s: float = 2.0,
            ngan_sach_s: float = 10.0, vlm: VLMVerifier | str | None = None,
            cau_dao: dict[str, Any] | None = None) -> SimpleNamespace:
    """Dựng pipeline cờ bật với đồng hồ giả.

    Parameters
    ----------
    tmp : Path
        Thư mục riêng của hệ (events ghi vào đây).
    vlm : VLMVerifier or "tat", optional
        Mặc định :class:`VlmDieuKhien`; ``"tat"`` là service không có verifier
        (VLM tắt hoặc thiếu key).
    cau_dao : dict, optional
        Ghi đè khối ``verifier.cau_dao`` (mặc định 3 lỗi, mở 60 s).

    Returns
    -------
    SimpleNamespace
        ``cfg, store, phat, vlm, svc, p, s, dh, dp, gui``; ``phat`` là danh
        sách ``(kind, event)`` theo thứ tự phát, ``gui(ts, anh, track)`` giao
        một cảnh báo và trả ``event_id``.
    """
    verifier_cfg: dict[str, Any] = {"ben_vung": True, "ngan_sach_s": ngan_sach_s,
                                    "hang_cho_toi_da": hang}
    if cau_dao:
        verifier_cfg["cau_dao"] = cau_dao
    cfg = kb.cau_hinh(tmp, verifier=verifier_cfg,
                      vlm={"grace_s": grace_s, "provider": "mock",
                           "max_workers": max_workers})
    store = EventStore(cfg.alerts, cfg.camera, cfg)
    phat: list[tuple[str, Event]] = []
    khoa = threading.Lock()

    def ghi(e: Event, k: str) -> None:
        with khoa:
            phat.append((k, e))

    store.subscribe(ghi)
    vlm_ = VlmDieuKhien() if vlm is None else vlm
    svc = VerificationService(cfg.vlm, None if vlm == "tat" else vlm_)
    p = Pipeline(cfg, "kich_ban")
    s = RunSummary(source="kich_ban", weights="w", out_dir="out")
    dh = DongHoGia()
    dp = p._tao_dieu_phoi(store, s, svc, dong_ho=dh)

    def gui(ts: float, anh: np.ndarray = DEN, track: int = 0) -> str:
        return kb.gui_nen(p, VerifyRequest(anh, HOP, "HAM", "CRITICAL", ts),
                          ts=ts, track=track)

    return SimpleNamespace(cfg=cfg, store=store, phat=phat, vlm=vlm_, svc=svc, p=p,
                           s=s, dh=dh, dp=dp, gui=gui)


def don_he(h: SimpleNamespace) -> None:
    """Thả mọi lượt VLM còn chặn, dừng bộ điều phối và service."""
    if isinstance(h.vlm, VlmDieuKhien):
        h.vlm.giai_phong()
    h.dp.dong()
    h.svc.shutdown()


def cua(h: SimpleNamespace, event_id: str) -> list[tuple[str, Event]]:
    """Thông báo đã phát của một ``event_id``, theo thứ tự."""
    return [(k, e) for k, e in h.phat if e.event_id == event_id]
