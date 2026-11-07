"""Report tiers of the T1-dev test set and per-tier scoring tables.

T1 mixes very different material (fixed Vietnamese surveillance cameras,
foreign fixed cameras, news and hand-held footage), so a single pooled
number hides what is being measured. Every file of the set therefore carries
a tier and flags (``files.csv`` of the set, written by
``scripts/build_t1_dev.py``):

* ``tang``: ``A`` (Vietnam + fixed camera), ``B`` (fixed camera outside
  Vietnam with the onset inside the file), ``C`` (everything else with an
  incident: news, hand-held, fixed camera without onset), ``am`` (no
  incident). See :func:`assign_tier`; the attributes are defined before the
  files were assigned (``reports``/protocol of the set).
* ``mu``: no model has ever been run on the file.
* ``fa_da_chan_doan``: negative files whose false alarms were already
  diagnosed by the team (reported with and without them).
* ``ro_ri``: training-data tags (``fasdd``, ``matpho_v0.4``...) known to
  contain the scene; a model trained on such data is scored without it.
* ``cham_duoc_voting``: the longest continuous scene inside the scoring
  window lasts at least ``k_enter`` heartbeats and (for incidents) the window
  holds at least 15 heartbeats; otherwise voting cannot confirm by
  construction and the file measures scene length, not the detector.

The scoring itself reuses :func:`firewatch.evalkit.clip_outcomes` and the
intervals of :mod:`firewatch.stats`. New measures plug in through the
``caught_fn`` / ``fa_fn`` arguments of :func:`sens_cell` and
:func:`fa_cell` without touching this module.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .evalkit import ClipResult, clip_outcomes
from .stats import cluster_bootstrap_rate, mcnemar_exact, paired_bootstrap_diff, wilson

TIERS = ("A", "B", "C", "am")
FILES_COLUMNS = ("file", "clip_id", "nhom_nguon", "camera_vat_ly", "nhom_su_co",
                 "duong", "tang", "loai_am", "mu", "fa_da_chan_doan", "ro_ri",
                 "ngoai_fa_chinh", "cham_duoc_voting", "canh_dai_nhat_s",
                 "nguon_nhan")
MIN_HEARTBEATS = 15
NO_CONCLUSION = "gộp, không dùng để kết luận"
LEAK_NOTE = "Rò rỉ với dữ liệu train đối thủ: CHƯA KIỂM."

CaughtFn = Callable[[ClipResult, float], list[bool]]
FaFn = Callable[[ClipResult, float], tuple[float, float]]


# ------------------------------------------------------------------ file table
@dataclass(frozen=True)
class FileRow:
    """One row of ``files.csv`` (only the fields the scoring needs)."""

    file: str
    clip_id: str
    nhom_nguon: str
    camera_vat_ly: str
    nhom_su_co: str
    duong: bool
    tang: str
    loai_am: str
    mu: bool
    fa_da_chan_doan: bool
    ro_ri: frozenset[str]
    ngoai_fa_chinh: bool
    cham_duoc_voting: bool
    canh_dai_nhat_s: float | None
    nguon_nhan: str
    da_chay_boi: frozenset[str] = frozenset()
    loai_khoi_bo_chinh: bool = False
    thu_thach: frozenset[str] = frozenset()

    @property
    def cluster(self) -> str:
        """Independence unit for bootstraps: physical camera, else source."""
        return self.camera_vat_ly or self.nhom_nguon or self.file

    @property
    def incident(self) -> str:
        """Incident unit: files of one incident count once."""
        return self.nhom_su_co or self.clip_id or self.file


def parse_tags(text: str | None) -> frozenset[str]:
    """Tags separated by ``;`` (blank entries dropped)."""
    return frozenset(t.strip() for t in (text or "").split(";") if t.strip())


def _flag(text: str | None) -> bool:
    return str(text or "").strip() in ("1", "true", "True", "co")


def read_files_csv(path: Path) -> dict[str, FileRow]:
    """Read ``files.csv`` of a T1-dev set, keyed by file stem.

    Parameters
    ----------
    path : Path
        CSV with at least the columns of :data:`FILES_COLUMNS`.

    Returns
    -------
    dict
        File stem -> :class:`FileRow`.

    Raises
    ------
    ValueError
        When a required column is missing or a tier is unknown.
    """
    with Path(path).open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in FILES_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: thiếu cột {missing}")
        out: dict[str, FileRow] = {}
        for r in reader:
            if r["tang"] not in TIERS:
                raise ValueError(f"{path}: tầng không hợp lệ {r['tang']!r} "
                                 f"({r['file']})")
            scene = r.get("canh_dai_nhat_s", "")
            out[r["file"]] = FileRow(
                file=r["file"], clip_id=r["clip_id"], nhom_nguon=r["nhom_nguon"],
                camera_vat_ly=r["camera_vat_ly"], nhom_su_co=r["nhom_su_co"],
                duong=_flag(r["duong"]), tang=r["tang"], loai_am=r["loai_am"],
                mu=_flag(r["mu"]), fa_da_chan_doan=_flag(r["fa_da_chan_doan"]),
                ro_ri=parse_tags(r["ro_ri"]), ngoai_fa_chinh=_flag(r["ngoai_fa_chinh"]),
                cham_duoc_voting=_flag(r["cham_duoc_voting"]),
                canh_dai_nhat_s=float(scene) if scene not in ("", None) else None,
                nguon_nhan=r["nguon_nhan"],
                da_chay_boi=parse_tags(r.get("da_chay_boi")),
                loai_khoi_bo_chinh=_flag(r.get("loai_khoi_bo_chinh")),
                thu_thach=parse_tags(r.get("thu_thach")))
    return out


# --------------------------------------------------------- tier assignment
def assign_tier(duong: bool, quoc_gia: str, camera_co_dinh: bool,
                co_pha_khoi_phat: bool) -> str:
    """Tier of one file from attributes defined before the assignment.

    Parameters
    ----------
    duong : bool
        The file contains an incident.
    quoc_gia : str
        Country code of the catalog (``vn`` for Vietnam).
    camera_co_dinh : bool
        Recording of one surveillance camera that does not move and is not
        cut inside the scoring window.
    co_pha_khoi_phat : bool
        The file starts before the first visible smoke or fire.

    Returns
    -------
    str
        ``A``, ``B``, ``C`` or ``am``.
    """
    if not duong:
        return "am"
    if camera_co_dinh and quoc_gia == "vn":
        return "A"
    if camera_co_dinh and co_pha_khoi_phat:
        return "B"
    return "C"


def scoring_window(t_start: float, t_end: float | None, duration_s: float,
                   tolerance_s: float) -> tuple[float, float]:
    """``[t_start, min(t_end + tolerance, duration)]`` of one incident."""
    end = duration_s if t_end is None else t_end + tolerance_s
    return t_start, min(end, duration_s)


def heartbeats_in(t0: float, t1: float, duration_s: float,
                  interval_s: float = 1.0) -> int:
    """Heartbeats (grid ``0, T, 2T...`` before the last frame) in ``[t0, t1]``."""
    if t1 < t0 or duration_s <= 0:
        return 0
    last = min(t1, duration_s - 1e-6)
    first_k = math.ceil(t0 / interval_s - 1e-9)
    last_k = math.floor(last / interval_s + 1e-9)
    return max(0, last_k - first_k + 1)


def longest_scene(cuts: Iterable[float], t0: float, t1: float) -> float:
    """Longest stretch of ``[t0, t1]`` without a scene cut, seconds."""
    if t1 <= t0:
        return 0.0
    edges = [t0] + sorted(c for c in cuts if t0 < c < t1) + [t1]
    return max(b - a for a, b in zip(edges, edges[1:]))


def voting_scorable(longest_s: float, n_heartbeats: int, positive: bool,
                    min_scene_s: float, min_heartbeats: int = MIN_HEARTBEATS
                    ) -> bool:
    """Whether voting can confirm on this file at all.

    Parameters
    ----------
    longest_s : float
        Longest continuous scene inside the scoring window (whole file for a
        negative file).
    n_heartbeats : int
        Heartbeats inside the scoring window.
    positive : bool
        The file has an incident; the heartbeat floor only applies then.
    min_scene_s : float
        ``k_enter * interval_s`` of the voting configuration.
    min_heartbeats : int
        Floor on heartbeats inside the window (15 by default).
    """
    if longest_s < min_scene_s:
        return False
    return not (positive and n_heartbeats < min_heartbeats)


# ------------------------------------------------------------------ subsets
@dataclass(frozen=True)
class Subset:
    """One row of the tier table.

    ``pos`` selects the incident files scored for sensitivity and ``neg``
    the negative files scored for false alarms (``None``: not reported).
    ``ket_luan`` is False for pooled rows that must not support a claim.
    """

    key: str
    title: str
    pos: Callable[[FileRow], bool] | None
    neg: Callable[[FileRow], bool] | None
    ket_luan: bool = True


def _tier(t: str) -> Callable[[FileRow], bool]:
    return (lambda f: f.duong and f.tang == t and f.cham_duoc_voting
            and not f.loai_khoi_bo_chinh)


def standard_subsets() -> list[Subset]:
    """Rows printed for every model (order of the report)."""
    main_neg = (lambda f: not f.duong and not f.ngoai_fa_chinh
                and f.cham_duoc_voting)
    return [
        Subset("A", "Tầng A — VN, camera cố định", _tier("A"), None),
        Subset("B", "Tầng B — camera cố định ngoài VN, có pha khởi phát",
               _tier("B"), None),
        Subset("C", "Tầng C — tin tức / quay tay / không có pha khởi phát",
               _tier("C"), None),
        Subset("am", "Âm — FA chính", None, main_neg),
        Subset("am_bt", "Âm FA chính — loại bt", None,
               lambda f: main_neg(f) and f.loai_am == "bt"),
        Subset("am_dn", "Âm FA chính — loại dn", None,
               lambda f: main_neg(f) and f.loai_am == "dn"),
        Subset("am_bo_lks", "Âm FA chính bỏ file lửa có kiểm soát", None,
               lambda f: main_neg(f) and "lua_kiem_soat" not in f.thu_thach),
        Subset("am_bo_cd", "Âm FA chính bỏ clip FA đã chẩn đoán", None,
               lambda f: main_neg(f) and not f.fa_da_chan_doan),
        Subset("mu", "T1-mù (chưa model nào chạy)",
               lambda f: f.duong and f.mu and f.cham_duoc_voting
               and not f.loai_khoi_bo_chinh,
               lambda f: not f.duong and f.mu),
        Subset("khong_cham", "Không chấm được bằng voting (tham khảo)",
               lambda f: f.duong and not f.cham_duoc_voting,
               lambda f: not f.duong and not f.cham_duoc_voting, False),
        Subset("ngoai_bo_chinh", "Dương ngoài bộ chính (tham khảo)",
               lambda f: f.duong and f.loai_khoi_bo_chinh, None, False),
        Subset("ngoai_fa", "Âm ngoài FA chính (tham khảo)", None,
               lambda f: not f.duong and f.ngoai_fa_chinh, False),
        Subset("gop", f"Toàn bộ — {NO_CONCLUSION}", lambda f: f.duong,
               lambda f: not f.duong, False),
    ]


def leaked(f: FileRow, train_tags: frozenset[str]) -> bool:
    """The file's scene is in the training data of a model with these tags."""
    return bool(f.ro_ri & train_tags)


