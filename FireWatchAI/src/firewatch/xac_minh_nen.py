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
"""

from __future__ import annotations

import heapq
import itertools
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from .alerts import VerifierInfo
from .config import Config
from .vlm import VerificationService, VerifyOutcome, VerifyRequest, trang_thai_verifier

log = logging.getLogger(__name__)

DU_PHONG_S = 0.5
"""Trừ khỏi ngân sách còn lại khi đặt timeout lượt gọi, để kết quả kịp ghi."""
TOI_THIEU_S = 1.0
"""Timeout lượt gọi nhỏ hơn mức này thì không gọi VLM nữa."""


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


# -------------------------------------------------------------- điều phối
TrangThaiMuc = Literal["cho", "dang_goi", "xong"]


@dataclass(eq=False)
class MucXacMinh:
    """Một cảnh báo đang được xác minh nền."""

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
    """Đã phát ``created`` chưa."""
    ve: list[VeHen] = field(default_factory=list)


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
        Phát ``created`` / ``updated`` cho một mục; được gọi khi đang giữ khoá
        của bộ điều phối, đúng một lần ``phat_tao`` cho mỗi ``event_id`` và
        ``phat_cap_nhat`` chỉ sau nó.
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
        self._cv = threading.Condition()
        self._muc: dict[str, MucXacMinh] = {}
        """Mục chưa có trạng thái cuối."""
        self._hang: OrderedDict[str, MucXacMinh] = OrderedDict()
        """Mục chờ worker, cũ nhất trước."""
        self._da_xong: set[str] = set()
        self._dung = False
        self._worker = [threading.Thread(target=self._lam, name=f"verifier-{i}",
                                         daemon=True)
                        for i in range(cfg.vlm.max_workers if service.enabled else 0)]
        for t in self._worker:
            t.start()

    # ------------------------------------------------------------ bên ngoài
    def gui(self, event_id: str, req: VerifyRequest, du_lieu: Any) -> None:
        """Nhận một cảnh báo vừa được Voting quyết. Không bao giờ chặn lâu.

        Cùng ``event_id`` còn trong hàng thì chỉ thay keyframe (hạn giữ nguyên);
        đang gọi hoặc đã có trạng thái cuối thì bỏ qua yêu cầu mới.
        """
        with self._cv:
            if event_id in self._da_xong:
                log.info("verifier %s: đã có trạng thái cuối, không xác minh lại",
                         event_id[:8])
                return
            cu = self._muc.get(event_id)
            if cu is not None:
                if cu.trang_thai == "cho":
                    cu.req = req
                    log.info("verifier %s: thay keyframe trong hàng chờ", event_id[:8])
                else:
                    log.info("verifier %s: đang gọi VLM, bỏ yêu cầu mới", event_id[:8])
                return
            now = self._dong_ho.bay_gio()
            m = MucXacMinh(event_id, req, du_lieu, now, now + self._ngan_sach)
            self._muc[event_id] = m
            if not self._service.enabled:
                self._ket_thuc(m, VerifyOutcome("UNVERIFIED", None, 0.0, 0,
                                                "vlm disabled", "vlm_tat"),
                               VerifierInfo.tao("VLM_OFF", reason="vlm_tat"))
                return
            if len(self._hang) >= self._toi_da:
                cu_nhat = next(iter(self._hang.values()))
                log.warning("hàng chờ verifier đầy (%d): bỏ %s", self._toi_da,
                            cu_nhat.event_id[:8])
                self._het_han(cu_nhat, "qua_han_hang_cho")
            self._hang[event_id] = m
            m.ve = [self._dong_ho.hen(now + self._grace, lambda: self._het_cua_so(m)),
                    self._dong_ho.hen(m.han, lambda: self._het_ngan_sach(m))]
            self._cv.notify_all()

    @property
    def so_trong_hang(self) -> int:
        """Số mục đang chờ worker."""
        with self._cv:
            return len(self._hang)

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
                m.trang_thai = "dang_goi"
                req = m.req
            outcome = self._service.goi_mot_lan(req, timeout)
            with self._cv:
                if m.trang_thai == "xong":
                    log.info("verifier %s: kết quả VLM đến sau ngân sách, bỏ",
                             m.event_id[:8])
                    continue
                outcome.latency_s = self._dong_ho.bay_gio() - m.t_quyet
                self._ket_thuc(m, outcome, trang_thai_verifier(outcome))

    # ---------------------------------------------------- trạng thái cuối
    def _het_han(self, m: MucXacMinh, ly_do: str) -> None:
        """``VLM_TIMEOUT``: ``qua_han_hang_cho`` nếu chưa gọi, ``timeout`` nếu
        đã gọi."""
        self._hang.pop(m.event_id, None)
        tre = self._dong_ho.bay_gio() - m.t_quyet
        da_goi = m.trang_thai == "dang_goi"
        self._ket_thuc(m, VerifyOutcome("UNVERIFIED", None, tre, int(da_goi),
                                        f"quá ngân sách ({ly_do})", ly_do),
                       VerifierInfo.tao("VLM_TIMEOUT", reason=ly_do))

    def _ket_thuc(self, m: MucXacMinh, outcome: VerifyOutcome,
                  info: VerifierInfo) -> None:
        """Gán trạng thái cuối và phát nó (giữ khoá khi gọi)."""
        m.trang_thai = "xong"
        for ve in m.ve:
            ve.huy()
        self._muc.pop(m.event_id, None)
        self._da_xong.add(m.event_id)
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
            log.exception("phát event %s lỗi", m.event_id[:8])
