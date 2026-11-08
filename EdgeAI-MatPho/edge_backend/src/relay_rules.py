"""
Pure rules of the fire-event relay (no PyAV / SQLite imports, unit-testable):
camera id matching, offline-queue drop policy, local-only address check.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

DIA_CHI_NOI_BO = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "mediamtx", "host.docker.internal")


def match_cam_id(raw_camera_id: Optional[str], cams: List[Dict[str, Any]]) -> str:
    """
    Map the FireWatch camera identifier to a registered cam_id: exact cam_id first, then exact
    cam_name (case-insensitive). No substring matching: "cam_1" must never be routed to
    "cam_10", or every alert of one camera would land on another camera's incident.
    Unknown ids are forwarded unchanged so the cloud can reject them explicitly.
    """
    if not raw_camera_id:
        return "cam_unknown"
    for c in cams:
        if c.get("cam_id") == raw_camera_id:
            return c["cam_id"]
    raw_lower = raw_camera_id.lower()
    for c in cams:
        if c.get("cam_name") and str(c["cam_name"]).lower() == raw_lower:
            return c["cam_id"]
    return raw_camera_id


def bo_su_kien_bi_tu_choi(status_code: int) -> bool:
    """
    True when a queued fire event must be dropped instead of retried: 4xx answers are
    final (404 camera unknown, 422 payload), except auth/rate-limit (401, 403, 408, 429)
    which can succeed later. 5xx and network errors are always retried.
    """
    if 400 <= status_code < 500:
        return status_code not in (401, 403, 408, 429)
    return False


def la_dia_chi_noi_bo(url: str) -> bool:
    """URL only reachable from the machine itself (meaningless for a phone)."""
    host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].strip().lower()
    return host in DIA_CHI_NOI_BO