def main_tier(tang: str, loai_khoi_bo_chinh: str | bool) -> str:
    """Tier of a file inside the main set, empty when it is outside.

    Parameters
    ----------
    tang : str
        Column ``tang`` of ``files.csv`` (``A``, ``B``, ``C`` or ``am``).
    loai_khoi_bo_chinh : str or bool
        Column ``loai_khoi_bo_chinh`` (``"1"`` = outside the main set).

    Returns
    -------
    str
        ``tang`` or ``""``; the same rule as the tier rows of
        :func:`standard_subsets`, so counting ``tang_chinh`` never puts a
        file removed from the main set (e.g. 009_d2) in tier A.
    """
    return "" if _flag(str(loai_khoi_bo_chinh)) else tang


# ------------------------------------------------------------------ cells
def _default_caught(r: ClipResult, tol: float) -> list[bool]:
    return clip_outcomes(r, tol)[0]


def _default_fa(r: ClipResult, tol: float) -> tuple[float, float]:
    return float(clip_outcomes(r, tol)[1]), r.duration_s / 3600


def sens_cell(results: Sequence[ClipResult], files: dict[str, FileRow],
              pred: Callable[[FileRow], bool], tol: float,
              exclude: Callable[[FileRow], bool] | None = None,
              caught_fn: CaughtFn | None = None) -> dict:
    """Sensitivity on the incidents selected by ``pred``.

    Files of one incident (same ``nhom_su_co``) count once: caught when any
    of them is caught.

    Returns
    -------
    dict
        ``k``, ``n``, ``ci`` (Wilson 95 %), ``caught`` (incident -> bool).
    """
    caught_fn = caught_fn or _default_caught
    per: dict[str, bool] = {}
    for r in results:
        f = files.get(r.clip)
        if f is None or not pred(f) or (exclude and exclude(f)):
            continue
        hit = any(caught_fn(r, tol))
        per[f.incident] = per.get(f.incident, False) or hit
    k, n = sum(per.values()), len(per)
    return {"k": k, "n": n, "ci": wilson(k, n), "caught": per}


