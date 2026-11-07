"""Verifier bền vững: cầu dao (kịch bản 5, 6 của ADR 2026-11-07).

Kịch bản 5: ba yêu cầu đã gọi VLM mà lỗi liên tiếp thì cầu dao mở; yêu cầu
thứ tư không gọi VLM, nhận ``VLM_OFF`` (``cau_dao_mo``) ngay; sau ``mo_s`` nửa
mở, đúng một lượt gọi thử, thành công thì đóng. Kịch bản 6: HTTP 429 liên tiếp
tính như lỗi. Đồng hồ giả do test đẩy; VLM giả chặn tới khi test trả lời hoặc
ném lỗi, nên không test nào ngủ thật để chờ mốc thời gian.
"""

from __future__ import annotations

import pytest

from firewatch.cau_dao import CauDao
from firewatch.vlm import GeminiHTTPError, VerifyOutcome, trang_thai_verifier

import he_verifier as hv
import kich_ban_verifier as kb


def _loi(h, i: int, loi: BaseException) -> None:
    """Chờ lượt gọi thứ ``i`` (từ 0) rồi cho nó kết thúc bằng ``loi``."""
    hv.cho(lambda: len(h.vlm.luot) > i)
    h.vlm.luot[i].nem(loi)


def _co_event(h, eid: str) -> None:
    hv.cho(lambda: h.store.get(eid) is not None)


# ------------------------------------------------------------- máy trạng thái
def test_cau_dao_dong_mo_nua_mo_theo_dong_ho_tiem():
    t = [0.0]
    cd = CauDao(3, 60.0, lambda: t[0])
    assert cd.trang_thai == "dong" and cd.cho_phep() and not cd.dang_chan()
    cd.that_bai()
    cd.that_bai()
    cd.thanh_cong()                          # thành công xoá đếm liên tiếp
    cd.that_bai()
    cd.that_bai()
    assert cd.trang_thai == "dong" and cd.so_lan_mo == 0
    cd.that_bai()                            # lỗi thứ 3 liên tiếp
    assert cd.trang_thai == "mo" and cd.dang_chan() and not cd.cho_phep()
    assert cd.so_lan_mo == 1
    t[0] = 59.9
    assert cd.trang_thai == "mo"
    t[0] = 60.0
    assert cd.trang_thai == "nua_mo" and not cd.dang_chan()
    assert cd.cho_phep() and not cd.cho_phep(), "nửa mở cấp đúng một lượt thử"
    assert cd.trang_thai == "nua_mo"
    cd.that_bai()                            # lượt thử thất bại: mở lại 60 s
    assert cd.trang_thai == "mo" and cd.so_lan_mo == 2
    t[0] = 120.0
    assert cd.cho_phep()
    cd.thanh_cong()
    assert cd.trang_thai == "dong" and cd.cho_phep() and cd.so_lan_mo == 2


def test_trang_thai_verifier_cau_dao_mo_la_vlm_off():
    v = trang_thai_verifier(VerifyOutcome("UNVERIFIED", None, 0.0, 0,
                                          "cầu dao mở", "cau_dao_mo"))
    assert (v.status, v.reason, v.needs_human_check) == ("VLM_OFF", "cau_dao_mo",
                                                         True)


# ------------------------------------------------------------- kịch bản 5, 6
@pytest.mark.parametrize("loi, ma", [
    (GeminiHTTPError(500, "<html>lỗi máy chủ</html>"), "http_5xx"),  # kịch bản 5
    (GeminiHTTPError(429, "quota"), "http_429"),                      # kịch bản 6
    (OSError("connection reset"), "loi_mang"),
])
def test_kich_ban_5_6_ba_loi_lien_tiep_mo_cau_dao_roi_nua_mo(he, loi, ma):
    h = he(max_workers=2)
    for i in range(3):
        eid = h.gui(ts=float(i), track=i)
        _loi(h, i, loi)
        _co_event(h, eid)
        v = h.store.get(eid).verifier
        assert (v.status, v.reason, v.needs_human_check) == ("VLM_ERROR", ma, True)
    hv.cho(lambda: h.dp.cau_dao.trang_thai == "mo")
    assert h.dp.cau_dao.so_lan_mo == 1
    assert [k for k, _ in h.phat] == ["created"] * 3
    # yêu cầu thứ tư: không gọi VLM, VLM_OFF ngay lúc gửi, không vào hàng
    d = h.gui(ts=3.0, track=3)
    assert [(k, e.event_id) for k, e in h.phat][-1] == ("created", d)
    ev = h.store.get(d)
    assert (ev.verifier.status, ev.verifier.reason, ev.verifier.needs_human_check
            ) == ("VLM_OFF", "cau_dao_mo", True)
    assert ev.verification == "UNVERIFIED" and ev.severity == "CRITICAL"
    assert len(h.vlm.luot) == 3 and h.dp.so_trong_hang == 0
    assert h.s.alerts[-1]["verifier_status"] == "VLM_OFF"
    # mọi mốc 2 s / 10 s đã huỷ: đẩy đồng hồ không phát thêm gì
    h.dh.tien_toi(59.9)
    assert h.dp.cau_dao.trang_thai == "mo" and len(h.phat) == 4
    h.dh.tien_toi(60.0)
    assert h.dp.cau_dao.trang_thai == "nua_mo"
    # nửa mở: E được gọi thử; F đến trong lúc thử thì VLM_OFF, không gọi
    e = h.gui(ts=60.0, track=4)
    hv.cho(lambda: len(h.vlm.luot) == 4)
    assert h.vlm.luot[3].timeout_s == pytest.approx(9.5)
    f = h.gui(ts=60.5, track=5)
    _co_event(h, f)
    assert (h.store.get(f).verifier.status, h.store.get(f).verifier.reason) == (
        "VLM_OFF", "cau_dao_mo")
    assert len(h.vlm.luot) == 4
    h.vlm.luot[3].tra(kb.CHAY)
    hv.cho(lambda: h.store.get(e) is not None
           and h.store.get(e).verifier.status == "VERIFIED")
    assert h.dp.cau_dao.trang_thai == "dong"
    # đã đóng: yêu cầu sau được gọi bình thường
    g = h.gui(ts=61.0, track=6)
    hv.cho(lambda: len(h.vlm.luot) == 5)
    h.vlm.luot[4].tra(kb.CHAY)
    hv.cho(lambda: h.store.get(g) is not None
           and h.store.get(g).verifier.status == "VERIFIED")
    assert h.dp.cho_xong(0)
    for eid in (d, e, f, g):
        assert [k for k, _ in hv.cua(h, eid)] == ["created"]


