"""Hard negatives from the operator loop.

When an operator answers an alert with "dismiss — controlled fire", the
keyframe and a metadata JSON are copied to ``alerts.hitl_negatives_dir``
(``data/hitl_negatives/``, not versioned). That folder feeds the eval set as
hard negatives (charcoal grills, cooking, burning in a container next to
parked bikes) and, after review, the fine-tune set.

Files per event, named ``<started_at>_<event_id[:8]>``:

* ``.jpg``           clean keyframe (no boxes / banner) when the store saved
  one (``alerts.save_raw_keyframe``), else the annotated snapshot;
* ``_annotated.jpg`` the snapshot as the operator saw it;
* ``.json``          event_id, camera_id, context, severity, verification,
  boxes, fire_type, VLM description, operator note, timestamps.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from .acks import Ack
from .alerts import Event, raw_keyframe_path

log = logging.getLogger(__name__)
EXPORT_ACTION = "dismiss_controlled"


def export_hard_negative(event: Event, ack: Ack, root: Path,
                         out_dir: Path) -> Path | None:
    """Copy keyframe + metadata of a dismissed alert into ``out_dir``.

    Parameters
    ----------
    event : Event
        The dismissed event.
    ack : Ack
        The operator decision (must be ``dismiss_controlled``).
    root : Path
        Project root that ``event.snapshot_path`` is relative to.
    out_dir : Path
        Destination folder, created if needed.

    Returns
    -------
    Path or None
        The metadata JSON written, or ``None`` when the action is not a
        dismissal.
    """
    if ack.action != EXPORT_ACTION:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.fromisoformat(event.started_at)
    stem = f"{started:%Y%m%d_%H%M%S}_{event.event_id[:8]}"
    snapshot = (root / event.snapshot_path) if event.snapshot_path else None
    image_file, image_is_raw = "", False
    if snapshot is not None and snapshot.is_file():
        raw = raw_keyframe_path(snapshot)
        source = raw if raw.is_file() else snapshot
        image_is_raw = source == raw
        shutil.copyfile(source, out_dir / f"{stem}.jpg")
        shutil.copyfile(snapshot, out_dir / f"{stem}_annotated.jpg")
        image_file = f"{stem}.jpg"
    else:
        log.warning("event %s không có snapshot: chỉ xuất metadata",
                    event.event_id[:8])
    vlm = event.vlm
    meta = {
        "event_id": event.event_id, "camera_id": event.camera_id,
        "context": event.context, "severity": event.severity,
        "verification": event.verification, "started_at": event.started_at,
        "video_ts_sec": event.video_ts_sec,
        "boxes": [b.model_dump() for b in event.boxes],
        "fire_type": vlm.fire_type if vlm else None,
        "vlm_description_vi": vlm.description_vi if vlm else None,
        "operator_action": ack.action, "operator_note": ack.note,
        "acked_at": ack.acked_at, "image": image_file,
        "image_is_raw": image_is_raw,
        "label": "negative",
    }
    path = out_dir / f"{stem}.json"
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("hard negative từ người trực: %s (%s)", path.name,
             "ảnh gốc" if image_is_raw else "ảnh đã vẽ box")
    return path
