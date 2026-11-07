"""Xác minh VLM chạy nền khi cờ ``verifier.ben_vung`` bật (ADR 2026-11-07).

Mỗi cảnh báo của Voting thành một :class:`MucXacMinh`, khoá theo ``event_id``,
với ba mốc tính từ lúc Voting quyết:

* hết cửa sổ đồng bộ (``vlm.grace_s``) mà chưa có kết luận thì phát
  ``created`` với ``PENDING``;
* có kết luận trước ngân sách (``verifier.ngan_sach_s``) thì phát nó: qua
  ``created`` nếu còn trong cửa sổ, qua ``updated`` nếu đã phát ``PENDING``;
* hết ngân sách thì ``VLM_TIMEOUT``, kết quả đến sau bị bỏ.

Hai mốc thời gian do đồng hồ riêng (:class:`DongHoThat`, hoặc đồng hồ giả
trong test) gọi, không do vòng heartbeat, nên nguồn video treo thì cảnh báo vẫn
đúng hạn. Mọi chuyển trạng thái đi qua một khoá, vì vậy ``updated`` không bao
giờ phát trước ``created`` của cùng ``event_id``, và mỗi ``event_id`` có đúng
một trạng thái cuối.

Hàng chờ có giới hạn ``verifier.hang_cho_toi_da``; đầy thì mục cũ nhất bị bỏ với
``VLM_TIMEOUT`` (``qua_han_hang_cho``). Worker (số lượng ``vlm.max_workers``)
lấy việc từ hàng và gọi VLM với timeout bằng ngân sách còn lại trừ
:data:`DU_PHONG_S`; còn dưới :data:`TOI_THIEU_S` thì không gọi.

Cầu dao (:class:`~firewatch.cau_dao.CauDao`): ``verifier.cau_dao.loi_lien_tiep``
yêu cầu đã gọi VLM mà thất bại liên tiếp (lỗi, 429, quá ngân sách) thì mở
``verifier.cau_dao.mo_s`` giây. Đang mở thì cảnh báo nhận ``VLM_OFF``
(``cau_dao_mo``) ngay lúc gửi, không vào hàng; hết giờ mở thì nửa mở, đúng một
mục được gọi thử, các mục khác trong lúc đó nhận ``VLM_OFF``.
"""

from __future__ import annotations

import heapq
import itertools
import logging
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from .alerts import VerifierInfo
from .cau_dao import CauDao
from .config import Config
from .vlm import VerificationService, VerifyOutcome, VerifyRequest, trang_thai_verifier

log = logging.getLogger(__name__)

DU_PHONG_S = 0.5
"""Trừ khỏi ngân sách còn lại khi đặt timeout lượt gọi, để kết quả kịp ghi."""
TOI_THIEU_S = 1.0
"""Timeout lượt gọi nhỏ hơn mức này thì không gọi VLM nữa."""
CUA_SO_THONG_KE_S = 600.0
"""Cửa sổ trượt của thống kê trên ``/health`` (tỉ lệ kịp, p50 / p95)."""
TRANG_THAI_CAU_DAO_EN = {"dong": "closed", "mo": "open", "nua_mo": "half_open"}
"""Tên trạng thái cầu dao trong ``/health`` (API dùng tiếng Anh như event)."""
NHO_DA_XONG = 4096
"""Số khoá (``event_id``, lượt) đã có trạng thái cuối được nhớ để từ chối gửi
lại; giới hạn để bộ nhớ không tăng mãi khi chạy nhiều ngày."""


# ------------------------------------------------------------------ đồng hồ
class VeHen:
    """Vé của một việc đã hẹn; ``huy()`` để việc không chạy nữa."""

    __slots__ = ("da_huy",)

    def __init__(self) -> None:
        self.da_huy = False

    def huy(self) -> None:
        self.da_huy = True


