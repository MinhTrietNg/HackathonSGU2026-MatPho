"""Which images get synthetic copies, and the train / val list files.

The v1.1 set gave every original two synthetic copies (66.6 % of the images,
val included) and trained on the folders. v1.2 instead:

* gives a synthetic copy to a fixed share of the *base* originals (chosen by
  a hash of the name, so a rebuild picks the same ones) and to every domain
  original, which are scarce and the most valuable to see at night;
* keeps val to originals (``val.txt``) so the checkpoint is not chosen on
  synthetic images, with the domain part listed apart (``val_domain.txt``);
* repeats domain lines in ``train.txt`` per clip, more for CCTV and
  basement / ground-floor clips than for news footage, whose logos and
  captions a repeated frame would teach (news clips at most twice, even
  in a basement).
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path

DOMAIN = ("pos_domain", "neg_domain")


def unit(name: str, salt: str) -> float:
    """Stable number in [0, 1) from a file stem and a salt."""
    h = hashlib.md5(f"{salt}:{name}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 2 ** 32


def wants_copy(row: dict, kind: str, fraction: float,
               val_domain_copies: bool = True) -> bool:
    """Whether an original manifest row gets a synthetic copy of ``kind``.

    Parameters
    ----------
    row : dict
        Manifest row with ``_name``, ``split`` and ``bucket``.
    kind : str
        ``"xam"`` or ``"cam"``: separate salts, so the two copies fall on
        different originals.
    fraction : float
        Share of base train originals that get the copy.
    val_domain_copies : bool
        Domain val originals also get copies (listed apart, for measuring
        robustness, never in ``val.txt``).
    """
    if row["bucket"] in DOMAIN:
        return row["split"] == "train" or val_domain_copies
    return row["split"] == "train" and unit(row["_name"], kind) < fraction


def clip_repeats(rows: Iterable[dict], target: int, caps: dict[str, int],
                 default_cap: int = 1,
                 camera_max: dict[str, int] | None = None) -> dict[str, int]:
    """Times each domain clip's train lines are written in ``train.txt``.

    ``ceil(target / originals)`` per clip, capped by the largest cap that
    applies to the clip's ``camera`` or ``context`` (e.g. ``cctv: 4``,
    ``ham: 4``), else ``default_cap``; then never above ``camera_max`` of
    its camera. A basement clip cut from the news is rare enough to repeat,
    but ``camera_max: {tin_tuc: 2}`` keeps its logos and captions from being
    seen four times as often as the rest.
    """
    camera_max = camera_max or {}
    n: Counter = Counter()
    meta: dict[str, tuple[str, str]] = {}
    for r in rows:
        if r["split"] == "train" and r["bucket"] == "pos_domain" \
                and r["variant"] == "goc":
            n[r["clip_id"]] += 1
            meta[r["clip_id"]] = (r["camera"], r["context"])
    out = {}
    for clip, k in n.items():
        camera, context = meta[clip]
        cap = max(caps.get(camera, 0), caps.get(context, 0), default_cap)
        cap = min(cap, camera_max.get(camera, cap))
        out[clip] = max(1, min(cap, math.ceil(target / k)))
    return out


def write_lists(out: Path, rows: list[dict], repeats: dict[str, int],
                neg_domain_repeat: int = 1) -> dict[str, int]:
    """Write ``train.txt``, ``val.txt``, ``val_domain.txt`` and
    ``val_domain_bien_the.txt`` in the dataset root.

    Lines are ``./images/<split>/<file>`` so Ultralytics resolves them next
    to the list file. Returns the number of lines of each list.
    """
    lists: dict[str, list[str]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["image"]):
        line = f"./{r['image']}"
        if r["split"] == "train":
            rep = 1
            if r["bucket"] == "pos_domain":
                rep = repeats.get(r["clip_id"], 1)
            elif r["bucket"] == "neg_domain":
                rep = neg_domain_repeat
            lists["train.txt"] += [line] * rep
        elif r["variant"] == "goc":
            lists["val.txt"].append(line)
            if r["bucket"] in DOMAIN:
                lists["val_domain.txt"].append(line)
        elif r["bucket"] in DOMAIN:
            lists["val_domain_bien_the.txt"].append(line)
    for name in ("train.txt", "val.txt", "val_domain.txt", "val_domain_bien_the.txt"):
        (out / name).write_text("".join(f"{x}\n" for x in lists[name]),
                                encoding="utf-8")
    return {k: len(v) for k, v in lists.items()}


def epoch_mix(rows: list[dict], repeats: dict[str, int]) -> dict[str, float]:
    """Share of the positive train lines per group in one epoch (in %)."""
    pos: Counter = Counter()
    for r in rows:
        if r["split"] != "train" or int(r["n_fire"]) + int(r["n_smoke"]) == 0:
            continue
        rep = repeats.get(r["clip_id"], 1) if r["bucket"] == "pos_domain" else 1
        key = "dung_mien" if r["bucket"] in DOMAIN else r["source"]
        pos[key] += rep
    total = sum(pos.values()) or 1
    return {k: round(100 * v / total, 2) for k, v in pos.most_common()}
