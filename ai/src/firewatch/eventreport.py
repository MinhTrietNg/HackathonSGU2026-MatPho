"""Markdown section with the protocol v2 metrics (used by ``eval_events.py``).

:func:`metrics_v2_md` takes outcomes per model for ONE set of files; to
report per tier, call it once per subset of files (filter the outcomes with
the metadata), never on a pooled set alone.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from .claims import Margins, fa_paired, verdict_all, verdict_pair
from .eventmetrics import (ClipOutcome, FASummary, Meta, Proportion,
                           ScoringConfig, fa_by_stratum, fa_summary,
                           incident_flags, measure_names, prefire_summary,
                           review_list, sensitivity_summary, ttd_censored,
                           ttd_common)
from .noninferiority import (PairedCounts, mcnemar_one_sided, newcombe_ci,
                             tango_ci)
from .stats import ClusterRate

NOT_ESTIMABLE = "không ước lượng được"


def _f(x: float, nd: int = 1) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) \
        else ("∞" if math.isinf(x) else f"{x:.{nd}f}")


def _prop(p: Proportion) -> str:
    if not p.n:
        return "0/0"
    return f"{p.k}/{p.n} = {100 * p.rate:.0f} % [{100 * p.low:.0f}–{100 * p.high:.0f}]"


def _cluster(c: ClusterRate) -> str:
    if not c.estimable:
        return f"{NOT_ESTIMABLE} ({c.n_clusters_with_events}/{c.n_clusters} cụm có FA)"
    extra = ""
    if c.method == "negbin" and c.dispersion_k is not None:
        cv = 0.0 if math.isinf(c.dispersion_k) else 1 / math.sqrt(c.dispersion_k)
        extra = f", c≈{cv:.1f}"
    return (f"[{_f(c.lo, 2)}–{_f(c.hi, 2)}] ({c.n_clusters_with_events}/"
            f"{c.n_clusters} cụm có FA{extra})")


def _fa_row(name: str, s: FASummary) -> str:
    return (f"| {name} | {s.files} | {_f(s.hours, 2)} | {s.episodes} | "
            f"{_f(s.rate, 2)} | [{_f(s.poisson[0], 2)}–{_f(s.poisson[1], 2)}] | "
            f"{_cluster(s.bootstrap)} | {_cluster(s.negbin)} | {_prop(s.sources)} | "
            f"{s.raw_alerts} |")


FA_HEAD = ["| Model | File | Giờ | Đợt FA | Đợt/giờ | Poisson [95 %] | "
           "Bootstrap theo cụm [95 %] | Negative binomial [95 %] | "
           "Video gốc có ≥ 1 FA [Wilson] | Alert thô (đơn vị v1) |",
           "|---|---|---|---|---|---|---|---|---|---|"]


def metrics_v2_md(outcomes_by_model: Mapping[str, Sequence[ClipOutcome]],
                  meta: Meta | None = None, cfg: ScoringConfig = ScoringConfig(),
                  margins: Margins | None = None, ours: str | None = None,
                  cluster_key: str = "camera_vat_ly",
                  source_key: str = "nhom_nguon", stratum_key: str = "loai_am",
                  measure: str = "at_60", title: str = "Thước đo giao thức v2",
                  max_review_rows: int = 60) -> list[str]:
    """Markdown lines of every v2 metric for one set of files.

    Parameters
    ----------
    outcomes_by_model : mapping
        Model -> :class:`ClipOutcome` list, same files in the same order.
    meta : mapping, optional
        File metadata (``camera_vat_ly``, ``nhom_nguon``, ``loai_am``).
    cfg : ScoringConfig
    margins : Margins, optional
        When given with ``ours``, the decision rule is applied.
    ours : str, optional
        Our model's name (compared with every other model).
    measure : str
        Primary sensitivity measure for the paired tests.
    """
    names = list(outcomes_by_model)
    tol_names = measure_names(cfg)
    md = ["", f"## {title}", "",
          f"Quy tắc: tín hiệu = mọi lần CONFIRMED/RECONFIRMED và mọi alert; tín hiệu "
          f"trong [t_start − {cfg.early_s:g}, t_start) tính bắt (TTD ≤ 0, vào danh "
          f"sách xem mắt); tín hiệu trong `sau_chay` không tính bắt và không tính "
          f"FA; `rac` bị bỏ khỏi chấm và khỏi giờ âm. FA đếm theo đợt (CONFIRMED "
          f"đầu của track + RECONFIRMED). Cụm cho khoảng FA: `{cluster_key}`. "
          "Các file cùng `nhom_su_co` tính là một sự cố. "
          "Khoảng tỷ lệ là Wilson 95 %.", "",
          "### Độ nhạy theo sự cố", "",
          "| Model | " + " | ".join(tol_names) + " | bắt trước mốc (TTD < 0) |",
          "|---|" + "---|" * (len(tol_names) + 1)]
    for m in names:
        s = sensitivity_summary(outcomes_by_model[m], cfg, meta)
        md.append(f"| {m} | " + " | ".join(_prop(s[t]) for t in tol_names)
                  + f" | {s['early_hits'].k} |")
    md += ["", f"`tol_X`: cửa sổ [t_start − {cfg.early_s:g}, t_end + X]; "
           f"`at_{cfg.horizon_s:g}`: [t_start − {cfg.early_s:g}, min(t_start + "
           f"{cfg.horizon_s:g}, t_end + {cfg.main_tolerance_s:g})]; `early_phase`: "
           f"chỉ sự cố có t_lua − t_khoi ≥ {cfg.min_smoke_phase_s:g} s, bắt trước "
           "t_lua.", "", "### Báo nhầm theo đợt trên file âm", ""] + FA_HEAD
    fallback = 0
    for m in names:
        s = fa_summary(outcomes_by_model[m], meta, cluster_key, source_key)
        fallback = max(fallback, s.clusters_from_fallback)
        md.append(_fa_row(m, s))
    if fallback:
        md += ["", f"**Cảnh báo:** {fallback} file âm thiếu `{cluster_key}`; cụm của "
               f"chúng lấy theo `{source_key}` (hoặc chính file)."]
    md += ["", f"### Báo nhầm theo `{stratum_key}`", ""] + FA_HEAD
    for m in names:
        for k, s in fa_by_stratum(outcomes_by_model[m], meta, stratum_key,
                                  cluster_key=cluster_key,
                                  source_key=source_key).items():
            md.append(_fa_row(f"{m} / {k}", s))
    md += ["", "### FA trước sự cố (phần trước cháy của file dương)", ""] + FA_HEAD
    for m in names:
        md.append(_fa_row(m, prefire_summary(outcomes_by_model[m], meta,
                                              cluster_key, source_key)))
    md += ["", f"### TTD (t_start ≥ {cfg.min_ttd_start_s:g} s, dung sai "
           f"{cfg.main_tolerance_s:g} s)", "",
           "Phân bố có kiểm duyệt (sự cố SÓT kiểm duyệt ở cuối cửa sổ; Kaplan–Meier, "
           "`n/a` = đường cong không đạt phân vị đó):", "",
           "| Model | Sự cố | Bắt | Kiểm duyệt | P25 | Trung vị | P75 |",
           "|---|---|---|---|---|---|---|"]
    for m in names:
        c = ttd_censored(outcomes_by_model[m], cfg)
        md.append(f"| {m} | {c.n} | {c.detected} | {c.censored} | "
                  + " | ".join(_f(c.quantiles[q]) for q in (0.25, 0.5, 0.75)) + " |")
    if len(names) >= 2:
        md += ["", "TTD trên giao các sự cố cả hai model cùng bắt "
               "(`statistics.median`):", "",
               "| A | B | Sự cố chung | Trung vị A (s) | Trung vị B (s) |",
               "|---|---|---|---|---|"]
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                t = ttd_common(outcomes_by_model, cfg, (a, b))
                md.append(f"| {a} | {b} | {t.n} | {_f(t.median[a])} | "
                          f"{_f(t.median[b])} |")
        md += ["", f"### So sánh cặp ({measure}; FA theo cụm `{cluster_key}`)", "",
               "Khoảng 95 % hai phía của chênh độ nhạy ghép cặp (A − B): Tango "
               "(chính) và Newcombe (đối chiếu). p McNemar một phía cho 'A bắt "
               "nhiều hơn'. Chưa áp biên δ: biên do chủ repo chốt.", "",
               "| A | B | Chỉ A | Chỉ B | Δ | Tango [95 %] | Newcombe [95 %] | "
               "p McNemar (1 phía) | FA/giờ A − B [95 %] |",
               "|---|---|---|---|---|---|---|---|---|"]
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                fa_ = incident_flags(outcomes_by_model[a], measure, meta)
                fb_ = incident_flags(outcomes_by_model[b], measure, meta)
                keys = sorted(set(fa_) & set(fb_))
                pc = PairedCounts.from_flags([fa_[k] for k in keys],
                                             [fb_[k] for k in keys])
                tl, th = tango_ci(pc.only_a, pc.only_b, pc.n)
                nl, nh = newcombe_ci(pc)
                d = fa_paired(outcomes_by_model[a], outcomes_by_model[b], meta,
                              cluster_key, source_key)
                fa_txt = (f"{d.diff:+.2f} [{d.low:+.2f}; {d.high:+.2f}]"
                          if d.estimable else f"{_f(d.diff, 2)} ({NOT_ESTIMABLE}, "
                          f"{d.n_clusters_with_events} cụm có FA)")
                md.append(f"| {a} | {b} | {pc.only_a} | {pc.only_b} | "
                          f"{_f(pc.diff, 3)} | [{_f(tl, 3)}; {_f(th, 3)}] | "
                          f"[{_f(nl, 3)}; {_f(nh, 3)}] | "
                          f"{mcnemar_one_sided(pc.only_a, pc.only_b):.3f} | {fa_txt} |")
    if margins is not None and ours in outcomes_by_model and len(names) >= 2:
        pairs = [verdict_pair(outcomes_by_model[ours], outcomes_by_model[n], n,
                              margins, meta, measure, cluster_key, source_key)
                 for n in names if n != ours]
        field = verdict_all(pairs, margins.alpha)
        md += ["", f"### Kết luận theo giao thức v2 (δ_S = {margins.delta_s:g}, "
               f"δ_F = {margins.delta_f:g}/giờ, {ours} so với từng model)", "",
               "| Đối thủ | NI độ nhạy | NI FA (cách) | Hơn S | Hơn F | Kết luận |",
               "|---|---|---|---|---|---|"]
        for p in pairs:
            md.append(f"| {p.competitor} | {'đạt' if p.ni_s else 'không'} | "
                      f"{'đạt' if p.ni_f else 'không'} ({p.fa_rule}) | "
                      f"{'có' if p.sup_s else 'không'} | "
                      f"{'có' if p.sup_f else 'không'} | {p.label} |")
        md += ["", f"- Không kém mọi đối thủ (intersection–union): "
               f"{'ĐẠT' if field.not_worse_all else 'KHÔNG ĐẠT'}",
               f"- Hàng đầu (tốt hơn từng đối thủ, intersection–union): "
               f"{'ĐẠT' if field.leading else 'KHÔNG ĐẠT'}",
               "- Kết luận riêng được phép nói (Holm trên mọi cặp × chỉ số): "
               + (", ".join(k for k, v in field.holm_claims.items() if v[2])
                  or "không có")]
    rows = review_list(outcomes_by_model)
    md += ["", f"### Danh sách xem mắt ({len(rows)} dòng)", ""]
    if rows:
        md += ["| Model | Clip | Sự cố | t_start | Tín hiệu (s) | Loại | Lý do |",
               "|---|---|---|---|---|---|---|"]
        for r in rows[:max_review_rows]:
            md.append(f"| {r['model']} | {r['clip']} | {r['su_co']} | {r['t_start']} | "
                      f"{r['ts']:.1f} | {r['kind']} | {r['ly_do']} |")
        if len(rows) > max_review_rows:
            md.append(f"| … | còn {len(rows) - max_review_rows} dòng | | | | | |")
    return md