class DongHo(Protocol):
    """Nguồn thời gian và bộ hẹn giờ; test tiêm đồng hồ giả."""

    def bay_gio(self) -> float:
        """Thời điểm hiện tại, giây, đơn điệu."""

    def hen(self, luc: float, viec: Callable[[], None]) -> VeHen:
        """Hẹn ``viec`` chạy khi ``bay_gio() >= luc``, trên luồng của đồng hồ."""

    def dong(self) -> None:
        """Dừng đồng hồ; việc chưa tới hạn bị bỏ."""


class DongHoThat:
    """Đồng hồ ``time.monotonic`` với một luồng hẹn giờ riêng.

    Việc tới hạn chạy trên luồng hẹn giờ, ngoài khoá của đồng hồ, nên việc đó
    được phép lấy khoá khác hay hẹn thêm việc.
    """

    def __init__(self) -> None:
        self._heap: list[tuple[float, int, VeHen, Callable[[], None]]] = []
        self._dem = itertools.count()
        self._cv = threading.Condition()
        self._dung = False
        self._luong = threading.Thread(target=self._chay, name="verifier-hen-gio",
                                       daemon=True)
        self._luong.start()

    def bay_gio(self) -> float:
        return time.monotonic()

    def hen(self, luc: float, viec: Callable[[], None]) -> VeHen:
        ve = VeHen()
        with self._cv:
            heapq.heappush(self._heap, (luc, next(self._dem), ve, viec))
            self._cv.notify()
        return ve

    def dong(self) -> None:
        with self._cv:
            self._dung = True
            self._heap.clear()
            self._cv.notify()

    def _chay(self) -> None:
        while True:
            with self._cv:
                while not self._dung:
                    if not self._heap:
                        self._cv.wait()
                        continue
                    con = self._heap[0][0] - time.monotonic()
                    if con <= 0:
                        break
                    self._cv.wait(con)
                if self._dung:
                    return
                _, _, ve, viec = heapq.heappop(self._heap)
            if ve.da_huy:
                continue
            try:
                viec()
            except Exception:  # noqa: BLE001 - luồng hẹn giờ không được chết
                log.exception("việc hẹn giờ của verifier lỗi")


def _phan_vi(xs: list[float], q: float) -> float | None:
    """Phân vị ``q`` của dãy đã sắp xếp, cùng cách tính với ``RunSummary``."""
    if not xs:
        return None
    return xs[int(q * (len(xs) - 1))]


def _ms(giay: float | None) -> int | None:
    return None if giay is None else int(round(giay * 1000))


# -------------------------------------------------------------- điều phối
TrangThaiMuc = Literal["cho", "dang_goi", "xong"]


Khoa = tuple[str, int]
"""(``event_id``, lượt xác minh): mỗi lượt có keyframe và trạng thái cuối riêng."""


@dataclass(eq=False)
class MucXacMinh:
    """Một lượt xác minh nền của một event."""

    event_id: str
    req: VerifyRequest
    du_lieu: Any
    """Dữ liệu cảnh báo của người gọi, trả lại nguyên vẹn trong callback."""
    t_quyet: float
    """Lúc Voting quyết, theo đồng hồ của bộ điều phối."""
    han: float
    """Hạn duy nhất: ``t_quyet + ngan_sach_s``."""
    trang_thai: TrangThaiMuc = "cho"
    da_tao: bool = False
    """Đã phát lần đầu (``phat_tao``) cho lượt này chưa."""
    ve: list[VeHen] = field(default_factory=list)
    luot: int = 1
    """Lượt xác minh của event (bắt đầu 1, ADR gom sự cố)."""

    @property
    def khoa(self) -> Khoa:
        return (self.event_id, self.luot)

    @property
    def nhan(self) -> str:
        """Nhãn ngắn trong log: 8 ký tự đầu của ``event_id`` và lượt."""
        return f"{self.event_id[:8]}#{self.luot}"


PhatFn = Callable[[MucXacMinh, VerifyOutcome, VerifierInfo], None]


