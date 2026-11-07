"""Build a mixed fine-tuning set from several labelled sources.

Every source is read into the same in-memory form (image path, list of
``fire``/``smoke`` boxes in normalised xywh, split group), then sampled per
*role* to hit target ratios and written out as one YOLO dataset with the
pipeline class order ``0 = fire, 1 = smoke``.

Roles
-----
``domain``
    Data from the project's own scene (parking lots, CCTV angle). Images
    with at least one fire/smoke box count as *domain positives*, empty ones
    as *domain negatives*. Domain positives are never sub-sampled.
``hard_neg``
    Only images that end up with no fire/smoke box are used (for example
    DFS images whose only boxes are the fire-like ``other`` class); they
    count toward the domain-negative budget.
``base``
    General fire/smoke data replayed so fine-tuning does not forget what
    the base model knew.

Class maps send each source class to ``fire``, ``smoke``, ``drop`` or
``skip``. Dropped boxes vanish and an image left without boxes becomes a
negative; ``skip`` removes the whole image, for classes whose labels are
not trustworthy enough to turn into either positives or negatives.
"""

from __future__ import annotations

import csv
import hashlib
import logging
import random
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

TARGET_CLASSES = ("fire", "smoke")
IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
ROLE_BUCKETS = ("pos_domain", "neg_domain", "base")


@dataclass(slots=True)
class Item:
    """One image ready to be written to the mixed set."""

    source: str
    image: Path
    boxes: list[tuple[str, float, float, float, float]]
    """(class, cx, cy, w, h), normalised to [0, 1]."""
    group: str
    bucket: str = ""
    label_status: str = "verified"
    clip: str = ""
    """Raw group key without namespace (clip name for video frames)."""

    @property
    def positive(self) -> bool:
        return bool(self.boxes)


@dataclass
class SourceStats:
    """What happened to one source while reading it."""

    images_seen: int = 0
    images_kept: int = 0
    images_no_label: int = 0
    images_skipped: int = 0
    """Whole images removed because they contain a ``skip`` class."""
    images_excluded: int = 0
    """Images removed by the audit (exclusions.csv)."""
    boxes_in: Counter = field(default_factory=Counter)
    boxes_out: Counter = field(default_factory=Counter)
    boxes_dropped: Counter = field(default_factory=Counter)
    unknown_classes: Counter = field(default_factory=Counter)


