"""Pure-Python building blocks for the eval harness (unit-tested, no model).

* clip-level stratified split (``allocate_split``)
* frame-level detection metrics: greedy IoU matching, AP@50, P/R/F1
* event-level scoring: time-to-detect, misses, false alarms per hour
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field

from .voting import Box, iou

CLASSES = ("fire", "smoke")


# ------------------------------------------------------------------ splitting
def allocate_split(n: int, ratios: tuple[float, float, float]) -> list[int]:
    """Return how many items go to train/val/test for one stratum of ``n``.

    Largest-remainder rounding; train always gets at least one item when
    ``n >= 1`` so tiny strata never end up with an empty train set.
    """
    if n <= 0:
        return [0, 0, 0]
    raw = [n * r for r in ratios]
    counts = [int(x) for x in raw]
    remainder = n - sum(counts)
    order = sorted(range(3), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in order[:remainder]:
        counts[i] += 1
    if counts[0] == 0:
        donor = max(range(1, 3), key=lambda i: counts[i])
        counts[donor] -= 1
        counts[0] += 1
    return counts


def stratified_clip_split(items: list[tuple[str, str]],
                          ratios: tuple[float, float, float],
                          seed: int) -> dict[str, str]:
    """Assign each ``(clip_id, stratum)`` to ``train``/``val``/``test``.

    Parameters
    ----------
    items : list of (clip_id, stratum)
        Stratum is e.g. ``"HAM/pos"``. Splitting is per clip, never per frame.
    """
    rng = random.Random(seed)
    by_stratum: dict[str, list[str]] = defaultdict(list)
    for clip_id, stratum in items:
        by_stratum[stratum].append(clip_id)
    out: dict[str, str] = {}
    for stratum in sorted(by_stratum):
        clips = sorted(by_stratum[stratum])
        rng.shuffle(clips)
        n_train, n_val, _ = allocate_split(len(clips), ratios)
        for i, clip in enumerate(clips):
            if i < n_train:
                out[clip] = "train"
            else:
                out[clip] = "val" if i < n_train + n_val else "test"
    return out


# --------------------------------------------------------- frame-level metrics
@dataclass(slots=True)
class GTBox:
    cls: str
    box: Box


@dataclass(slots=True)
class PredBox:
    cls: str
    conf: float
    box: Box


def match_predictions(preds: list[PredBox], gts: list[GTBox], cls: str,
                      iou_thr: float = 0.5) -> list[tuple[float, bool]]:
    """Greedy match (highest conf first) for one image and one class.

    Returns
    -------
    list of (conf, is_true_positive)
        One entry per prediction of ``cls``.
    """
    gt_boxes = [g.box for g in gts if g.cls == cls]
    used = [False] * len(gt_boxes)
    out: list[tuple[float, bool]] = []
    for p in sorted((p for p in preds if p.cls == cls), key=lambda p: -p.conf):
        best, best_i = 0.0, -1
        for i, g in enumerate(gt_boxes):
            if used[i]:
                continue
            s = iou(p.box, g)
            if s > best:
                best, best_i = s, i
        if best >= iou_thr and best_i >= 0:
            used[best_i] = True
            out.append((p.conf, True))
        else:
            out.append((p.conf, False))
    return out


def average_precision(records: list[tuple[float, bool]], n_gt: int) -> float:
    """All-point interpolated AP from (conf, tp) records of one class."""
    if n_gt == 0:
        return 0.0
    records = sorted(records, key=lambda r: -r[0])
    tp = fp = 0
    precisions: list[float] = []
    recalls: list[float] = []
    for _, is_tp in records:
        tp += is_tp
        fp += not is_tp
        precisions.append(tp / (tp + fp))
        recalls.append(tp / n_gt)
    # Làm đơn điệu precision từ phải sang trái (một lượt) rồi tích phân theo recall.
    p_env = precisions[:]
    for i in range(len(p_env) - 2, -1, -1):
        p_env[i] = max(p_env[i], p_env[i + 1])
    ap, prev_r = 0.0, 0.0
    for r, p in zip(recalls, p_env):
        ap += (r - prev_r) * p
        prev_r = r
    return ap


def prf_at(records: list[tuple[float, bool]], n_gt: int,
           conf_thr: float) -> tuple[float, float, float]:
    """Precision, recall, F1 counting only predictions with conf ≥ ``conf_thr``."""
    kept = [tp for conf, tp in records if conf >= conf_thr]
    tp = sum(kept)
    fp = len(kept) - tp
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / n_gt if n_gt else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f1


@dataclass
class FrameMetrics:
    """Accumulates per-class records across images; ``group`` = context."""

    iou_thr: float = 0.5
    records: dict[str, list[tuple[float, bool]]] = field(
        default_factory=lambda: defaultdict(list))
    n_gt: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    n_images: int = 0

    def add(self, preds: list[PredBox], gts: list[GTBox]) -> None:
        self.n_images += 1
        for cls in CLASSES:
            self.n_gt[cls] += sum(1 for g in gts if g.cls == cls)
            self.records[cls].extend(match_predictions(preds, gts, cls, self.iou_thr))

    def summary(self, conf_thr: float) -> dict[str, dict[str, float]]:
        """Per class + ``all`` (mAP = mean AP over classes with GT)."""
        out: dict[str, dict[str, float]] = {}
        aps = []
        for cls in CLASSES:
            ap = average_precision(self.records[cls], self.n_gt[cls])
            p, r, f1 = prf_at(self.records[cls], self.n_gt[cls], conf_thr)
            out[cls] = {"ap50": ap, "precision": p, "recall": r, "f1": f1,
                        "n_gt": self.n_gt[cls],
                        "n_pred": sum(1 for c, _ in self.records[cls] if c >= conf_thr)}
            if self.n_gt[cls]:
                aps.append(ap)
        both = [rec for cls in CLASSES for rec in self.records[cls]]
        n_all = sum(self.n_gt.values())
        p, r, f1 = prf_at(both, n_all, conf_thr)
        out["all"] = {"ap50": sum(aps) / len(aps) if aps else 0.0, "precision": p,
                      "recall": r, "f1": f1, "n_gt": n_all,
                      "n_pred": sum(1 for c, _ in both if c >= conf_thr)}
        return out


# --------------------------------------------------------- event-level metrics
@dataclass(slots=True)
class GTEvent:
    t_start: float
    t_end: float | None = None


@dataclass(slots=True)
class ClipResult:
    clip: str
    positive: bool
    duration_s: float
    gt: list[GTEvent]
    alert_ts: list[float]


def merge_events(events: list[GTEvent]) -> list[GTEvent]:
    """Merge overlapping / touching GT windows (fire + smoke of one incident)."""
    out: list[GTEvent] = []
    for ev in sorted(events, key=lambda e: e.t_start):
        if out and ev.t_start <= (out[-1].t_end if out[-1].t_end is not None else 1e18):
            end_a, end_b = out[-1].t_end, ev.t_end
            out[-1].t_end = None if None in (end_a, end_b) else max(end_a, end_b)
        else:
            out.append(GTEvent(ev.t_start, ev.t_end))
    return out


def clip_outcomes(r: ClipResult, tolerance_s: float) -> tuple[list[bool], int]:
    """Per clip: caught flag of each merged incident, and false-alarm count.

    Same rules as :func:`score_events`: an incident is caught by an alert in
    ``[t_start, t_end + tolerance]``; any other alert is a false alarm.
    """
    windows = merge_events(r.gt)
    caught = []
    for w in windows:
        end = (w.t_end if w.t_end is not None else r.duration_s) + tolerance_s
        caught.append(any(w.t_start <= a <= end for a in r.alert_ts))
    fa = sum(not any(w.t_start <= a <= (w.t_end if w.t_end is not None
                                         else r.duration_s) + tolerance_s
                     for w in windows) for a in r.alert_ts)
    return caught, fa


def score_events(results: list[ClipResult], tolerance_s: float) -> dict[str, float]:
    """Time-to-detect, miss rate and false alarms per hour over clips.

    An incident is *caught* by the first alert with
    ``t_start <= alert <= t_end + tolerance``. Alerts outside every incident
    window (or on negative clips) are false alarms; FA/hour is normalised
    by the total duration of negative clips as the spec asks, with the
    all-clip rate given too.
    """
    incidents = caught = 0
    ttds: list[float] = []
    fa_neg = fa_pos = 0
    neg_hours = pos_hours = 0.0
    for r in results:
        if r.positive:
            pos_hours += r.duration_s / 3600
        else:
            neg_hours += r.duration_s / 3600
        windows = merge_events(r.gt)
        for w in windows:
            incidents += 1
            end = (w.t_end if w.t_end is not None else r.duration_s) + tolerance_s
            hits = [a for a in r.alert_ts if w.t_start <= a <= end]
            if hits:
                caught += 1
                ttds.append(min(hits) - w.t_start)
        for a in r.alert_ts:
            inside = any(w.t_start <= a <= (w.t_end if w.t_end is not None
                                             else r.duration_s) + tolerance_s
                         for w in windows)
            if not inside:
                if r.positive:
                    fa_pos += 1
                else:
                    fa_neg += 1
    ttds_sorted = sorted(ttds)
    median = ttds_sorted[len(ttds_sorted) // 2] if ttds_sorted else float("nan")
    return {
        "incidents": incidents,
        "caught": caught,
        "miss_rate": (incidents - caught) / incidents if incidents else float("nan"),
        "ttd_median_s": median,
        "ttd_mean_s": sum(ttds) / len(ttds) if ttds else float("nan"),
        "false_alarms_neg": fa_neg,
        "false_alarms_pos": fa_pos,
        "neg_hours": neg_hours,
        "fa_per_hour_neg": fa_neg / neg_hours if neg_hours else float("nan"),
        "fa_per_hour_all": (fa_neg + fa_pos) / (neg_hours + pos_hours)
        if (neg_hours + pos_hours) else float("nan"),
    }