def fa_cell(results: Sequence[ClipResult], files: dict[str, FileRow],
            pred: Callable[[FileRow], bool], tol: float,
            fa_fn: FaFn | None = None) -> dict:
    """False alarms per hour on the negative files selected by ``pred``.

    The interval is a cluster bootstrap over physical cameras; with two or
    fewer cameras that have a false alarm it is reported as not estimable.

    Returns
    -------
    dict
        ``fa``, ``hours``, ``rate``, ``ci``, ``n_files``, ``n_cam``,
        ``n_cam_fa``, ``estimable`` and the per-file lists used for paired
        comparisons (``files``, ``counts``, ``hours_list``, ``groups``).
    """
    fa_fn = fa_fn or _default_fa
    names, counts, hours, groups = [], [], [], []
    for r in sorted(results, key=lambda r: r.clip):
        f = files.get(r.clip)
        if f is None or not pred(f):
            continue
        c, h = fa_fn(r, tol)
        names.append(r.clip)
        counts.append(c)
        hours.append(h)
        groups.append(f.cluster)
    tot_h = sum(hours)
    cams_fa = {g for g, c in zip(groups, counts) if c > 0}
    estimable = len(cams_fa) > 2
    ci = (cluster_bootstrap_rate(counts, hours, groups) if estimable and groups
          else (float("nan"), float("nan")))
    src: dict[str, bool] = {}
    for n_, c in zip(names, counts):
        key = files[n_].nhom_nguon or n_
        src[key] = src.get(key, False) or c > 0
    return {"fa": sum(counts), "hours": tot_h, "src_k": sum(src.values()),
            "src_n": len(src),
            "rate": sum(counts) / tot_h if tot_h else float("nan"), "ci": ci,
            "n_files": len(names), "n_cam": len(set(groups)),
            "n_cam_fa": len(cams_fa), "estimable": estimable, "files": names,
            "counts": counts, "hours_list": hours, "groups": groups}