# ----------------------------------------------------------------- labels
def clip_box(cx: float, cy: float, w: float, h: float,
             ) -> tuple[float, float, float, float] | None:
    """Clip a normalised xywh box to the image; ``None`` if degenerate."""
    x1, y1 = max(0.0, cx - w / 2), max(0.0, cy - h / 2)
    x2, y2 = min(1.0, cx + w / 2), min(1.0, cy + h / 2)
    if x2 - x1 <= 1e-6 or y2 - y1 <= 1e-6:
        return None
    return (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1


def map_class(raw: str, class_map: dict[str, str], stats: SourceStats) -> str:
    """Return ``fire``/``smoke``/``drop``/``skip`` for a raw class id or name."""
    stats.boxes_in[raw] += 1
    target = class_map.get(raw, class_map.get(raw.lower()))
    if target is None:
        stats.unknown_classes[raw] += 1
        return "drop"
    return target


def read_yolo(label_path: Path, class_map: dict[str, str], stats: SourceStats,
              ) -> list[tuple[str, float, float, float, float]] | None:
    """Parse one YOLO txt; missing file means no boxes; ``None`` = skip image."""
    boxes: list[tuple[str, float, float, float, float]] = []
    if not label_path.is_file():
        return boxes
    skip = False
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        raw = str(int(float(parts[0])))
        target = map_class(raw, class_map, stats)
        if target == "skip" or skip:
            skip = True                     # đọc tiếp để thống kê box vào đủ
            continue
        if target == "drop":
            stats.boxes_dropped[raw] += 1
            continue
        clipped = clip_box(*(float(v) for v in parts[1:5]))
        if clipped is None:
            stats.boxes_dropped[raw] += 1
            continue
        boxes.append((target, *clipped))
    if skip:
        return None
    for c, *_ in boxes:
        stats.boxes_out[c] += 1
    return boxes


def read_voc(xml_path: Path, class_map: dict[str, str], stats: SourceStats,
             ) -> list[tuple[str, float, float, float, float]] | None:
    """Parse one Pascal VOC xml into normalised xywh boxes; ``None`` = skip."""
    boxes: list[tuple[str, float, float, float, float]] = []
    if not xml_path.is_file():
        return boxes
    raw_xml = xml_path.read_bytes()
    # Nhãn VOC tải từ ngoài là dữ liệu không tin cậy: VOC hợp lệ không cần
    # DOCTYPE/ENTITY, nên từ chối để chặn XXE và "billion laughs".
    head = raw_xml[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in raw_xml.upper():
        log.warning("bỏ %s: XML có DOCTYPE/ENTITY", xml_path.name)
        stats.boxes_dropped["xml_rejected"] += 1
        return boxes
    root = ET.fromstring(raw_xml)
    size = root.find("size")
    w_img = float(size.findtext("width", "0")) if size is not None else 0.0
    h_img = float(size.findtext("height", "0")) if size is not None else 0.0
    if w_img <= 0 or h_img <= 0:
        import cv2  # chỉ khi xml thiếu kích thước

        img = cv2.imread(str(xml_path.with_suffix(".jpg")))
        if img is None:
            return boxes
        h_img, w_img = float(img.shape[0]), float(img.shape[1])
    skip = False
    for obj in root.iter("object"):
        raw = (obj.findtext("name") or "").strip()
        target = map_class(raw, class_map, stats)
        if target == "skip" or skip:
            skip = True                     # đọc tiếp để thống kê box vào đủ
            continue
        bb = obj.find("bndbox")
        if target == "drop" or bb is None:
            stats.boxes_dropped[raw] += 1
            continue
        x1, y1 = float(bb.findtext("xmin", "0")), float(bb.findtext("ymin", "0"))
        x2, y2 = float(bb.findtext("xmax", "0")), float(bb.findtext("ymax", "0"))
        clipped = clip_box((x1 + x2) / 2 / w_img, (y1 + y2) / 2 / h_img,
                           (x2 - x1) / w_img, (y2 - y1) / h_img)
        if clipped is None:
            stats.boxes_dropped[raw] += 1
            continue
        boxes.append((target, *clipped))
    if skip:
        return None
    for c, *_ in boxes:
        stats.boxes_out[c] += 1
    return boxes


# ---------------------------------------------------------------- sources
def group_of(stem: str, regex: str | None) -> str:
    """Split group of an image: first regex group of its stem, else the stem."""
    if regex:
        m = re.match(regex, stem)
        if m and m.groups():
            return m.group(1)
    return stem


def group_prefix(spec) -> str:
    return getattr(spec, "group_namespace", None) or spec.name


def source_images(spec, images_dir: Path) -> list[Path]:
    """Sorted images of a source, reduced to ``spec.pool`` of them when set.

    The subset is chosen by an MD5 of each file stem, so it is the same on
    every machine and run, and both audit_data.py and the dataset builder
    see exactly the same images of a very large public set.
    """
    paths = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMG_EXTS)
    caps: dict[str, int] = getattr(spec, "pool_by_prefix", {}) or {}
    if caps:
        kept: list[Path] = []
        for pre, cap in caps.items():
            group = [p for p in paths if p.stem.startswith(pre)]
            kept += sorted(group, key=_stem_md5)[:cap]
        kept += [p for p in paths
                 if not any(p.stem.startswith(pre) for pre in caps)]
        paths = sorted(kept)
    n = getattr(spec, "pool", 0)
    if n and len(paths) > n:
        paths = sorted(sorted(paths, key=_stem_md5)[:n])
    return paths


def _stem_md5(p: Path) -> str:
    return hashlib.md5(p.stem.encode("utf-8")).hexdigest()


def read_status_csv(path: Path | None) -> dict[str, str]:
    """``image -> label_status`` from a curation status CSV (stem keyed)."""
    if path is None or not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        return {Path(r["image"]).stem: r["label_status"] for r in csv.DictReader(fh)}


def load_source(spec, resolve, exclude: set[str] | None = None,
                group_override: dict[str, str] | None = None,
                ) -> tuple[list[Item], SourceStats]:
    """Read every usable image of one source spec (see ``FinetuneSource``).

    ``exclude`` and ``group_override`` are keyed by resolved absolute path
    strings (from ``audit_data.py``'s exclusions.csv / groups.csv).
    """
    stats = SourceStats()
    exclude = exclude or set()
    group_override = group_override or {}
    status_map = read_status_csv(resolve(spec.status_csv)
                                 if getattr(spec, "status_csv", None) else None)
    images_dir = resolve(spec.images)
    labels_dir = resolve(spec.labels) if spec.labels else images_dir
    if not images_dir.is_dir():
        log.warning("nguồn %s: chưa có thư mục ảnh %s, bỏ qua", spec.name, images_dir)
        return [], stats
    allowed: dict[str, str] | None = None
    if spec.manifest:
        manifest = resolve(spec.manifest)
        allowed = {}
        with manifest.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("labeled", "1") == "1":
                    allowed[Path(row["image"]).stem] = row.get("clip") or ""
    reader = read_voc if spec.format == "voc" else read_yolo
    suffix = ".xml" if spec.format == "voc" else ".txt"
    items: list[Item] = []
    for img in source_images(spec, images_dir):
        stats.images_seen += 1
        if str(img.resolve()) in exclude:
            stats.images_excluded += 1
            continue
        if allowed is not None and img.stem not in allowed:
            stats.images_no_label += 1
            continue
        label = labels_dir / f"{img.stem}{suffix}"
        if not label.is_file() and spec.require_label:
            stats.images_no_label += 1
            continue
        boxes = reader(label, spec.classes, stats)
        if boxes is None:
            stats.images_skipped += 1
            continue
        if spec.role == "hard_neg" and boxes:
            continue
        raw_group = (allowed or {}).get(img.stem) or group_of(img.stem,
                                                                spec.group_regex)
        group = group_override.get(str(img.resolve()),
                                   f"{group_prefix(spec)}:{raw_group}")
        status = status_map.get(img.stem, getattr(spec, "label_status", "verified"))
        items.append(Item(spec.name, img, boxes, group, label_status=status,
                          clip=raw_group))
        stats.images_kept += 1
    if stats.unknown_classes:
        log.warning("nguồn %s: class không có trong classes map (bị bỏ): %s",
                    spec.name, dict(stats.unknown_classes))
    return items, stats


# --------------------------------------------------------------- sampling
def bucket_items(items: list[Item], role: str) -> None:
    """Assign each item to pos_domain / neg_domain / base by role + boxes."""
    for it in items:
        if role == "base":
            it.bucket = "base"
        elif role == "hard_neg":
            it.bucket = "neg_domain"
        else:
            it.bucket = "pos_domain" if it.positive else "neg_domain"


def bucket_targets(available: dict[str, int], ratios: dict[str, float],
                   target_total: int, keep_domain: bool = False) -> dict[str, int]:
    """How many images to take from each bucket.

    With ``target_total`` the total is fixed and split by ratio. Otherwise
    every domain positive is kept and the other buckets are sized relative
    to them. With ``keep_domain`` (and a ``target_total``) every domain image
    is kept and base fills the rest of the total. Each target is capped by
    what is available.
    """
    if keep_domain and target_total > 0:
        raw = {b: available.get(b, 0) for b in ("pos_domain", "neg_domain")}
        raw["base"] = max(0, target_total - sum(raw.values()))
    elif target_total > 0:
        raw = {b: round(target_total * ratios[b]) for b in ROLE_BUCKETS}
    else:
        pos = available.get("pos_domain", 0)
        if pos == 0:
            raise ValueError("chưa có ảnh dương đúng miền: đặt --target-total "
                             "hoặc gán nhãn khung cháy trước")
        scale = pos / ratios["pos_domain"]
        raw = {b: round(scale * ratios[b]) for b in ROLE_BUCKETS}
        raw["pos_domain"] = pos
    return {b: min(raw[b], available.get(b, 0)) for b in ROLE_BUCKETS}


def sample_bucket(items: list[Item], n: int, rng: random.Random) -> list[Item]:
    """Pick ``n`` items, spreading picks over sources as evenly as possible."""
    if n >= len(items):
        return list(items)
    by_source: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        by_source[it.source].append(it)
    for lst in by_source.values():
        rng.shuffle(lst)
    # Chia đều kiểu "đổ nước": nguồn nhỏ lấy hết, phần dư chia cho nguồn lớn hơn.
    queues = sorted(by_source.values(), key=len)
    picked: list[Item] = []
    for i, q in enumerate(queues):
        quota = (n - len(picked)) // (len(queues) - i)
        picked.extend(q[:quota])
    if len(picked) < n:                      # phần lẻ do chia nguyên
        rest = [it for q in queues for it in q if it not in set(picked)]
        picked.extend(rest[: n - len(picked)])
    return picked[:n]


def split_by_group(items: list[Item], val_ratio: float, rng: random.Random,
                   ) -> dict[str, str]:
    """Assign whole groups to train/val so no group spans both splits.

    Every group is decided exactly once, even when its images sit in
    different buckets (fire and pre-ignition frames of one clip). Groups are
    stratified by their *dominant* bucket so val still gets domain positives,
    negatives and base alike. Returns ``image path -> split``.
    """
    groups: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        groups[it.group].append(it)
    dominant: dict[str, str] = {
        g: Counter(it.bucket for it in members).most_common(1)[0][0]
        for g, members in groups.items()}
    by_bucket: dict[str, list[str]] = defaultdict(list)
    for g in sorted(groups):
        by_bucket[dominant[g]].append(g)
    out: dict[str, str] = {}
    for names in by_bucket.values():
        rng.shuffle(names)
        total = sum(len(groups[g]) for g in names)
        n_val = round(total * val_ratio)
        taken = 0
        for g in names:
            size = len(groups[g])
            # Không cho val phình quá gấp đôi mục tiêu khi nhóm quá to; nhóm đầu
            # tiên vẫn được nhận để val không rỗng.
            to_val = (len(names) > 1 and taken < n_val
                      and (taken == 0 or taken + size <= 2 * n_val))
            if to_val:
                taken += size
            for it in groups[g]:
                out[str(it.image)] = "val" if to_val else "train"
    return out


def file_md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dedupe(items: list[Item]) -> tuple[list[Item], int]:
    """Drop byte-identical images (same photo shipped by two sources)."""
    seen: set[str] = set()
    out: list[Item] = []
    for it in items:
        key = file_md5(it.image)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out, len(items) - len(out)


def yolo_lines(boxes: list[tuple[str, float, float, float, float]]) -> str:
    ids = {name: i for i, name in enumerate(TARGET_CLASSES)}
    return "".join(f"{ids[c]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n"
                   for c, cx, cy, w, h in boxes)
