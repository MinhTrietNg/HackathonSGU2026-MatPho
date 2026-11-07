"""
Utility Formatters and Normalizers for Mắt Phố Backend
"""

import re
from typing import Optional, List, Any
from datetime import datetime, timezone


def format_iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """
    Format a datetime object into a strict ISO-8601 UTC string (YYYY-MM-DDTHH:mm:ss.sssZ).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def current_utc_iso() -> str:
    """Return the current UTC timestamp formatted as ISO-8601."""
    return format_iso_utc(datetime.now(timezone.utc))


def parse_iso_utc(val: Any) -> Optional[datetime]:
    """Parse string or timestamp to timezone-aware UTC datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc)
    if isinstance(val, str):
        cleaned = val.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None
    return None


def normalize_phone_e164(phone: str) -> str:
    """
    Normalize Vietnamese phone numbers to international E.164 format (+84xxxxxxxxx).
    Examples:
      '0912345678'   -> '+84912345678'
      '84912345678'  -> '+84912345678'
      '+84912345678' -> '+84912345678'
      '091 234 5678' -> '+84912345678'
    """
    if not phone:
        return ""
    # Strip non-digit characters except leading '+'
    digits_only = re.sub(r"[^\d+]", "", phone.strip())
    if digits_only.startswith("+84"):
        return digits_only
    if digits_only.startswith("84") and len(digits_only) >= 11:
        return f"+{digits_only}"
    if digits_only.startswith("0") and len(digits_only) >= 10:
        return f"+84{digits_only[1:]}"
    if not digits_only.startswith("+"):
        return f"+84{digits_only}"
    return digits_only


def normalize_bbox(bbox: Any) -> List[float]:
    """
    Normalize bounding box to 4 normalized coordinates [x1, y1, x2, y2] between 0.0 and 1.0.
    """
    if not bbox or not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        return [0.0, 0.0, 1.0, 1.0]
    return [float(x) for x in bbox[:4]]
