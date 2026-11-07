"""agreement.py: rời rạc hoá mỗi giây, κ, Bland–Altman, phân xử, gộp hai người.

Mọi nhãn ở đây là nhãn giả lập có κ và độ lệch biết trước.
"""

import math

import numpy as np
import pytest

from firewatch import agreement as ag


def _nhan(events=(), sau=(), rac=(), nguon="nguoi:A"):
    evs = []
    for tk, tl, te, tc in events:
        dau = min(v for v in (tk, tl) if v is not None)
        evs.append({"t_start": dau, "t_end": te,
                    "label": "fire" if tl is not None else "smoke",
                    "t_khoi": tk, "t_lua": tl, "tin_cay": tc})
    return {"schema": ag.SCHEMA, "clip_id": "x", "t0_goc": 0.0, "events": evs,
            "sau_chay": [list(k) for k in sau], "rac": [list(k) for k in rac],
            "nguon_nhan": nguon}


# ------------------------------------------------------------ rời rạc hoá
def test_nhan_moi_giay_tam_o_va_uu_tien():
    n = _nhan([(2.0, 5.0, 8.0, "cao")], sau=[(8.0, 10.0)], rac=[(6.2, 7.0)])
    got = ag.nhan_moi_giay(n, 10.5)
    # ô:      0  1  2  3  4  5  6(tâm 6.5 ∈ rac)  7  8  9  10 (tâm 10.25)
    exp = [0, 0, 1, 1, 1, 2, 4, 2, 3, 3, 0]
    assert got.tolist() == exp


def test_nhan_moi_giay_chi_khoi_va_file_am():
    n = _nhan([(1.0, None, 3.0, "vua")])
    assert ag.nhan_moi_giay(n, 4.0).tolist() == [0, 1, 1, 0]
    am = _nhan()
    assert ag.nhan_moi_giay(am, 3.0).tolist() == [0, 0, 0]


def test_chuan_hoa_nhan_cu_khong_co_t_khoi():
    cu = {"events": [{"t_start": 4.0, "t_end": 9.0, "label": "fire"}],
          "clip_id": "c", "t0_goc": 0.0}
    nh = ag.chuan_hoa(cu)
    assert nh["events"][0]["t_lua"] == 4.0 and nh["events"][0]["t_khoi"] is None
    assert nh["sau_chay"] == [] and nh["rac"] == []
    cu["events"][0]["label"] = "smoke"
    assert ag.chuan_hoa(cu)["events"][0]["t_khoi"] == 4.0


def test_kiem_nhan_bat_loi():
    ok = _nhan([(2.0, 5.0, 8.0, "cao")])
    assert ag.kiem_nhan(ok, 10.0) == []
    sai = _nhan([(2.0, 5.0, 8.0, "cao")])
    sai["events"][0]["t_start"] = 3.0
    sai["events"][0]["tin_cay"] = "trung_binh"
    sai["nguon_nhan"] = "ai_do"
    loi = " | ".join(ag.kiem_nhan(sai, 10.0))
    assert "t_start" in loi and "tin_cay" in loi and "nguon_nhan" in loi
    assert ag.kiem_nhan(_nhan([(2.0, None, 30.0, "vua")]), 10.0)
    cu = _nhan([(2.0, None, 5.0, None)], nguon="tu_dong_v1.0+duyet:CR")
    assert ag.kiem_nhan(cu) == []


# ------------------------------------------------------------------ κ
def test_kappa_vi_du_tinh_tay():
    # bảng 2x2 [[20, 5], [10, 15]]: po = 0,7; pe = 0,5 -> κ = 0,4
    a = [0] * 25 + [1] * 25
    b = [0] * 20 + [1] * 5 + [0] * 10 + [1] * 15
    assert math.isclose(ag.cohen_kappa(a, b), 0.4)
    assert ag.cohen_kappa(a, a) == 1.0
    assert math.isnan(ag.cohen_kappa([1, 1, 1], [1, 1, 1]))


@pytest.mark.parametrize("p", [0.0, 0.1, 0.2, 0.4])
def test_kappa_gia_lap_biet_truoc(p):
    """B = A, trừ một tỉ lệ p ô thay bằng lớp rút độc lập từ cùng phân bố.

    Khi đó E[p_o] = (1 - p) + p·Σπ², p_e = Σπ² nên κ kỳ vọng = 1 - p.
    """
    rng = np.random.default_rng(7)
    pi = np.array([0.55, 0.15, 0.15, 0.1, 0.05])
    n = 200_000
    a = rng.choice(5, n, p=pi)
    b = a.copy()
    doi = rng.random(n) < p
    b[doi] = rng.choice(5, int(doi.sum()), p=pi)
    assert abs(ag.cohen_kappa(a, b, 5) - (1 - p)) < 0.01


def test_kappa_bootstrap_theo_file_chua_gia_tri_that():
    rng = np.random.default_rng(1)
    pi = np.array([0.6, 0.2, 0.2])
    cap = []
    for _ in range(60):
        a = rng.choice(3, 80, p=pi)
        b = a.copy()
        doi = rng.random(80) < 0.2
        b[doi] = rng.choice(3, int(doi.sum()), p=pi)
        cap.append((a, b))
    lo, hi = ag.kappa_bootstrap(cap, so_lan=400, seed=3, k=3)
    assert lo < 0.8 < hi and hi - lo < 0.15