def paired_cell(a: dict, b: dict) -> dict:
    """McNemar on two sensitivity cells over their common incidents."""
    common = sorted(set(a["caught"]) & set(b["caught"]))
    only_a = sum(a["caught"][i] and not b["caught"][i] for i in common)
    only_b = sum(b["caught"][i] and not a["caught"][i] for i in common)
    return {"n": len(common), "only_a": only_a, "only_b": only_b,
            "p": mcnemar_exact(only_a, only_b)}


def paired_fa(a: dict, b: dict) -> tuple[float, float, float]:
    """Paired bootstrap of ``rate(b) - rate(a)`` by camera, same files."""
    if a["files"] != b["files"] or not a["files"]:
        return float("nan"), float("nan"), float("nan")
    return paired_bootstrap_diff(b["counts"], a["counts"], a["hours_list"],
                                 a["groups"])


# ------------------------------------------------------------------ tables
def _pct(k: int, n: int, ci: tuple[float, float]) -> str:
    if not n:
        return "– (n = 0)"
    return f"{k}/{n} [{100 * ci[0]:.0f}–{100 * ci[1]:.0f} %]"


def _rate(c: dict) -> str:
    if not c["n_files"]:
        return "– (0 file)"
    base = f"{c['fa']:g} / {c['hours']:.2f} h = {c['rate']:.2f}"
    lo, hi = wilson(c["src_k"], c["src_n"])
    src = (f"; video gốc có FA {c['src_k']}/{c['src_n']} "
           f"[{100 * lo:.0f}–{100 * hi:.0f} %]")
    if c["estimable"]:
        return base + f" [{c['ci'][0]:.2f}–{c['ci'][1]:.2f}]" + src
    return base + f" [không ước lượng được: {c['n_cam_fa']} camera có FA]" + src


