"""
Luật ghép tín hiệu cháy của FireWatch vào sự cố đang mở (Mắt Phố Backend).

Module thuần: không phụ thuộc Firestore để test được bằng dict. Quy tắc:
1. Cùng ``event_id`` (hoặc ``event_id`` nằm trong ``event_ids`` của alert) là cùng sự cố.
2. Một camera chỉ có một sự cố đang mở: tín hiệu mới của camera đang có alert
   ``NEW`` / ``CONFIRMED`` còn hoạt động trong ``INCIDENT_MERGE_WINDOW_S`` giây
   (mặc định 900) được ghép vào alert đó dù FireWatch cấp ``event_id`` mới
   (FireWatch chạy lại, clip lặp, sự cố đóng rồi bùng lại).
3. Alert mở nhưng im lặng quá cửa sổ thì coi như sự cố cũ: tạo alert mới.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

TRANG_THAI_MO = ("NEW", "CONFIRMED")
MAC_DINH_CUA_SO_S = 900


def cua_so_ghep_s() -> int:
    """Cửa sổ ghép (giây) từ biến môi trường ``INCIDENT_MERGE_WINDOW_S``."""
    raw = os.getenv("INCIDENT_MERGE_WINDOW_S", "").strip()
    try:
        value = int(raw) if raw else MAC_DINH_CUA_SO_S
    except ValueError:
        value = MAC_DINH_CUA_SO_S
    return max(value, 0)


def doc_gio(value: Any) -> Optional[datetime]:
    """Đổi giá trị thời gian (datetime, ISO string, None) sang datetime có múi giờ."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def moc_hoat_dong(doc: Dict[str, Any]) -> Optional[datetime]:
    """Lần hoạt động gần nhất của alert: lớn nhất trong last_seen_ts, updated_at, created_at."""
    mocs = [doc_gio(doc.get(k)) for k in ("last_seen_ts", "updated_at", "created_at")]
    mocs = [m for m in mocs if m is not None]
    return max(mocs) if mocs else None


def cung_event(doc: Dict[str, Any], event_id: Optional[str]) -> bool:
    if not event_id:
        return False
    if doc.get("event_id") == event_id:
        return True
    aliases = doc.get("event_ids") or []
    return isinstance(aliases, (list, tuple)) and event_id in aliases


def chon_su_co_dang_mo(
    docs: Iterable[Dict[str, Any]],
    *,
    event_id: Optional[str],
    cam_id: str,
    now: datetime,
    cua_so_s: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Chọn alert để ghép tín hiệu mới vào, hoặc ``None`` nếu phải tạo alert mới.

    ``docs`` là các alert ứng viên (dict có ``alert_id``, ``cam_id``, ``status``,
    ``event_id``, ``event_ids``, ``created_at``, ``updated_at``, ``last_seen_ts``).
    """
    cua_so = cua_so_ghep_s() if cua_so_s is None else cua_so_s
    candidates: List[Dict[str, Any]] = list(docs)

    for doc in candidates:
        if cung_event(doc, event_id):
            return doc

    mo: List[tuple] = []
    for doc in candidates:
        if doc.get("cam_id") != cam_id:
            continue
        if str(doc.get("status") or "") not in TRANG_THAI_MO:
            continue
        moc = moc_hoat_dong(doc)
        if moc is None:
            continue
        tuoi = (now - moc).total_seconds()
        if 0 <= tuoi <= cua_so or tuoi < 0:
            mo.append((moc, doc))
    if not mo:
        return None
    mo.sort(key=lambda x: x[0], reverse=True)
    return mo[0][1]


def tai_bung(doc: Dict[str, Any], payload_type: Optional[str], event_id: Optional[str]) -> bool:
    """
    Tín hiệu ``created`` mang ``event_id`` khác alert đang mở: FireWatch coi đây là sự cố
    mới (sự cố cũ đã ``ended`` hoặc FireWatch chạy lại). Backend giữ cùng alert nhưng phát
    lại cảnh báo tới app.
    """
    if (payload_type or "").lower() != "created":
        return False
    if not event_id:
        return False
    return not cung_event(doc, event_id)
