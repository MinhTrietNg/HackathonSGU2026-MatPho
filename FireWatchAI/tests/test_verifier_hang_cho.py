"""Verifier bền vững: hàng chờ, ngân sách nền, hẹn giờ độc lập heartbeat.

Kịch bản 3, 4, 7, 8 của ADR 2026-11-07 và kịch bản 12 (nguồn treo). Đồng hồ giả
do test đẩy; VLM giả chặn cho tới khi test trả lời, nên không test nào ngủ thật
để chờ mốc thời gian. Worker vẫn là luồng thật: test chỉ chờ (tối đa 2 s giờ
thật) cho tới khi worker xử lý xong một bước.
"""

from __future__ import annotations

import heapq
import itertools
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from firewatch.alerts import Event, EventStore, VLMResult
from firewatch.pipeline import Pipeline, RunSummary
from firewatch.vlm import VerificationService, VerifyRequest, VLMVerifier
from firewatch.xac_minh_nen import DongHoThat, VeHen

import kich_ban_verifier as kb

DEN = np.zeros((120, 160, 3), dtype=np.uint8)
TRANG = np.full((120, 160, 3), 255, dtype=np.uint8)
HOP = (10.0, 20.0, 60.0, 80.0)


# ------------------------------------------------------------- đồ giả
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
    da_xong: threading.Event = field(default_factory=threading.Event)

    def tra(self, ket_qua: VLMResult) -> None:
        self.ket_qua = ket_qua
        self.tra_loi.set()


class VlmDieuKhien(VLMVerifier):
    """VLM giả chặn ở mỗi lượt gọi cho tới khi test gọi ``LuotGoi.tra``."""

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


