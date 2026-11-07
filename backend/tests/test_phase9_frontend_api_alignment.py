"""
Tests for Phase 9: Frontend Flutter API Alignment
Verifying:
1. ai_schedule preservation in CameraModel & PATCH /api/v1/cameras/{id} (Fixing data loss)
2. Snapshot-on-Exit thumbnail upload via POST /api/v1/cameras/{id}/thumbnail (JSON Base64 PNG)
3. Inclusion of thumbnail_url, is_ai_enabled, and ai_schedule in all Camera GET/PATCH responses
4. Overnight AI rest schedule computation (e.g. 22:00 -> 06:00)
"""

import time
import pytest
from datetime import datetime, timezone, timedelta
from src.core.ai_schedule import should_ai_scan_now, is_in_rest_schedule
from src.models.common import UserRole

TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _register_user(client, phone: str, name: str) -> dict:
    req = client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": phone, "full_name": name, "password": "Password123@"},
    )
    assert req.status_code == 200
    ch_id = req.json()["challenge_id"]
    ver = client.post(
        "/api/v1/auth/verify-otp",
        json={"challenge_id": ch_id, "code": "123456"},
    )
    assert ver.status_code == 200
    data = ver.json()
    token = data["custom_token"]
    user_id = data["user"]["user_id"]
    return {
        "user_id": user_id,
        "token": token,
        "phone": phone,
        "name": name,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def test_overnight_rest_schedule_evaluation():
    """
    Verify overnight schedule logic: 22:00 -> 06:00 on Monday (1).
    At 23:30 Monday -> Resting (should_scan = False)
    At 03:00 Tuesday -> Resting from previous day's shift (should_scan = False)
    At 08:00 Tuesday -> Active (should_scan = True)
    """
    schedule = [
        {"from": "22:00", "to": "06:00", "days": [1]}  # Monday night to Tuesday morning
    ]

    vn_tz = timezone(timedelta(hours=7))

    # Monday 23:30 (Monday is weekday=0, ISO=1)
    # 2026-11-09 is Monday
    monday_2330 = datetime(2026, 11, 9, 23, 30, tzinfo=vn_tz)
    assert is_in_rest_schedule(schedule, monday_2330) is True
    assert should_ai_scan_now(True, schedule, monday_2330) is False

    # Tuesday 03:00 (from previous Monday night shift)
    # 2026-11-10 is Tuesday
    tuesday_0300 = datetime(2026, 11, 10, 3, 0, tzinfo=vn_tz)
    assert is_in_rest_schedule(schedule, tuesday_0300) is True
    assert should_ai_scan_now(True, schedule, tuesday_0300) is False

    # Tuesday 08:00 (Past 06:00, active scanning)
    tuesday_0800 = datetime(2026, 11, 10, 8, 0, tzinfo=vn_tz)
    assert is_in_rest_schedule(schedule, tuesday_0800) is False
    assert should_ai_scan_now(True, schedule, tuesday_0800) is True


def test_camera_ai_schedule_preservation_and_thumbnail(client):
    """
    Test end-to-end:
    1. Leader creates camera
    2. Leader patches camera with ai_schedule (from/to/days) -> Verifies persistence
    3. Leader uploads thumbnail base64 PNG -> Verifies cache buster ?v=
    4. Member with NOTIFIER role is blocked from uploading thumbnail (403)
    5. GET /cameras and GET /cameras/{id} return both ai_schedule and thumbnail_url
    """
    ts = int(time.time() * 1000) % 10000000
    leader = _register_user(client, f"091{ts:07d}", "Trưởng Nhóm Phase 9")
    notifier = _register_user(client, f"092{ts:07d}", "Người Nhận Tin Phase 9")

    # 1. Create a group
    grp_res = client.post(
        "/api/v1/groups",
        json={"name": "Nhóm Thử Nghiệm API 9", "address": "123 Đường Cứu Hỏa"},
        headers=leader["headers"],
    )
    assert grp_res.status_code == 201
    group_id = grp_res.json()["group_id"]

    # Add notifier to group
    inv_res = client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"phone_number": notifier["phone"], "role": "NOTIFIER"},
        headers=leader["headers"],
    )
    assert inv_res.status_code == 201
    inv_id = inv_res.json()["invitation_id"]
    acc_res = client.post(
        f"/api/v1/invitations/{inv_id}/accept",
        headers=notifier["headers"],
    )
    assert acc_res.status_code == 200

    # 2. Add camera
    cam_res = client.post(
        "/api/v1/cameras",
        json={
            "group_id": group_id,
            "cam_name": "Camera Sân Sau",
            "rtsp_url": "rtsp://mock-cam.lan/live",
            "device_name": "IP Cam Outdoor",
        },
        headers=leader["headers"],
    )
    assert cam_res.status_code == 201
    cam_id = cam_res.json()["cam_id"]

    # 3. Patch ai_schedule as sent by Flutter App
    schedule_payload = [
        {"from": "17:00", "to": "19:30", "days": [1, 2, 3, 4, 5, 6, 7]},
        {"from": "10:30", "to": "12:30", "days": [6, 7]},
    ]
    patch_res = client.patch(
        f"/api/v1/cameras/{cam_id}",
        json={
            "is_ai_enabled": True,
            "ai_schedule": schedule_payload,
        },
        headers=leader["headers"],
    )
    assert patch_res.status_code == 200
    patch_data = patch_res.json()
    assert patch_data["is_ai_enabled"] is True
    assert len(patch_data["ai_schedule"]) == 2
    assert patch_data["ai_schedule"][0]["from"] == "17:00"
    assert patch_data["ai_schedule"][0]["to"] == "19:30"
    assert patch_data["ai_schedule"][0]["days"] == [1, 2, 3, 4, 5, 6, 7]

    # 4. GET camera detail to verify ai_schedule is NOT lost
    get_res = client.get(f"/api/v1/cameras/{cam_id}", headers=leader["headers"])
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["is_ai_enabled"] is True
    assert len(get_data["ai_schedule"]) == 2
    assert get_data["ai_schedule"][1]["from"] == "10:30"

    # 5. Upload thumbnail (Base64 PNG)
    thumb_res = client.post(
        f"/api/v1/cameras/{cam_id}/thumbnail",
        json={"image_base64": TINY_PNG_BASE64},
        headers=leader["headers"],
    )
    assert thumb_res.status_code == 200
    thumb_data = thumb_res.json()
    assert thumb_data["status"] == "ok"
    assert thumb_data["cam_id"] == cam_id
    assert "thumbnail_url" in thumb_data
    assert "v=" in thumb_data["thumbnail_url"]

    # 6. Verify thumbnail_url appears in GET /cameras/{id} and GET /cameras
    get_res2 = client.get(f"/api/v1/cameras/{cam_id}", headers=leader["headers"])
    assert get_res2.status_code == 200
    assert get_res2.json()["thumbnail_url"] == thumb_data["thumbnail_url"]

    list_res = client.get(f"/api/v1/cameras?group_id={group_id}", headers=leader["headers"])
    assert list_res.status_code == 200
    cams = list_res.json()
    assert len(cams) >= 1
    found = next((c for c in cams if c["cam_id"] == cam_id), None)
    assert found is not None
    assert found["thumbnail_url"] == thumb_data["thumbnail_url"]
    assert len(found["ai_schedule"]) == 2

    # 7. NOTIFIER role must get 403 when trying to upload thumbnail
    notif_upload = client.post(
        f"/api/v1/cameras/{cam_id}/thumbnail",
        json={"image_base64": TINY_PNG_BASE64},
        headers=notifier["headers"],
    )
    assert notif_upload.status_code == 403
