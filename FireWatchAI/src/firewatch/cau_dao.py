"""Cầu dao của verifier bền vững (ADR 2026-11-07, mục cầu dao).

Đếm theo yêu cầu xác minh đã gọi VLM: lỗi, 429 và quá ngân sách đều là thất
bại; yêu cầu bị rút khỏi hàng chờ trước khi gọi không tính. ``loi_lien_tiep``
thất bại liên tiếp thì cầu dao mở trong ``mo_s`` giây; trong lúc mở không gọi
VLM. Hết ``mo_s`` thì nửa mở: cấp đúng một lượt gọi thử, thành công thì đóng,
thất bại thì mở lại. Nguồn thời gian tiêm được để test không ngủ thật.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Literal

log = logging.getLogger(__name__)

TrangThaiCauDao = Literal["dong", "mo", "nua_mo"]


class CauDao:
    """Máy trạng thái đóng → mở → nửa mở của cầu dao.

    Parameters
    ----------
    loi_lien_tiep : int
        Số thất bại liên tiếp (khi đang đóng) thì mở.
    mo_s : float
        Thời gian mở trước khi cho một lượt thử.
    bay_gio : callable
        Nguồn thời gian (giây, đơn điệu), cùng đồng hồ với bộ điều phối.
    """

    def __init__(self, loi_lien_tiep: int, mo_s: float,
                 bay_gio: Callable[[], float]):
        self._nguong, self._mo_s, self._bay_gio = loi_lien_tiep, mo_s, bay_gio
        self._khoa = threading.Lock()
        self._loi = 0
        """Thất bại liên tiếp kể từ lần thành công hoặc lần mở gần nhất."""
        self._mo_toi: float | None = None
        """Thời điểm hết ``mo_s``; ``None`` khi đóng."""
        self._dang_thu = False
        """Nửa mở và lượt thử đang chạy."""
        self.so_lan_mo = 0
        """Số lần cầu dao mở từ lúc khởi động."""

    def _trang_thai(self) -> TrangThaiCauDao:
        if self._mo_toi is None:
            return "dong"
        if self._dang_thu or self._bay_gio() >= self._mo_toi:
            return "nua_mo"
        return "mo"

    @property
    def trang_thai(self) -> TrangThaiCauDao:
        """``dong``, ``mo`` hoặc ``nua_mo`` tại thời điểm hỏi."""
        with self._khoa:
            return self._trang_thai()

    def dang_chan(self) -> bool:
        """True khi đang mở và chưa tới lúc thử; không tiêu lượt thử."""
        return self.trang_thai == "mo"

    def cho_phep(self) -> bool:
        """Có được gọi VLM ngay bây giờ không.

        Đóng: luôn được. Mở: không. Nửa mở: đúng một lượt thử được cấp; các
        lượt sau bị từ chối cho tới khi lượt thử kết thúc.
        """
        with self._khoa:
            st = self._trang_thai()
            if st == "dong":
                return True
            if st == "mo" or self._dang_thu:
                return False
            self._dang_thu = True
            log.info("cầu dao verifier nửa mở: cho một lượt gọi thử")
            return True

    def thanh_cong(self) -> None:
        """Một yêu cầu đã gọi VLM có câu trả lời: đóng cầu dao."""
        with self._khoa:
            if self._mo_toi is not None:
                log.info("cầu dao verifier đóng lại: VLM trả lời được")
            self._loi, self._mo_toi, self._dang_thu = 0, None, False

    def that_bai(self) -> None:
        """Một yêu cầu đã gọi VLM thất bại (lỗi, 429, quá ngân sách)."""
        with self._khoa:
            if self._mo_toi is not None:
                if self._dang_thu or self._bay_gio() >= self._mo_toi:
                    self._mo("lượt gọi thử thất bại")
                return
            self._loi += 1
            if self._loi >= self._nguong:
                self._mo(f"{self._loi} thất bại liên tiếp")

    def _mo(self, vi_sao: str) -> None:
        self._mo_toi = self._bay_gio() + self._mo_s
        self._dang_thu = False
        self._loi = 0
        self.so_lan_mo += 1
        log.warning("cầu dao verifier mở %.0fs (%s): không gọi VLM, event VLM_OFF",
                    self._mo_s, vi_sao)