@pytest.fixture()
def he(tmp_path: Path):
    """Dựng pipeline cờ bật với đồng hồ giả; trả hàm ``dung(**cau_hinh)``."""
    da_dung: list[SimpleNamespace] = []

    def dung(*, max_workers: int = 1, hang: int = 8, grace_s: float = 2.0,
             ngan_sach_s: float = 10.0, vlm: VLMVerifier | str | None = None
             ) -> SimpleNamespace:
        """``vlm="tat"``: service không có verifier (VLM tắt hoặc thiếu key)."""
        cfg = kb.cau_hinh(tmp_path / f"he{len(da_dung)}",
                          verifier={"ben_vung": True, "ngan_sach_s": ngan_sach_s,
                                    "hang_cho_toi_da": hang},
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

        h = SimpleNamespace(cfg=cfg, store=store, phat=phat, vlm=vlm_, svc=svc, p=p,
                            s=s, dh=dh, dp=dp, gui=gui)
        da_dung.append(h)
        return h

    yield dung
    for h in da_dung:
        if isinstance(h.vlm, VlmDieuKhien):
            h.vlm.giai_phong()
        h.dp.dong()
        h.svc.shutdown()


def _cua(h: SimpleNamespace, event_id: str) -> list[tuple[str, Event]]:
    return [(k, e) for k, e in h.phat if e.event_id == event_id]


# ------------------------------------------------------------- kịch bản
def test_kich_ban_3_vlm_tra_loi_o_5s_thi_pending_roi_updated_verified(he):
    h = he()
    eid = h.gui(ts=12.0)
    cho(lambda: len(h.vlm.luot) == 1)
    assert h.vlm.luot[0].timeout_s == pytest.approx(9.5)   # gọi ngay: 10 - 0,5
    h.dh.tien_toi(2.0)
    assert [k for k, _ in h.phat] == ["created"]
    dau = h.phat[0][1]
    assert dau.event_id == eid
    assert (dau.verifier.status, dau.verifier.reason, dau.verification) == (
        "PENDING", "cho_vlm", "UNVERIFIED")
    assert dau.severity == "CRITICAL" and dau.video_ts_sec == 12.0
    h.dh.tien_toi(5.0)
    h.vlm.luot[0].tra(kb.CHAY)
    cho(lambda: len(h.phat) == 2)
    kind, cuoi = h.phat[1]
    assert kind == "updated" and cuoi.event_id == eid
    assert (cuoi.verifier.status, cuoi.verification) == ("VERIFIED", "VERIFIED")
    assert cuoi.verifier.latency_ms == 5000 and cuoi.verifier.needs_human_check is False
    assert cuoi.severity == "CRITICAL"
    assert h.s.alerts[0]["updated"] is True
    assert h.s.alerts[0]["verifier_status"] == "VERIFIED"
    h.dh.tien_toi(30.0)                   # mốc ngân sách đã huỷ: không phát thêm
    assert len(h.phat) == 2


def test_kich_ban_4_vlm_tra_loi_o_12s_thi_timeout_luc_10s_va_bo_ket_qua_muon(
        he, caplog):
    h = he()
    eid = h.gui(ts=3.0)
    cho(lambda: len(h.vlm.luot) == 1)
    h.dh.tien_toi(9.99)
    assert [k for k, _ in h.phat] == ["created"]
    h.dh.tien_toi(10.0)
    assert [k for k, _ in h.phat] == ["created", "updated"]
    het = h.phat[1][1]
    assert (het.verifier.status, het.verifier.reason) == ("VLM_TIMEOUT", "timeout")
    assert het.verifier.needs_human_check is True
    assert het.verification == "UNVERIFIED" and het.severity == "CRITICAL"
    with caplog.at_level(logging.INFO, logger="firewatch"):
        h.dh.tien_toi(12.0)
        h.vlm.luot[0].tra(kb.CHAY)
        cho(lambda: "đến sau ngân sách" in caplog.text)
    assert len(h.phat) == 2, "kết quả đến muộn không được phát"
    assert h.store.get(eid).verifier.status == "VLM_TIMEOUT"


def test_kich_ban_7_hang_day_bo_muc_cu_nhat_va_timeout_theo_ngan_sach_con_lai(he):
    h = he(max_workers=1, hang=2)
    a = h.gui(ts=1.0, track=1)
    cho(lambda: len(h.vlm.luot) == 1)      # worker duy nhất đang bận với A
    b = h.gui(ts=2.0, track=2)
    c = h.gui(ts=3.0, track=3)
    assert h.dp.so_trong_hang == 2 and h.phat == []
    d = h.gui(ts=4.0, track=4)             # hàng đầy: B (cũ nhất) bị bỏ
    assert h.dp.so_trong_hang == 2
    assert [(k, e.event_id) for k, e in h.phat] == [("created", b)]
    bo = h.phat[0][1]
    assert (bo.verifier.status, bo.verifier.reason) == ("VLM_TIMEOUT",
                                                        "qua_han_hang_cho")
    assert bo.verifier.needs_human_check is True and bo.severity == "CRITICAL"
    # A trả lời ở 6 s; worker lấy C với timeout = ngân sách còn lại - 0,5 = 3,5 s
    h.dh.tien_toi(6.0)
    h.vlm.luot[0].tra(kb.CHAY)
    cho(lambda: len(h.vlm.luot) == 2)
    assert h.vlm.luot[1].timeout_s == pytest.approx(3.5)
    # C trả lời ở 9 s; còn 0,5 s < 1 s nên D không được gọi
    h.dh.tien_toi(9.0)
    h.vlm.luot[1].tra(kb.CHAY)
    cho(lambda: h.store.get(d) is not None
        and h.store.get(d).verifier.status == "VLM_TIMEOUT")
    assert len(h.vlm.luot) == 2
    assert h.store.get(d).verifier.reason == "qua_han_hang_cho"
    assert h.store.get(a).verifier.status == "VERIFIED"
    assert h.store.get(a).verifier.latency_ms == 6000
    assert h.store.get(c).verifier.latency_ms == 9000
    for eid in (a, b, c, d):               # mỗi event đúng một created
        assert [k for k, _ in _cua(h, eid)].count("created") == 1
    assert h.dp.cho_xong(0)


def test_kich_ban_8_cung_event_id_chi_mot_muc_keyframe_moi_nhat(he):
    h = he(max_workers=1)
    h.gui(ts=1.0, track=1)
    cho(lambda: len(h.vlm.luot) == 1)      # worker bận
    req = VerifyRequest(DEN, HOP, "HAM", "CRITICAL", 5.0)
    p_alert = kb._PendingAlert(future=None, deadline_wall=0.0, kind="NEW",
                               track_id=5, severity=kb.Severity.CRITICAL, ts=5.0,
                               detections=[kb.DET], image=None,
                               started_at=kb.BAT_DAU, event_id="cung-mot-event")
    h.dp.gui("cung-mot-event", req, p_alert)
    h.dh.tien_toi(1.0)
    h.dp.gui("cung-mot-event", VerifyRequest(TRANG, HOP, "HAM", "CRITICAL", 5.0),
             p_alert)
    assert h.dp.so_trong_hang == 1
    h.vlm.luot[0].tra(kb.CHAY)
    cho(lambda: len(h.vlm.luot) == 2)
    luot = h.vlm.luot[1]
    anh = cv2.imdecode(np.frombuffer(luot.frame_jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert anh.mean() > 200, "VLM phải nhận keyframe mới nhất"
    assert luot.timeout_s == pytest.approx(8.5), "hạn giữ từ lần gửi đầu (0 s)"
    luot.tra(kb.CHAY)
    cho(lambda: len(_cua(h, "cung-mot-event")) == 1)
    assert [k for k, _ in _cua(h, "cung-mot-event")] == ["created"]


def test_kich_ban_12_nguon_treo_van_timeout_dung_10s(he):
    """Không có heartbeat nào sau khi Voting quyết (nguồn treo): mốc 2 s và 10 s
    vẫn phát nhờ đồng hồ riêng; pipeline không giữ gì chờ ``_flush_pending``."""
    h = he()
    eid = h.gui(ts=7.0)
    assert h.p._pending == []
    cho(lambda: len(h.vlm.luot) == 1)
    h.dh.tien_toi(2.0)
    h.dh.tien_toi(10.0)
    assert [(k, e.event_id) for k, e in h.phat] == [("created", eid),
                                                    ("updated", eid)]
    assert h.phat[0][1].verifier.status == "PENDING"
    het = h.phat[1][1]
    assert (het.verifier.status, het.verifier.reason) == ("VLM_TIMEOUT", "timeout")
    assert het.verifier.needs_human_check is True


# ------------------------------------------------------------- bổ sung
def test_vlm_tat_thi_created_ngay_voi_vlm_off(he):
    h = he(vlm="tat")
    eid = h.gui(ts=1.0)
    assert [(k, e.event_id) for k, e in h.phat] == [("created", eid)]
    ev = h.phat[0][1]
    assert (ev.verifier.status, ev.verifier.reason) == ("VLM_OFF", "vlm_tat")
    assert ev.verifier.needs_human_check is True
    h.dh.tien_toi(30.0)
    assert len(h.phat) == 1


def test_khong_xac_minh_lai_sau_trang_thai_cuoi(he):
    h = he()
    eid = h.gui(ts=1.0)
    cho(lambda: len(h.vlm.luot) == 1)
    h.vlm.luot[0].tra(kb.CHAY)
    cho(lambda: len(h.phat) == 1)
    h.dp.gui(eid, VerifyRequest(DEN, HOP, "HAM", "CRITICAL", 1.0), None)
    assert h.dp.so_trong_hang == 0 and len(h.vlm.luot) == 1


def test_dong_ho_that_chay_dung_viec_va_bo_viec_da_huy():
    dh = DongHoThat()
    try:
        chay: list[str] = []
        xong = threading.Event()
        bo = dh.hen(dh.bay_gio() + 0.02, lambda: chay.append("bo"))
        dh.hen(dh.bay_gio() + 0.05, lambda: (chay.append("giu"), xong.set()))
        bo.huy()
        assert xong.wait(1.0)
        assert chay == ["giu"]
    finally:
        dh.dong()
