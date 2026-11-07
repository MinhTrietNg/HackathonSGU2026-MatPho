"""Đồng thuận giữa hai người gán mốc sự cố, cho nhãn JSON lược đồ ``t1_dev_v1.1``.

Định nghĩa trường theo ``docs/huong_dan_gan_nhan_su_co_v1.md``. Module chỉ dùng
numpy và thư viện chuẩn (không có scipy / sklearn trong môi trường).

Rời rạc hoá nhãn mỗi giây
-------------------------
File dài ``D`` giây được chia thành ô ``[k*step, (k+1)*step)``, ô cuối cắt tại
``D``. Lớp của ô là trạng thái tại **tâm ô** (ô cuối: tâm của phần còn lại), theo
thứ tự ưu tiên::

    rac  >  sự cố  >  sau_chay  >  khong

Trong một sự cố ``[t_start, t_end)``: lớp ``lua`` khi ``t_lua`` khác null và tâm
ô ``>= t_lua``; ngược lại là ``khoi``. Nghĩa là ``lua`` mô tả *pha* của sự cố (đã
thấy lửa), không phải từng khung có ngọn lửa. Mã lớp: 0 ``khong``, 1 ``khoi``,
2 ``lua``, 3 ``sau_chay``, 4 ``rac``.

Quy tắc phân xử (đề xuất, xem ``can_phan_xu``) và giá trị cuối khi không cần
phân xử (xem ``gop_hai_nguoi``) ghi trong docstring từng hàm.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np

SCHEMA = "t1_dev_v1.1"
LOP: tuple[str, ...] = ("khong", "khoi", "lua", "sau_chay", "rac")
KHONG, KHOI, LUA, SAU_CHAY, RAC = range(5)
TIN_CAY: tuple[str, ...] = ("thap", "vua", "cao")   # tăng dần
MOC: tuple[str, ...] = ("t_khoi", "t_lua", "t_end")

# Ngưỡng phân xử và ngưỡng chấp nhận: ĐỀ XUẤT, chủ repo chốt trước lượt gán.
NGUONG_DT_PHAN_XU = 3.0       # |Δt| > 3 s ở một mốc -> người thứ ba
NGUONG_VUNG_PHAN_XU = 2.0     # lệch tổng độ dài rac / sau_chay > 2 s -> người thứ ba
NGUONG_KAPPA = 0.8            # κ mỗi giây và κ "có sự cố"
NGUONG_TRUNG_VI_DT = 1.0      # trung vị |Δt| của từng mốc

_NGUON_NHAN = re.compile(
    r"^(tu_dong_v\d+\.\d+(\+duyet:[\w.-]+)?|nguoi:[\w.+-]+|phan_xu:[\w.+-]+)$")


# --------------------------------------------------------------------- nhãn
def _khoang(x: Iterable[Sequence[float]] | None) -> list[tuple[float, float]]:
    """Danh sách khoảng ``[a, b)`` đã sắp xếp; bỏ khoảng rỗng."""
    out = [(float(a), float(b)) for a, b in (x or []) if float(b) > float(a)]
    return sorted(out)


def moc_dau(ev: dict[str, Any]) -> float | None:
    """Dấu hiệu đầu tiên của sự cố: min các ``t_khoi``, ``t_lua`` khác null.

    Thiếu cả hai thì dùng ``t_start`` (nhãn cũ ``tu_dong_v1.0``).
    """
    vals = [ev.get(k) for k in ("t_khoi", "t_lua")]
    vals = [float(v) for v in vals if v is not None]
    if vals:
        return min(vals)
    return None if ev.get("t_start") is None else float(ev["t_start"])


def chuan_hoa(nhan: dict[str, Any]) -> dict[str, Any]:
    """Bản sao nhãn đủ khoá; thiếu khoá = rỗng / null (CHUNG §3.1).

    Nhãn cũ chỉ có ``t_start`` được coi như ``t_lua`` khi ``label == "fire"``,
    ``t_khoi`` khi ``label == "smoke"``.
    """
    evs = []
    for ev in nhan.get("events") or []:
        e = dict(ev)
        if "t_khoi" not in e and "t_lua" not in e and e.get("t_start") is not None:
            key = "t_lua" if e.get("label") == "fire" else "t_khoi"
            e[key] = float(e["t_start"])
        e.setdefault("t_khoi", None)
        e.setdefault("t_lua", None)
        e.setdefault("tin_cay", None)
        e["t_start"] = moc_dau(e)
        evs.append(e)
    out = dict(nhan)
    out["events"] = sorted(evs, key=lambda e: (e["t_start"] is None, e["t_start"]))
    out["sau_chay"] = [list(k) for k in _khoang(nhan.get("sau_chay"))]
    out["rac"] = [list(k) for k in _khoang(nhan.get("rac"))]
    return out


def kiem_nhan(nhan: dict[str, Any], thoi_luong: float | None = None) -> list[str]:
    """Lỗi lược đồ ``t1_dev_v1.1`` của một nhãn (danh sách rỗng = hợp lệ).

    Parameters
    ----------
    nhan : dict
        Nội dung một file ``<file>.json``.
    thoi_luong : float, optional
        Độ dài video; có thì kiểm mốc nằm trong ``[0, thoi_luong + 0.5]``.
    """
    loi: list[str] = []
    if nhan.get("schema") != SCHEMA:
        loi.append(f"schema phải là {SCHEMA}")
    if not nhan.get("clip_id"):
        loi.append("thiếu clip_id")
    nguon = nhan.get("nguon_nhan", "")
    if not _NGUON_NHAN.match(str(nguon)):
        loi.append(f"nguon_nhan không hợp lệ: {nguon!r}")
    tran = math.inf if thoi_luong is None else float(thoi_luong) + 0.5
    for i, ev in enumerate(nhan.get("events") or []):
        tk, tl, te = ev.get("t_khoi"), ev.get("t_lua"), ev.get("t_end")
        if tk is None and tl is None:
            loi.append(f"sự cố {i}: thiếu cả t_khoi và t_lua")
            continue
        dau = min(float(v) for v in (tk, tl) if v is not None)
        if ev.get("t_start") is None or abs(float(ev["t_start"]) - dau) > 1e-6:
            loi.append(f"sự cố {i}: t_start phải bằng min(t_khoi, t_lua) = {dau}")
        if te is None or float(te) <= dau:
            loi.append(f"sự cố {i}: t_end phải lớn hơn mốc đầu")
        elif float(te) > tran:
            loi.append(f"sự cố {i}: t_end vượt độ dài video")
        if dau < 0:
            loi.append(f"sự cố {i}: mốc âm")
        if ev.get("label") not in ("fire", "smoke"):
            loi.append(f"sự cố {i}: label phải là fire|smoke")
        tc = ev.get("tin_cay")
        bat_buoc = not str(nguon).startswith("tu_dong")
        if (tc is not None or bat_buoc) and tc not in TIN_CAY:
            loi.append(f"sự cố {i}: tin_cay phải thuộc {TIN_CAY}")
    for key in ("sau_chay", "rac"):
        for k in nhan.get(key) or []:
            if len(k) != 2 or float(k[1]) <= float(k[0]) or float(k[0]) < 0:
                loi.append(f"{key}: khoảng không hợp lệ {k}")
            elif float(k[1]) > tran:
                loi.append(f"{key}: khoảng vượt độ dài video {k}")
    return loi


def co_su_co(nhan: dict[str, Any]) -> int:
    """1 nếu file có ít nhất một sự cố, ngược lại 0."""
    return int(bool(nhan.get("events")))


def _trong(t: float, khoang: list[tuple[float, float]]) -> bool:
    return any(a <= t < b for a, b in khoang)


def nhan_moi_giay(nhan: dict[str, Any], thoi_luong: float,
                  buoc: float = 1.0) -> np.ndarray:
    """Lớp của từng ô ``buoc`` giây (mã trong ``LOP``), lấy tại tâm ô.

    Parameters
    ----------
    nhan : dict
        Nhãn JSON (đã hoặc chưa ``chuan_hoa``).
    thoi_luong : float
        Độ dài video, giây.
    buoc : float
        Độ rộng ô, mặc định 1 s.

    Returns
    -------
    numpy.ndarray
        Mảng ``int8`` dài ``ceil(thoi_luong / buoc)``.
    """
    n = max(0, math.ceil(thoi_luong / buoc - 1e-9))
    nh = chuan_hoa(nhan)
    rac = _khoang(nh["rac"])
    sau = _khoang(nh["sau_chay"])
    out = np.full(n, KHONG, dtype=np.int8)
    for k in range(n):
        a = k * buoc
        c = (a + min(a + buoc, thoi_luong)) / 2.0
        if _trong(c, rac):
            out[k] = RAC
            continue
        lop = None
        for ev in nh["events"]:
            dau, te = ev["t_start"], ev.get("t_end")
            if dau is None or te is None or not dau <= c < float(te):
                continue
            tl = ev.get("t_lua")
            lop = LUA if tl is not None and c >= float(tl) else KHOI
            if lop == LUA:
                break
        if lop is not None:
            out[k] = lop
        elif _trong(c, sau):
            out[k] = SAU_CHAY
    return out


# ------------------------------------------------------------------- thống kê
def ma_tran_nham(a: np.ndarray, b: np.ndarray, k: int = len(LOP)) -> np.ndarray:
    """Ma trận đếm ``k x k``: hàng = người A, cột = người B."""
    a = np.asarray(a, dtype=int)
    b = np.asarray(b, dtype=int)
    if a.shape != b.shape:
        raise ValueError("hai dãy nhãn phải cùng độ dài")
    m = np.zeros((k, k), dtype=np.int64)
    np.add.at(m, (a, b), 1)
    return m


def cohen_kappa(a: Sequence[int], b: Sequence[int],
                k: int | None = None) -> float:
    """Cohen κ không trọng số giữa hai dãy nhãn rời rạc.

    ``κ = (p_o - p_e) / (1 - p_e)``. Trả ``nan`` khi ``p_e = 1`` (cả hai người
    chỉ dùng một lớp duy nhất, κ không xác định) hoặc dãy rỗng.
    """
    a = np.asarray(a, dtype=int)
    b = np.asarray(b, dtype=int)
    if a.size == 0:
        return float("nan")
    k = int(max(a.max(), b.max()) + 1) if k is None else k
    m = ma_tran_nham(a, b, k).astype(float)
    n = m.sum()
    po = np.trace(m) / n
    pe = float((m.sum(1) / n) @ (m.sum(0) / n))
    if pe >= 1.0 - 1e-12:
        return float("nan")
    return float((po - pe) / (1.0 - pe))


def kappa_bootstrap(cap: Sequence[tuple[np.ndarray, np.ndarray]], so_lan: int = 2000,
                    seed: int = 0, alpha: float = 0.05,
                    k: int = len(LOP)) -> tuple[float, float]:
    """Khoảng bootstrap phân vị cho κ, lấy mẫu lại theo **file** (cụm).

    Các giây trong cùng file tương quan mạnh, nên đơn vị lấy mẫu là file.
    Lần lặp cho κ ``nan`` bị bỏ.
    """
    if not cap:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    mats = [ma_tran_nham(a, b, k) for a, b in cap]
    stack = np.stack(mats).astype(float)
    vals = []
    for _ in range(so_lan):
        idx = rng.integers(0, len(mats), len(mats))
        m = stack[idx].sum(0)
        n = m.sum()
        if n == 0:
            continue
        po = np.trace(m) / n
        pe = float((m.sum(1) / n) @ (m.sum(0) / n))
        if pe < 1.0 - 1e-12:
            vals.append((po - pe) / (1.0 - pe))
    if not vals:
        return (float("nan"), float("nan"))
    lo, hi = np.quantile(vals, [alpha / 2, 1 - alpha / 2])
    return (float(lo), float(hi))


def bland_altman(x: Sequence[float], y: Sequence[float]) -> dict[str, float]:
    """Thống kê Bland–Altman cho cặp mốc ``(x = người A, y = người B)``.

    Returns
    -------
    dict
        ``n``; ``lech_tb`` = trung bình ``y - x``; ``sd`` (ddof = 1);
        ``loa_duoi``, ``loa_tren`` = ``lech_tb ± 1.96 sd``; ``trung_vi_abs`` =
        trung vị ``|y - x|``; ``ty_le_le_1s``, ``ty_le_le_3s`` = tỉ lệ
        ``|y - x| <= 1`` và ``<= 3`` giây. Thiếu dữ liệu thì ``nan``.
    """
    d = np.asarray(y, dtype=float) - np.asarray(x, dtype=float)
    n = int(d.size)
    nan = float("nan")
    if n == 0:
        return {"n": 0, "lech_tb": nan, "sd": nan, "loa_duoi": nan, "loa_tren": nan,
                "trung_vi_abs": nan, "ty_le_le_1s": nan, "ty_le_le_3s": nan}
    mean = float(d.mean())
    sd = float(d.std(ddof=1)) if n > 1 else nan
    ad = np.abs(d)
    return {"n": n, "lech_tb": mean, "sd": sd,
            "loa_duoi": mean - 1.96 * sd, "loa_tren": mean + 1.96 * sd,
            "trung_vi_abs": float(np.median(ad)),
            "ty_le_le_1s": float(np.mean(ad <= 1.0 + 1e-9)),
            "ty_le_le_3s": float(np.mean(ad <= 3.0 + 1e-9))}


# ------------------------------------------------------------- so cặp, phân xử
def ghep_su_co(ev_a: list[dict], ev_b: list[dict]) -> list[tuple[int | None,
                                                                  int | None]]:
    """Ghép sự cố của hai người theo độ chồng lấn ``[t_start, t_end)`` lớn nhất.

    Ghép tham lam theo độ chồng lấn giảm dần; cặp không chồng lấn không ghép.
    Sự cố còn lại ghép với ``None``.
    """
    cands = []
    for i, a in enumerate(ev_a):
        for j, b in enumerate(ev_b):
            lo = max(a["t_start"], b["t_start"])
            hi = min(a["t_end"], b["t_end"])
            if hi > lo:
                cands.append((hi - lo, i, j))
    cands.sort(reverse=True)
    used_a: set[int] = set()
    used_b: set[int] = set()
    pairs: list[tuple[int | None, int | None]] = []
    for _, i, j in cands:
        if i not in used_a and j not in used_b:
            pairs.append((i, j))
            used_a.add(i)
            used_b.add(j)
    pairs += [(i, None) for i in range(len(ev_a)) if i not in used_a]
    pairs += [(None, j) for j in range(len(ev_b)) if j not in used_b]
    return pairs


def _do_dai(k: list[tuple[float, float]]) -> float:
    return sum(b - a for a, b in _hop(k))


def _hop(k: Iterable[Sequence[float]]) -> list[tuple[float, float]]:
    """Hợp các khoảng (gộp khoảng chồng hoặc chạm nhau)."""
    out: list[list[float]] = []
    for a, b in _khoang(k):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _lech_vung(ka: list, kb: list) -> float:
    """Độ dài hiệu đối xứng của hai tập khoảng."""
    hop = _do_dai(list(ka) + list(kb))
    giao = 0.0
    for a0, a1 in _hop(ka):
        for b0, b1 in _hop(kb):
            giao += max(0.0, min(a1, b1) - max(a0, b0))
    return hop - giao


@dataclass
class SoSanhFile:
    """Kết quả so nhãn hai người trên một file."""

    file: str
    co_a: int
    co_b: int
    giay_a: np.ndarray
    giay_b: np.ndarray
    cap_su_co: list[tuple[int | None, int | None]]
    lech_moc: list[dict[str, Any]] = field(default_factory=list)
    ly_do_phan_xu: list[str] = field(default_factory=list)

    @property
    def can_phan_xu(self) -> bool:
        """Có ít nhất một lý do phải nhờ người thứ ba."""
        return bool(self.ly_do_phan_xu)


def so_sanh_file(ten: str, nhan_a: dict, nhan_b: dict, thoi_luong: float,
                 buoc: float = 1.0) -> SoSanhFile:
    """So nhãn hai người trên một file và liệt kê lý do phải phân xử.

    Quy tắc phân xử (đề xuất; một điều kiện là đủ):

    1. Bất đồng "có sự cố" hoặc số sự cố khác nhau (có sự cố không ghép được).
    2. Một mốc (``t_khoi`` / ``t_lua`` / ``t_end``) có ở người này, null ở người kia.
    3. ``|Δt| > NGUONG_DT_PHAN_XU`` (3 s) ở bất kỳ mốc nào.
    4. Một trong hai người ghi ``tin_cay = thap``.
    5. Hiệu đối xứng của ``rac`` hoặc của ``sau_chay`` dài hơn
       ``NGUONG_VUNG_PHAN_XU`` (2 s).
    """
    a = chuan_hoa(nhan_a)
    b = chuan_hoa(nhan_b)
    res = SoSanhFile(ten, co_su_co(a), co_su_co(b), nhan_moi_giay(a, thoi_luong, buoc),
                     nhan_moi_giay(b, thoi_luong, buoc),
                     ghep_su_co(a["events"], b["events"]))
    ly_do = res.ly_do_phan_xu
    if res.co_a != res.co_b:
        ly_do.append("bat_dong_co_su_co")
    elif any(i is None or j is None for i, j in res.cap_su_co):
        ly_do.append("so_su_co_khac")
    for i, j in res.cap_su_co:
        if i is None or j is None:
            continue
        ea, eb = a["events"][i], b["events"][j]
        for key in MOC:
            va, vb = ea.get(key), eb.get(key)
            rec = {"su_co": i, "moc": key, "a": va, "b": vb}
            if (va is None) != (vb is None):
                ly_do.append(f"{key}_chi_mot_nguoi")
            elif va is not None:
                rec["dt"] = float(vb) - float(va)
                if abs(rec["dt"]) > NGUONG_DT_PHAN_XU + 1e-9:
                    ly_do.append(f"{key}_lech_gt_{NGUONG_DT_PHAN_XU:g}s")
            res.lech_moc.append(rec)
    if any(e.get("tin_cay") == "thap" for e in a["events"] + b["events"]):
        ly_do.append("tin_cay_thap")
    for key in ("rac", "sau_chay"):
        if _lech_vung(a[key], b[key]) > NGUONG_VUNG_PHAN_XU + 1e-9:
            ly_do.append(f"{key}_lech_gt_{NGUONG_VUNG_PHAN_XU:g}s")
    return res


def gop_hai_nguoi(nhan_a: dict, nhan_b: dict, ma_a: str, ma_b: str,
                  so_sanh: SoSanhFile) -> dict[str, Any] | None:
    """Giá trị cuối khi KHÔNG cần phân xử; ``None`` nếu cần người thứ ba.

    Quy tắc (đề xuất, thống nhất với luật "mốc sớm hơn" của quy ước dữ liệu §7):

    - ``t_khoi``, ``t_lua``: giá trị **sớm hơn** của hai người (thời gian phát
      hiện không bị tính dễ hơn thực tế).
    - ``t_end``: giá trị sớm hơn; đoạn giữa hai ``t_end`` thêm vào ``sau_chay``
      (trung tính: không tính bắt, không tính báo nhầm).
    - ``sau_chay``, ``rac``: hợp của hai người.
    - ``tin_cay``: mức thấp hơn của hai người.
    - ``nguon_nhan``: ``nguoi:<ma_a>+<ma_b>``.
    """
    if so_sanh.can_phan_xu:
        return None
    a = chuan_hoa(nhan_a)
    b = chuan_hoa(nhan_b)
    evs, them_sau = [], []
    for i, j in so_sanh.cap_su_co:
        ea, eb = a["events"][i], b["events"][j]
        e: dict[str, Any] = {}
        for key in ("t_khoi", "t_lua"):
            vals = [v for v in (ea.get(key), eb.get(key)) if v is not None]
            e[key] = float(min(vals)) if vals else None
        ends = sorted(float(v) for v in (ea["t_end"], eb["t_end"]))
        e["t_end"] = ends[0]
        if ends[1] > ends[0]:
            them_sau.append((ends[0], ends[1]))
        e["t_start"] = min(v for v in (e["t_khoi"], e["t_lua"]) if v is not None)
        e["label"] = "fire" if e["t_lua"] is not None else "smoke"
        muc = [TIN_CAY.index(x) for x in (ea.get("tin_cay"), eb.get("tin_cay"))
               if x in TIN_CAY]
        e["tin_cay"] = TIN_CAY[min(muc)] if muc else "vua"
        evs.append({k: e[k] for k in ("t_start", "t_end", "label", "t_khoi",
                                      "t_lua", "tin_cay")})
    evs.sort(key=lambda e: e["t_start"])
    return {"schema": SCHEMA, "clip_id": a.get("clip_id") or b.get("clip_id"),
            "t0_goc": a.get("t0_goc", b.get("t0_goc", 0.0)), "events": evs,
            "sau_chay": [list(k) for k in _hop(a["sau_chay"] + b["sau_chay"]
                                               + them_sau)],
            "rac": [list(k) for k in _hop(a["rac"] + b["rac"])],
            "nguon_nhan": f"nguoi:{ma_a}+{ma_b}"}


@dataclass
class TongHop:
    """Chỉ số đồng thuận trên cả bộ file."""

    n_file: int
    kappa_giay: float
    kappa_giay_ci: tuple[float, float]
    kappa_co_su_co: float
    kappa_co_su_co_ci: tuple[float, float]
    bland_altman: dict[str, dict[str, float]]
    ma_tran_giay: np.ndarray
    n_phan_xu: int

    def dat_nguong(self) -> dict[str, bool]:
        """So với ngưỡng đề xuất (κ ≥ 0,8; trung vị |Δt| ≤ 1 s)."""
        out = {"kappa_giay": self.kappa_giay >= NGUONG_KAPPA,
               "kappa_co_su_co": self.kappa_co_su_co >= NGUONG_KAPPA}
        for key, ba in self.bland_altman.items():
            out[f"trung_vi_{key}"] = (ba["n"] > 0
                                      and ba["trung_vi_abs"] <= NGUONG_TRUNG_VI_DT)
        return out


def tong_hop(ds: list[SoSanhFile], so_lan: int = 2000, seed: int = 0) -> TongHop:
    """Gộp các ``SoSanhFile``: κ mỗi giây, κ "có sự cố", Bland–Altman từng mốc.

    Khoảng 95 % của κ: bootstrap phân vị theo file (``kappa_bootstrap``). κ "có
    sự cố" coi mỗi file là một quan sát nhị phân.
    """
    cap = [(s.giay_a, s.giay_b) for s in ds]
    a_all = np.concatenate([c[0] for c in cap]) if cap else np.zeros(0, int)
    b_all = np.concatenate([c[1] for c in cap]) if cap else np.zeros(0, int)
    co = [(np.array([s.co_a]), np.array([s.co_b])) for s in ds]
    ba = {}
    for key in MOC:
        xs = [r["a"] for s in ds for r in s.lech_moc if r["moc"] == key and "dt" in r]
        ys = [r["b"] for s in ds for r in s.lech_moc if r["moc"] == key and "dt" in r]
        ba[key] = bland_altman(xs, ys)
    return TongHop(
        n_file=len(ds),
        kappa_giay=cohen_kappa(a_all, b_all, len(LOP)),
        kappa_giay_ci=kappa_bootstrap(cap, so_lan, seed),
        kappa_co_su_co=cohen_kappa([s.co_a for s in ds], [s.co_b for s in ds], 2),
        kappa_co_su_co_ci=kappa_bootstrap(co, so_lan, seed, k=2),
        bland_altman=ba,
        ma_tran_giay=ma_tran_nham(a_all, b_all),
        n_phan_xu=sum(s.can_phan_xu for s in ds))