# ------------------------------------------------------------ Bland–Altman
def test_bland_altman_xac_dinh():
    x = np.arange(10, dtype=float)
    d = np.array([1, -1] * 5, dtype=float) + 0.5
    ba = ag.bland_altman(x, x + d)
    sd = float(np.std(d, ddof=1))
    assert ba["n"] == 10 and math.isclose(ba["lech_tb"], 0.5)
    assert math.isclose(ba["loa_duoi"], 0.5 - 1.96 * sd)
    assert math.isclose(ba["loa_tren"], 0.5 + 1.96 * sd)
    assert math.isclose(ba["trung_vi_abs"], 1.0)   # |1,5| và |-0,5| -> trung vị 1
    assert ba["ty_le_le_1s"] == 0.5 and ba["ty_le_le_3s"] == 1.0
    assert ag.bland_altman([], [])["n"] == 0


def test_bland_altman_gia_lap_lech_va_nhieu_biet_truoc():
    rng = np.random.default_rng(11)
    x = rng.uniform(0, 100, 50_000)
    y = x + 0.7 + rng.normal(0, 0.5, x.size)
    ba = ag.bland_altman(x, y)
    assert abs(ba["lech_tb"] - 0.7) < 0.01
    assert abs(ba["loa_tren"] - (0.7 + 1.96 * 0.5)) < 0.02
    assert abs(ba["loa_duoi"] - (0.7 - 1.96 * 0.5)) < 0.02


# ------------------------------------------------------- so cặp và phân xử
def test_khong_can_phan_xu_va_gop_lay_moc_som():
    a = _nhan([(10.0, 20.0, 50.0, "cao")], sau=[(50.0, 60.0)], rac=[(70.0, 71.0)])
    b = _nhan([(11.0, 18.5, 52.0, "vua")], sau=[(52.0, 60.0)], rac=[(70.0, 71.5)])
    s = ag.so_sanh_file("f", a, b, 80.0)
    assert not s.can_phan_xu, s.ly_do_phan_xu
    g = ag.gop_hai_nguoi(a, b, "A", "B", s)
    ev = g["events"][0]
    assert (ev["t_khoi"], ev["t_lua"], ev["t_end"], ev["t_start"]) == (10.0, 18.5,
                                                                      50.0, 10.0)
    assert ev["tin_cay"] == "vua" and ev["label"] == "fire"
    assert g["sau_chay"] == [[50.0, 60.0]] and g["rac"] == [[70.0, 71.5]]
    assert g["nguon_nhan"] == "nguoi:A+B"
    assert ag.kiem_nhan(g, 80.0) == []


@pytest.mark.parametrize("b, ly_do", [
    (_nhan(), "bat_dong_co_su_co"),
    (_nhan([(10.0, 24.5, 50.0, "cao")]), "t_lua_lech_gt_3s"),
    (_nhan([(None, 20.0, 50.0, "cao")]), "t_khoi_chi_mot_nguoi"),
    (_nhan([(10.0, 20.0, 50.0, "thap")]), "tin_cay_thap"),
    (_nhan([(10.0, 20.0, 50.0, "cao")], rac=[(60.0, 63.0)]), "rac_lech_gt_2s"),
    (_nhan([(10.0, 20.0, 50.0, "cao"), (65.0, None, 70.0, "cao")]), "so_su_co_khac"),
])
def test_quy_tac_phan_xu(b, ly_do):
    a = _nhan([(10.0, 20.0, 50.0, "cao")])
    s = ag.so_sanh_file("f", a, b, 80.0)
    assert s.can_phan_xu and ly_do in s.ly_do_phan_xu
    assert ag.gop_hai_nguoi(a, b, "A", "B", s) is None


def test_lech_dung_3s_khong_phan_xu():
    a = _nhan([(10.0, 20.0, 50.0, "cao")])
    b = _nhan([(13.0, 20.0, 47.0, "cao")])
    s = ag.so_sanh_file("f", a, b, 80.0)
    assert not s.can_phan_xu
    g = ag.gop_hai_nguoi(a, b, "A", "B", s)
    assert g["events"][0]["t_end"] == 47.0 and g["sau_chay"] == [[47.0, 50.0]]


def test_tong_hop_bo_gia_lap():
    """30 file: 20 dương (B lệch +0,5 s mọi mốc), 10 âm; 1 file bất đồng có/không."""
    ds = []
    for i in range(20):
        a = _nhan([(10.0, 20.0, 50.0, "cao")])
        b = _nhan([(10.5, 20.5, 50.5, "cao")])
        ds.append(ag.so_sanh_file(f"d{i}", a, b, 60.0))
    for i in range(10):
        b = _nhan([(30.0, None, 40.0, "cao")]) if i == 0 else _nhan()
        ds.append(ag.so_sanh_file(f"a{i}", _nhan(), b, 60.0))
    th = ag.tong_hop(ds, so_lan=200)
    for key in ag.MOC:
        assert th.bland_altman[key]["n"] == 20
        assert math.isclose(th.bland_altman[key]["lech_tb"], 0.5)
        assert math.isclose(th.bland_altman[key]["trung_vi_abs"], 0.5)
    # κ có sự cố: bảng [[9, 1], [0, 20]] -> po = 29/30, pe = (10*9 + 20*21)/900
    pe = (10 * 9 + 20 * 21) / 900
    assert math.isclose(th.kappa_co_su_co, (29 / 30 - pe) / (1 - pe))
    assert th.n_phan_xu == 1
    assert th.ma_tran_giay.sum() == 30 * 60
    assert th.dat_nguong()["trung_vi_t_khoi"]
