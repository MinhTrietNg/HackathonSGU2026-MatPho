"""
AI Schedule & Mode Engine for Mắt Phố (Figma H7 -> H15)
Computes whether FireWatch AI should currently scan a camera's RTSP stream
and formats Vietnamese UI status strings matching Figma H7-H15.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Union

VN_TZ = timezone(timedelta(hours=7))

WEEKDAY_TO_VN: Dict[int, str] = {
    0: "T2",
    1: "T3",
    2: "T4",
    3: "T5",
    4: "T6",
    5: "T7",
    6: "CN",
}

ALL_DAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
WEEKDAYS = ["T2", "T3", "T4", "T5", "T6"]
WEEKEND = ["T7", "CN"]


def _normalize_slot(slot: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    if hasattr(slot, "model_dump"):
        data = slot.model_dump(by_alias=True)
    elif isinstance(slot, dict):
        data = dict(slot)
    else:
        return {}

    # Map 'from' / 'to' <-> 'start_time' / 'end_time'
    start = data.get("from") or data.get("start_time") or ""
    end = data.get("to") or data.get("end_time") or ""
    raw_days = data.get("days") or []

    # Map ISO weekday integers [1..7] (1=Monday ... 7=Sunday) <-> VN codes ["T2".."CN"]
    norm_iso_days = set()
    norm_vn_days = set()
    for d in raw_days:
        if isinstance(d, int):
            if 1 <= d <= 7:
                norm_iso_days.add(d)
                norm_vn_days.add(WEEKDAY_TO_VN[d - 1])
        elif isinstance(d, str):
            d_upper = d.strip().upper()
            if d_upper in WEEKDAY_TO_VN.values():
                norm_vn_days.add(d_upper)
                for k, v in WEEKDAY_TO_VN.items():
                    if v == d_upper:
                        norm_iso_days.add(k + 1)

    return {
        "from": start[:5] if start else "",
        "to": end[:5] if end else "",
        "start_time": start[:5] if start else "",
        "end_time": end[:5] if end else "",
        "days": sorted(list(norm_iso_days)) if norm_iso_days else list(raw_days),
        "days_vn": sorted(list(norm_vn_days)),
        "days_iso": sorted(list(norm_iso_days)),
    }


def is_in_rest_schedule(
    schedules: Optional[List[Union[Dict[str, Any], Any]]],
    now_vn: Optional[datetime] = None,
) -> bool:
    """
    Returns True if `now_vn` (default: current time in Asia/Ho_Chi_Minh UTC+7)
    falls inside ANY configured AI rest schedule slot.
    Supports both intra-day (e.g. 17:00 -> 19:30) and overnight (e.g. 22:00 -> 06:00) slots.
    Supports both ISO days [1..7] and VN codes ['T2'..'CN'].
    """
    if not schedules:
        return False

    now = now_vn or datetime.now(VN_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=VN_TZ)
    else:
        now = now.astimezone(VN_TZ)

    curr_weekday_iso = now.isoweekday()  # 1 = Monday, ..., 7 = Sunday
    prev_weekday_iso = 7 if curr_weekday_iso == 1 else curr_weekday_iso - 1
    curr_day_code = WEEKDAY_TO_VN[now.weekday()]
    prev_day_code = WEEKDAY_TO_VN[(now.weekday() - 1) % 7]
    curr_hm = now.strftime("%H:%M")

    for raw_slot in schedules:
        s = _normalize_slot(raw_slot)
        start = s.get("from") or s.get("start_time", "")
        end = s.get("to") or s.get("end_time", "")
        days_iso = s.get("days_iso") or []
        days_vn = s.get("days_vn") or []

        if not start or not end or (not days_iso and not days_vn):
            continue

        is_curr_day_match = (curr_weekday_iso in days_iso) or (curr_day_code in days_vn)
        is_prev_day_match = (prev_weekday_iso in days_iso) or (prev_day_code in days_vn)

        if start <= end:
            # Intra-day slot (e.g. 17:00 -> 19:30)
            if is_curr_day_match and start <= curr_hm < end:
                return True
        else:
            # Overnight slot (e.g. 22:00 -> 06:00)
            # Active if starting day is today and time >= 22:00 OR yesterday started and time < 06:00
            if (is_curr_day_match and curr_hm >= start) or (is_prev_day_match and curr_hm < end):
                return True

    return False


def should_ai_scan_now(
    is_ai_enabled_or_mode: Union[bool, Optional[str]],
    schedules: Optional[List[Union[Dict[str, Any], Any]]] = None,
    now_vn: Optional[datetime] = None,
) -> bool:
    """
    Determines whether FireWatch AI should keep the RTSP stream open and run inference.
    Supports both:
      1. Boolean flag: `is_ai_enabled: bool` + `ai_schedule` (Frontend v3.4 contract)
      2. String enum: `ai_mode: "ALWAYS" | "SCHEDULE" | "OFF"`
    """
    if isinstance(is_ai_enabled_or_mode, bool):
        if not is_ai_enabled_or_mode:
            return False
        if not schedules:
            return True
        return not is_in_rest_schedule(schedules, now_vn=now_vn)

    mode = str(is_ai_enabled_or_mode.value if hasattr(is_ai_enabled_or_mode, "value") else (is_ai_enabled_or_mode or "ALWAYS")).upper()
    if mode == "OFF":
        return False
    if mode == "SCHEDULE":
        return not is_in_rest_schedule(schedules, now_vn=now_vn)
    return True


def _format_days_label(days: List[str]) -> str:
    day_set = set(days)
    if day_set == set(ALL_DAYS) or len(day_set) == 7:
        return "mỗi ngày"
    if day_set == set(WEEKDAYS):
        return "T2–T6"
    if day_set == set(WEEKEND):
        return "T7–CN"
    ordered = [d for d in ALL_DAYS if d in day_set]
    return ", ".join(ordered)


def format_ai_status_text(
    ai_mode: Optional[str],
    schedules: Optional[List[Union[Dict[str, Any], Any]]] = None,
    is_editable: bool = True,
) -> str:
    """
    Generates exact Vietnamese subtitle string for camera rows on Figma H7, H8, H9:
      - ALWAYS (Editable): "Đang bật 24/7"
      - ALWAYS (Locked H8): "Bật 24/7 · chỉ chủ nhóm đổi được"
      - OFF (Editable): "Đã tắt AI"
      - OFF (Locked H8): "Đã tắt AI · chỉ chủ nhóm đổi được"
      - SCHEDULE (1 slot): "Nghỉ 17:00–19:30 · mỗi ngày"
      - SCHEDULE (2 slots): "Nghỉ 11:00–13:30, 17:00–19:30"
    """
    mode = str(ai_mode.value if hasattr(ai_mode, "value") else (ai_mode or "ALWAYS")).upper()
    suffix = "" if is_editable else " · chỉ chủ nhóm đổi được"

    if mode == "OFF":
        return f"Đã tắt AI{suffix}"

    if mode == "SCHEDULE" and schedules:
        norm_slots = [_normalize_slot(x) for x in schedules if _normalize_slot(x)]
        if len(norm_slots) == 1:
            s0 = norm_slots[0]
            start = s0.get("start_time", "17:00")
            end = s0.get("end_time", "19:30")
            days_lbl = _format_days_label(s0.get("days") or ALL_DAYS)
            return f"Nghỉ {start}–{end} · {days_lbl}{suffix}"
        elif len(norm_slots) >= 2:
            ranges = [f"{s.get('start_time', '')}–{s.get('end_time', '')}" for s in norm_slots[:2]]
            return f"Nghỉ {', '.join(ranges)}{suffix}"

    if is_editable:
        return "Đang bật 24/7"
    return "Bật 24/7 · chỉ chủ nhóm đổi được"