class DieuPhoiXacMinh:
    """Hàng chờ, worker và hai mốc thời gian của verifier bền vững.

    Parameters
    ----------
    cfg : Config
        Lấy ``vlm.grace_s``, ``vlm.max_workers`` và khối ``verifier``.
    service : VerificationService
        Gọi VLM (``goi_mot_lan``); không có verifier thì mọi mục là ``VLM_OFF``.
    phat_tao, phat_cap_nhat : callable
        Phát lần đầu / lần sau cho một lượt; được gọi khi đang giữ khoá của bộ
        điều phối, đúng một lần ``phat_tao`` cho mỗi (``event_id``, lượt) và
        ``phat_cap_nhat`` chỉ sau nó. Với lượt 1 đó là ``created`` /
        ``updated``; lượt sau do lớp gom sự cố quyết phát gì.
    dong_ho : DongHo, optional
        Mặc định :class:`DongHoThat` (bộ điều phối tự đóng khi ``dong``).
    """

    def __init__(self, cfg: Config, service: VerificationService, *,
                 phat_tao: PhatFn, phat_cap_nhat: PhatFn,
                 dong_ho: DongHo | None = None):
        self._grace = cfg.vlm.grace_s
        self._ngan_sach = cfg.verifier.ngan_sach_s
        self._toi_da = cfg.verifier.hang_cho_toi_da
        self._service = service
        self._phat_tao, self._phat_cap_nhat = phat_tao, phat_cap_nhat
        self._dong_ho_rieng = dong_ho is None
        self._dong_ho: DongHo = dong_ho if dong_ho is not None else DongHoThat()
        self.cau_dao = CauDao(cfg.verifier.cau_dao.loi_lien_tiep,
                              cfg.verifier.cau_dao.mo_s, self._dong_ho.bay_gio)
        self._cv = threading.Condition()
        self._muc: dict[Khoa, MucXacMinh] = {}
        """Mục chưa có trạng thái cuối."""
        self._hang: OrderedDict[Khoa, MucXacMinh] = OrderedDict()
        """Mục chờ worker, cũ nhất trước."""
        self._da_xong: OrderedDict[Khoa, None] = OrderedDict()
        self._ket_qua: deque[tuple[float, float | None]] = deque()
        """(lúc có trạng thái cuối, độ trễ nếu VLM trả lời kịp) để thống kê."""
        self.so_vlm_off = 0
        """Số event đã phát ``VLM_OFF`` từ lúc khởi động."""
        self._dung = False
        self._worker = [threading.Thread(target=self._lam, name=f"verifier-{i}",
                                         daemon=True)
                        for i in range(cfg.vlm.max_workers if service.enabled else 0)]
        for t in self._worker:
            t.start()

    # ------------------------------------------------------------ bên ngoài
    def gui(self, event_id: str, req: VerifyRequest, du_lieu: Any,
            luot: int = 1) -> None:
        """Nhận một lượt xác minh. Không bao giờ chặn lâu.

        Khoá là (``event_id``, ``luot``). Cùng khoá còn trong hàng thì chỉ thay
        keyframe (hạn giữ nguyên); đang gọi hoặc đã có trạng thái cuối thì bỏ
        qua yêu cầu mới. Lượt mới của cùng ``event_id`` là một mục riêng.
        """
        khoa = (event_id, luot)
        with self._cv:
            if khoa in self._da_xong:
                log.info("verifier %s#%d: đã có trạng thái cuối, không xác minh lại",
                         event_id[:8], luot)
                return
            cu = self._muc.get(khoa)
            if cu is not None:
                if cu.trang_thai == "cho":
                    cu.req = req
                    log.info("verifier %s: thay keyframe trong hàng chờ", cu.nhan)
                else:
                    log.info("verifier %s: đang gọi VLM, bỏ yêu cầu mới", cu.nhan)
                return
            now = self._dong_ho.bay_gio()
            m = MucXacMinh(event_id, req, du_lieu, now, now + self._ngan_sach,
                           luot=luot)
            self._muc[khoa] = m
            if not self._service.enabled:
                self._vlm_off(m, "vlm_tat", "vlm disabled")
                return
            if self.cau_dao.dang_chan():
                self._vlm_off(m, "cau_dao_mo", "cầu dao mở")
                return
            if len(self._hang) >= self._toi_da:
                cu_nhat = next(iter(self._hang.values()))
                log.warning("hàng chờ verifier đầy (%d): bỏ %s", self._toi_da,
                            cu_nhat.nhan)
                self._het_han(cu_nhat, "qua_han_hang_cho")
            self._hang[khoa] = m
            m.ve = [self._dong_ho.hen(now + self._grace, lambda: self._het_cua_so(m)),
                    self._dong_ho.hen(m.han, lambda: self._het_ngan_sach(m))]
            self._cv.notify_all()

    @property
    def so_trong_hang(self) -> int:
        """Số mục đang chờ worker."""
        with self._cv:
            return len(self._hang)

    def thong_ke(self) -> dict[str, Any]:
        """Khối ``verifier`` của ``GET /health`` (chỉ khi cờ bật).

        Returns
        -------
        dict
            ``breaker`` (``closed`` / ``open`` / ``half_open``), ``breaker_opens``,
            ``queued``, ``window_s``, ``requests_in_window`` (yêu cầu có trạng
            thái cuối trong cửa sổ), ``answered_ratio_in_window`` (phần trong đó
            VLM trả lời kịp ngân sách; ``None`` khi chưa có yêu cầu),
            ``latency_p50_ms`` / ``latency_p95_ms`` của các câu trả lời kịp,
            tính từ lúc Voting quyết (``None`` khi không có), ``vlm_off_total``.
        """
        with self._cv:
            now = self._dong_ho.bay_gio()
            while self._ket_qua and now - self._ket_qua[0][0] > CUA_SO_THONG_KE_S:
                self._ket_qua.popleft()
            n = len(self._ket_qua)
            tre = sorted(t for _, t in self._ket_qua if t is not None)
            queued, vlm_off = len(self._hang), self.so_vlm_off
        return {"breaker": TRANG_THAI_CAU_DAO_EN[self.cau_dao.trang_thai],
                "breaker_opens": self.cau_dao.so_lan_mo,
                "queued": queued,
                "window_s": int(CUA_SO_THONG_KE_S),
                "requests_in_window": n,
                "answered_ratio_in_window": round(len(tre) / n, 3) if n else None,
                "latency_p50_ms": _ms(_phan_vi(tre, 0.5)),
                "latency_p95_ms": _ms(_phan_vi(tre, 0.95)),
                "vlm_off_total": vlm_off}

    def cho_xong(self, timeout_s: float) -> bool:
        """Chờ (giờ thật) tới khi mọi mục có trạng thái cuối; ``False`` nếu hết giờ."""
        with self._cv:
            return self._cv.wait_for(lambda: not self._muc, timeout_s)

    def dong(self) -> None:
        """Dừng worker (không chờ lượt gọi dở) và đồng hồ riêng."""
        with self._cv:
            self._dung = True
            self._cv.notify_all()
        if self._dong_ho_rieng:
            self._dong_ho.dong()

    # ------------------------------------------------------------- mốc giờ
    def _het_cua_so(self, m: MucXacMinh) -> None:
        with self._cv:
            if m.trang_thai == "xong" or m.da_tao:
                return
            tre = self._dong_ho.bay_gio() - m.t_quyet
            m.da_tao = True
            self._goi(self._phat_tao, m,
                      VerifyOutcome("UNVERIFIED", None, tre, 0,
                                    "vlm chưa trả lời trong grace_s"),
                      VerifierInfo.tao("PENDING", reason="cho_vlm"))

    def _het_ngan_sach(self, m: MucXacMinh) -> None:
        with self._cv:
            if m.trang_thai == "xong":
                return
            self._het_han(m, "timeout" if m.trang_thai == "dang_goi"
                          else "qua_han_hang_cho")

    # --------------------------------------------------------------- worker
    def _lam(self) -> None:
        while True:
            with self._cv:
                while not self._dung and not self._hang:
                    self._cv.wait()
                if self._dung:
                    return
                _, m = self._hang.popitem(last=False)
                timeout = m.han - self._dong_ho.bay_gio() - DU_PHONG_S
                if timeout < TOI_THIEU_S:
                    self._het_han(m, "qua_han_hang_cho")
                    continue
                if not self.cau_dao.cho_phep():
                    self._vlm_off(m, "cau_dao_mo", "cầu dao mở")
                    continue
                m.trang_thai = "dang_goi"
                req = m.req
            outcome = self._service.goi_mot_lan(req, timeout)
            with self._cv:
                if m.trang_thai == "xong":
                    # Đã VLM_TIMEOUT (và đã tính thất bại cho cầu dao).
                    log.info("verifier %s: kết quả VLM đến sau ngân sách, bỏ",
                             m.nhan)
                    continue
                if outcome.result is not None:
                    self.cau_dao.thanh_cong()
                else:
                    self.cau_dao.that_bai()
                outcome.latency_s = self._dong_ho.bay_gio() - m.t_quyet
                self._ket_thuc(m, outcome, trang_thai_verifier(outcome))

    # ---------------------------------------------------- trạng thái cuối
    def _het_han(self, m: MucXacMinh, ly_do: str) -> None:
        """``VLM_TIMEOUT``: ``qua_han_hang_cho`` nếu chưa gọi, ``timeout`` nếu
        đã gọi (tính là một thất bại cho cầu dao)."""
        self._hang.pop(m.khoa, None)
        tre = self._dong_ho.bay_gio() - m.t_quyet
        da_goi = m.trang_thai == "dang_goi"
        if da_goi:
            self.cau_dao.that_bai()
        self._ket_thuc(m, VerifyOutcome("UNVERIFIED", None, tre, int(da_goi),
                                        f"quá ngân sách ({ly_do})", ly_do),
                       VerifierInfo.tao("VLM_TIMEOUT", reason=ly_do))

    def _vlm_off(self, m: MucXacMinh, ly_do: str, loi: str) -> None:
        """``VLM_OFF`` ngay, không gọi VLM: VLM tắt hoặc cầu dao mở."""
        self._hang.pop(m.khoa, None)
        self.so_vlm_off += 1
        self._ket_thuc(m, VerifyOutcome("UNVERIFIED", None, 0.0, 0, loi, ly_do),
                       VerifierInfo.tao("VLM_OFF", reason=ly_do))

    def _ket_thuc(self, m: MucXacMinh, outcome: VerifyOutcome,
                  info: VerifierInfo) -> None:
        """Gán trạng thái cuối và phát nó (giữ khoá khi gọi)."""
        m.trang_thai = "xong"
        for ve in m.ve:
            ve.huy()
        self._muc.pop(m.khoa, None)
        self._da_xong[m.khoa] = None
        while len(self._da_xong) > NHO_DA_XONG:
            self._da_xong.popitem(last=False)
        now = self._dong_ho.bay_gio()
        self._ket_qua.append((now, outcome.latency_s if outcome.result is not None
                              else None))
        while self._ket_qua and now - self._ket_qua[0][0] > CUA_SO_THONG_KE_S:
            self._ket_qua.popleft()
        phat = self._phat_cap_nhat if m.da_tao else self._phat_tao
        m.da_tao = True
        self._goi(phat, m, outcome, info)
        self._cv.notify_all()

    @staticmethod
    def _goi(phat: PhatFn, m: MucXacMinh, outcome: VerifyOutcome,
             info: VerifierInfo) -> None:
        try:
            phat(m, outcome, info)
        except Exception:  # noqa: BLE001 - lỗi phát không được làm kẹt verifier
            log.exception("phát event %s lỗi", m.nhan)