def _pick(fn, model: str):
    """A hook given for every model, or a mapping model -> hook."""
    return fn.get(model) if isinstance(fn, dict) else fn


def tier_table(per_model: dict[str, Sequence[ClipResult]],
               files: dict[str, FileRow], tol: float,
               train_tags: dict[str, frozenset[str]] | None = None,
               subsets: list[Subset] | None = None,
               caught_fn: CaughtFn | None = None,
               fa_fn: FaFn | None = None) -> tuple[list[str], dict]:
    """Markdown tables by tier for every model, plus the raw cells.

    Parameters
    ----------
    per_model : dict
        Model name -> clip results on the files of ``files``.
    files : dict
        ``files.csv`` rows by file stem.
    tol : float
        Tolerance after the incident window, seconds.
    train_tags : dict, optional
        Model name -> training-data tags; files whose ``ro_ri`` meets them
        are dropped for that model (rows "bỏ rò rỉ").
    subsets : list of Subset, optional
        Rows; :func:`standard_subsets` by default.
    caught_fn, fa_fn : callable, optional
        Hooks for other measures (see :func:`sens_cell`, :func:`fa_cell`).

    Returns
    -------
    tuple
        ``(lines, cells)`` where ``cells[model][subset_key]`` holds the
        ``sens`` and ``fa`` dicts.
    """
    subsets = subsets or standard_subsets()
    train_tags = train_tags or {}
    models = list(per_model)
    cells: dict[str, dict[str, dict]] = {m: {} for m in models}
    md = ["| Tầng | " + " | ".join(f"{m}: bắt [Wilson 95 %]" for m in models)
          + " | " + " | ".join(f"{m}: FA / giờ âm = FA/giờ [bootstrap camera 95 %]"
                               for m in models) + " | Dùng kết luận |",
          "|---|" + "---|" * (2 * len(models)) + "---|"]
    for s in subsets:
        row_s, row_f = [], []
        for m in models:
            res = per_model[m]
            sens = (sens_cell(res, files, s.pos, tol, caught_fn=_pick(caught_fn, m))
                    if s.pos else None)
            fa = (fa_cell(res, files, s.neg, tol, fa_fn=_pick(fa_fn, m))
                  if s.neg else None)
            cells[m][s.key] = {"sens": sens, "fa": fa}
            row_s.append(_pct(sens["k"], sens["n"], sens["ci"]) if sens else "")
            row_f.append(_rate(fa) if fa else "")
        md.append(f"| {s.title} | " + " | ".join(row_s) + " | " + " | ".join(row_f)
                  + f" | {'có' if s.ket_luan else 'KHÔNG'} |")
    md += ["", "Bỏ file rò rỉ theo từng model (`ro_ri` giao nguồn train của model):",
           "", "| Tầng | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    for t in ("A", "B", "C"):
        row = []
        for m in models:
            tags = train_tags.get(m, frozenset())
            c = sens_cell(per_model[m], files, _tier(t), tol,
                          exclude=lambda f, tg=tags: leaked(f, tg),
                          caught_fn=_pick(caught_fn, m))
            cells[m][f"{t}_bo_ro_ri"] = {"sens": c, "fa": None}
            tag_txt = ",".join(sorted(tags)) or "không khai báo"
            row.append(_pct(c["k"], c["n"], c["ci"]) + f" (nguồn train: {tag_txt})")
        md.append(f"| Tầng {t} bỏ rò rỉ | " + " | ".join(row) + " |")
    md += ["", LEAK_NOTE]
    return md, cells


def paired_table(cells: dict, base: str, cand: str,
                 subsets: list[Subset] | None = None) -> list[str]:
    """Markdown: paired comparison of two models on every subset."""
    subsets = subsets or standard_subsets()
    md = [f"| Tầng | Sự cố chung | Chỉ {base} | Chỉ {cand} | p McNemar | "
          f"FA/giờ ({cand} − {base}) [bootstrap camera 95 %] | Dùng kết luận |",
          "|---|---|---|---|---|---|---|"]
    for s in subsets:
        a, b = cells[base].get(s.key), cells[cand].get(s.key)
        if a is None or b is None:
            continue
        sens = "| – | – | – | – "
        if a["sens"] and b["sens"]:
            p = paired_cell(a["sens"], b["sens"])
            sens = f"| {p['n']} | {p['only_a']} | {p['only_b']} | {p['p']:.3f} "
        fa = "–"
        if a["fa"] and b["fa"]:
            d, lo, hi = paired_fa(a["fa"], b["fa"])
            fa = "–" if d != d else f"{d:+.2f} [{lo:+.2f}; {hi:+.2f}]"
        md.append(f"| {s.title} {sens}| {fa} | {'có' if s.ket_luan else 'KHÔNG'} |")
    md += ["", LEAK_NOTE]
    return md


# ------------------------------------------------------------ composition
def composition(files: dict[str, FileRow], durations: dict[str, float],
                subsets: list[Subset] | None = None) -> list[str]:
    """Markdown composition table: files, incidents, negative hours, cameras.

    Parameters
    ----------
    files : dict
        ``files.csv`` rows.
    durations : dict
        File stem -> seconds counted as negative time (duration minus
        ``rac``) for negative files; ignored for incident files.
    subsets : list of Subset, optional
        Rows; :func:`standard_subsets` by default.
    """
    subsets = subsets or standard_subsets()
    rows = list(files.values())
    n_inc_all = len({f.incident for f in rows if f.duong})
    md = ["| Tầng | File dương | Sự cố (tỷ lệ trên mọi sự cố) [Wilson 95 %] | "
          "Camera/nguồn dương | File âm | Giờ âm | Camera âm | Dùng kết luận |",
          "|---|---|---|---|---|---|---|---|"]
    for s in subsets:
        pos = [f for f in rows if s.pos and s.pos(f)]
        neg = [f for f in rows if s.neg and s.neg(f)]
        inc = {f.incident for f in pos}
        k = len(inc)
        lo, hi = wilson(k, n_inc_all) if s.pos else (float("nan"),) * 2
        inc_txt = (f"{k} ({k}/{n_inc_all} [{100 * lo:.0f}–{100 * hi:.0f} %])"
                   if s.pos else "")
        hours = sum(durations.get(f.file, 0.0) for f in neg) / 3600
        md.append(f"| {s.title} | {len(pos) if s.pos else ''} | {inc_txt} | "
                  f"{len({f.cluster for f in pos}) if s.pos else ''} | "
                  f"{len(neg) if s.neg else ''} | "
                  f"{f'{hours:.3f}' if s.neg else ''} | "
                  f"{len({f.cluster for f in neg}) if s.neg else ''} | "
                  f"{'có' if s.ket_luan else 'KHÔNG'} |")
    md += ["", LEAK_NOTE]
    return md