def test_luot_thu_that_bai_thi_mo_lai_du_mo_s(he):
    h = he(max_workers=1, cau_dao={"loi_lien_tiep": 2, "mo_s": 30})
    for i in range(2):
        eid = h.gui(ts=float(i), track=i)
        _loi(h, i, GeminiHTTPError(503, "unavailable"))
        _co_event(h, eid)
    hv.cho(lambda: h.dp.cau_dao.trang_thai == "mo")
    h.dh.tien_toi(30.0)
    assert h.dp.cau_dao.trang_thai == "nua_mo"
    e = h.gui(ts=30.0, track=2)
    _loi(h, 2, GeminiHTTPError(503, "unavailable"))
    _co_event(h, e)
    assert h.store.get(e).verifier.status == "VLM_ERROR"
    hv.cho(lambda: h.dp.cau_dao.trang_thai == "mo")
    assert h.dp.cau_dao.so_lan_mo == 2
    h.dh.tien_toi(59.9)
    assert h.dp.cau_dao.trang_thai == "mo"
    h.dh.tien_toi(60.0)
    assert h.dp.cau_dao.trang_thai == "nua_mo"


def test_qua_ngan_sach_tinh_la_that_bai_va_ket_qua_muon_khong_dong_lai(he):
    h = he(max_workers=1)
    a = h.gui(ts=0.0, track=0)
    hv.cho(lambda: len(h.vlm.luot) == 1)
    h.dh.tien_toi(10.0)                      # VLM_TIMEOUT (timeout): thất bại 1
    assert h.store.get(a).verifier.reason == "timeout"
    assert h.dp.cau_dao.trang_thai == "dong"
    h.vlm.luot[0].tra(kb.CHAY)               # kết quả muộn: bỏ, không xoá đếm
    hv.cho(lambda: h.vlm.luot[0].da_xong.is_set())
    for i in (1, 2):
        eid = h.gui(ts=10.0 + i, track=i)
        _loi(h, i, GeminiHTTPError(500, "lỗi"))
        _co_event(h, eid)
    hv.cho(lambda: h.dp.cau_dao.trang_thai == "mo")
    assert h.dp.cau_dao.so_lan_mo == 1


def test_thanh_cong_xoa_dem_loi_lien_tiep(he):
    h = he(max_workers=1)
    loi = GeminiHTTPError(500, "lỗi")
    for i, ket in enumerate([loi, loi, None, loi, loi]):
        eid = h.gui(ts=float(i), track=i)
        hv.cho(lambda i=i: len(h.vlm.luot) > i)
        if ket is None:
            h.vlm.luot[i].tra(kb.CHAY)
        else:
            h.vlm.luot[i].nem(ket)
        _co_event(h, eid)
    assert h.dp.cau_dao.trang_thai == "dong" and h.dp.cau_dao.so_lan_mo == 0
    eid = h.gui(ts=5.0, track=5)
    _loi(h, 5, loi)
    _co_event(h, eid)
    hv.cho(lambda: h.dp.cau_dao.trang_thai == "mo")


def test_muc_dang_cho_trong_hang_khi_cau_dao_mo_thi_vlm_off(he):
    """Cầu dao mở trong lúc mục còn chờ worker: worker không gọi, VLM_OFF."""
    h = he(max_workers=1, cau_dao={"loi_lien_tiep": 1, "mo_s": 60})
    a = h.gui(ts=0.0, track=0)
    hv.cho(lambda: len(h.vlm.luot) == 1)     # worker duy nhất bận với A
    b = h.gui(ts=1.0, track=1)               # B chờ trong hàng
    assert h.dp.so_trong_hang == 1
    h.vlm.luot[0].nem(GeminiHTTPError(500, "lỗi"))   # A lỗi: mở ngay
    _co_event(h, a)
    _co_event(h, b)
    assert h.store.get(b).verifier.status == "VLM_OFF"
    assert h.store.get(b).verifier.reason == "cau_dao_mo"
    assert len(h.vlm.luot) == 1
