"""
Phase 4 Test Suite: Camera Management, RTSP Probe, HLS Stream RBAC, Watch Area & 30-Day Trash Bin
"""

import time
import pytest
from src.services.repositories.user_repo import get_user_repo
from src.services.repositories.group_repo import get_group_repo
from src.services.repositories.camera_repo import get_camera_repo
from src.models.common import UserRole


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


def test_rtsp_probe_simulation_and_errors(client):
    """Test RTSP probe simulation for success, auth fail, and vendor blocked."""
    ts = int(time.time() * 1000) % 10000000
    leader = _register_user(client, f"093{ts:07d}", "Trưởng Nhóm Probe")

    # 1. Success probe simulation
    res_ok = client.post(
        "/api/v1/cameras/probe",
        json={"rtsp_url": "rtsp://admin:pass@mock-camera.local:554/live"},
        headers=leader["headers"],
    )
    assert res_ok.status_code == 200
    data_ok = res_ok.json()
    assert data_ok["resolution"] == "1920x1080"
    assert data_ok["fps"] == 25
    assert "preview_snapshot_url" in data_ok

    # 2. Auth fail simulation
    res_auth = client.post(
        "/api/v1/cameras/probe",
        json={"rtsp_url": "rtsp://wrong_pass@auth-fail.local/live"},
        headers=leader["headers"],
    )
    assert res_auth.status_code == 400
    err_auth = res_auth.json()["error"]
    assert err_auth["code"] == "CAMERA_AUTH_FAILED"

    # 3. Vendor blocked simulation
    res_vendor = client.post(
        "/api/v1/cameras/probe",
        json={"rtsp_url": "rtsp://vendor-blocked.local/live"},
        headers=leader["headers"],
    )
    assert res_vendor.status_code == 400
    err_vendor = res_vendor.json()["error"]
    assert err_vendor["code"] == "CAMERA_VENDOR_BLOCKED"


def test_camera_crud_and_counts(client):
    """Test camera creation, group/subgroup count updates, and listings."""
    ts = int(time.time() * 1000) % 10000000
    leader = _register_user(client, f"094{ts:07d}", "Trưởng Nhóm Cam")

    # 1. Create a group
    res_grp = client.post(
        "/api/v1/groups",
        json={"name": "Khu phố Camera", "address": "Quận 1", "my_nickname": "Trưởng Ban"},
        headers=leader["headers"],
    )
    assert res_grp.status_code == 201
    group_id = res_grp.json()["group_id"]

    # 2. Create a subgroup
    res_sub = client.post(
        f"/api/v1/groups/{group_id}/subgroups",
        json={"name": "Ngõ 12", "description": "Khu ngõ 12"},
        headers=leader["headers"],
    )
    assert res_sub.status_code == 201
    subgroup_id = res_sub.json()["subgroup_id"]

    # 3. Create a camera
    cam_payload = {
        "group_id": group_id,
        "subgroup_id": subgroup_id,
        "cam_name": "Camera Đầu Ngõ 12",
        "device_name": "Hikvision 2MP",
        "rtsp_url": "rtsp://admin:123456@192.168.1.10:554/live",
        "watch_area": {
            "left": 0.1,
            "top": 0.1,
            "width": 0.8,
            "height": 0.8,
        },
    }
    res_cam = client.post("/api/v1/cameras", json=cam_payload, headers=leader["headers"])
    assert res_cam.status_code == 201
    cam_data = res_cam.json()
    cam_id = cam_data["cam_id"]
    assert cam_data["cam_name"] == "Camera Đầu Ngõ 12"
    assert cam_data["live_stream_url"] is not None

    # Check count in subgroup
    sub_detail = client.get(f"/api/v1/groups/{group_id}/subgroups", headers=leader["headers"]).json()
    target_sub = next(s for s in sub_detail if s["subgroup_id"] == subgroup_id)
    assert target_sub["camera_count"] == 1

    # 4. List cameras
    res_list = client.get(f"/api/v1/cameras?group_id={group_id}", headers=leader["headers"])
    assert res_list.status_code == 200
    cam_list = res_list.json()
    assert len(cam_list) == 1
    assert cam_list[0]["cam_id"] == cam_id
    assert cam_list[0]["live_stream_url"] is not None

    # 5. Get camera detail
    res_detail = client.get(f"/api/v1/cameras/{cam_id}", headers=leader["headers"])
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["cam_id"] == cam_id
    assert "Trưởng Nhóm Cam" in detail["notified_names"]


def test_camera_rbac_stream_blocking(client):
    """
    CRITICAL RBAC TEST:
    - LEADER can get HLS stream.
    - NOTIFIER is STRICTLY BLOCKED (403 and null stream_url).
    - MEMBER without camera assignment cannot get HLS stream (403 and null stream_url).
    """
    ts = int(time.time() * 1000) % 10000000
    leader = _register_user(client, f"095{ts:07d}", "Trưởng Ban RBAC")
    notifier = _register_user(client, f"096{ts:07d}", "Cụ Già Nhận Tin")
    member_no_cam = _register_user(client, f"097{ts:07d}", "Thành Viên Không Gán Cam")

    # 1. Create group and camera
    res_grp = client.post(
        "/api/v1/groups",
        json={"name": "Khu Phố An Toàn", "address": "Phố Huế", "my_nickname": "Trưởng Phố"},
        headers=leader["headers"],
    )
    group_id = res_grp.json()["group_id"]

    res_cam = client.post(
        "/api/v1/cameras",
        json={
            "group_id": group_id,
            "cam_name": "Camera Giám Sát Phố",
            "rtsp_url": "rtsp://admin:pass@192.168.1.50/live",
        },
        headers=leader["headers"],
    )
    cam_id = res_cam.json()["cam_id"]

    # 2. Add NOTIFIER to group
    inv_notif = client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"phone_number": notifier["phone"], "role": "NOTIFIER", "nickname": "Bà Bẩy"},
        headers=leader["headers"],
    ).json()
    client.post(f"/api/v1/invitations/{inv_notif['invitation_id']}/accept", headers=notifier["headers"])

    # 3. Add MEMBER (camera_ids = []) to group
    inv_mem = client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"phone_number": member_no_cam["phone"], "role": "MEMBER", "nickname": "Chú Tám"},
        headers=leader["headers"],
    ).json()
    client.post(f"/api/v1/invitations/{inv_mem['invitation_id']}/accept", headers=member_no_cam["headers"])

    # Explicitly set member_no_cam camera_ids to empty list (not assigned to this cam)
    client.put(
        f"/api/v1/groups/{group_id}/members/{member_no_cam['user_id']}/cameras",
        json={"camera_ids": []},
        headers=leader["headers"],
    )

    # TEST A: LEADER accesses stream -> SUCCESS 200
    res_leader_stream = client.get(f"/api/v1/cameras/{cam_id}/stream", headers=leader["headers"])
    assert res_leader_stream.status_code == 200
    assert "stream_url" in res_leader_stream.json()
    assert res_leader_stream.json()["stream_type"] == "HLS"

    # TEST B: NOTIFIER lists cameras -> live_stream_url IS NULL
    res_notif_list = client.get(f"/api/v1/cameras?group_id={group_id}", headers=notifier["headers"])
    assert res_notif_list.status_code == 200
    assert res_notif_list.json()[0]["live_stream_url"] is None

    # TEST C: NOTIFIER attempts direct stream -> 403 PERMISSION_DENIED
    res_notif_stream = client.get(f"/api/v1/cameras/{cam_id}/stream", headers=notifier["headers"])
    assert res_notif_stream.status_code == 403
    assert res_notif_stream.json()["error"]["code"] == "PERMISSION_DENIED"

    # TEST D: MEMBER without camera assignment lists cameras -> live_stream_url IS NULL
    res_mem_list = client.get(f"/api/v1/cameras?group_id={group_id}", headers=member_no_cam["headers"])
    assert res_mem_list.status_code == 200
    assert res_mem_list.json()[0]["live_stream_url"] is None

    # TEST E: MEMBER without camera assignment attempts direct stream -> 403 PERMISSION_DENIED
    res_mem_stream = client.get(f"/api/v1/cameras/{cam_id}/stream", headers=member_no_cam["headers"])
    assert res_mem_stream.status_code == 403
    assert res_mem_stream.json()["error"]["code"] == "PERMISSION_DENIED"


def test_camera_watch_area_and_update(client):
    """Test updating camera info and watch area normalized bounds."""
    ts = int(time.time() * 1000) % 10000000
    leader = _register_user(client, f"098{ts:07d}", "Trưởng Vùng Quét")

    res_grp = client.post(
        "/api/v1/groups",
        json={"name": "Nhóm Vùng Quét", "address": "Cầu Giấy", "my_nickname": "Chỉ huy"},
        headers=leader["headers"],
    )
    group_id = res_grp.json()["group_id"]

    res_cam = client.post(
        "/api/v1/cameras",
        json={"group_id": group_id, "cam_name": "Cam Sân Trước", "rtsp_url": "rtsp://192.168.1.11/live"},
        headers=leader["headers"],
    )
    cam_id = res_cam.json()["cam_id"]

    # 1. Update general info
    res_patch = client.patch(
        f"/api/v1/cameras/{cam_id}",
        json={"cam_name": "Cam Sân Sau (Đã đổi)", "is_ai_enabled": False},
        headers=leader["headers"],
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["cam_name"] == "Cam Sân Sau (Đã đổi)"
    assert res_patch.json()["is_ai_enabled"] is False

    # 2. Update watch area
    area_payload = {
        "left": 0.2,
        "top": 0.2,
        "width": 0.6,
        "height": 0.6,
    }
    res_area = client.put(
        f"/api/v1/cameras/{cam_id}/watch-area",
        json=area_payload,
        headers=leader["headers"],
    )
    assert res_area.status_code == 200
    assert res_area.json()["watch_area"]["width"] == 0.6


def test_trash_restore_and_permanent_delete(client):
    """
    Test 30-day trash lifecycle:
    - Manager soft deletes camera.
    - Camera is moved to trash and removed from active list.
    - Manager restores camera.
    - Manager tries to permanent delete -> 403 Forbidden.
    - Leader permanently purges camera -> 200 OK.
    """
    ts = int(time.time() * 1000) % 10000000
    leader = _register_user(client, f"099{ts:07d}", "Trưởng Ban Thùng Rác")
    manager = _register_user(client, f"091{ts:07d}", "Phó Ban Thùng Rác")

    res_grp = client.post(
        "/api/v1/groups",
        json={"name": "Khu Phố Thùng Rác", "address": "Ba Đình", "my_nickname": "Trưởng Ban"},
        headers=leader["headers"],
    )
    group_id = res_grp.json()["group_id"]

    # Invite manager
    inv = client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"phone_number": manager["phone"], "role": "MEMBER_MANAGER", "nickname": "Phó Ban"},
        headers=leader["headers"],
    ).json()
    client.post(f"/api/v1/invitations/{inv['invitation_id']}/accept", headers=manager["headers"])

    # Create camera
    res_cam = client.post(
        "/api/v1/cameras",
        json={"group_id": group_id, "cam_name": "Camera Bãi Xe", "rtsp_url": "rtsp://192.168.1.12/live"},
        headers=leader["headers"],
    )
    cam_id = res_cam.json()["cam_id"]

    # 1. Soft delete by Manager
    res_del = client.delete(f"/api/v1/cameras/{cam_id}", headers=manager["headers"])
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"
    assert "purge_at" in res_del.json()

    # Active list should be empty
    active_cams = client.get(f"/api/v1/cameras?group_id={group_id}", headers=leader["headers"]).json()
    assert len(active_cams) == 0

    # Trash list should contain the camera
    trash_cams = client.get(f"/api/v1/cameras/trash?group_id={group_id}", headers=manager["headers"]).json()
    assert len(trash_cams) == 1
    assert trash_cams[0]["cam_id"] == cam_id

    # 2. Restore camera by Manager
    res_restore = client.post(f"/api/v1/cameras/{cam_id}/restore", headers=manager["headers"])
    assert res_restore.status_code == 200

    # Camera back in active list
    active_again = client.get(f"/api/v1/cameras?group_id={group_id}", headers=leader["headers"]).json()
    assert len(active_again) == 1

    # 3. Manager tries to permanently delete -> 403 Forbidden
    res_perm_mgr = client.delete(f"/api/v1/cameras/{cam_id}/permanent", headers=manager["headers"])
    assert res_perm_mgr.status_code == 403
    assert res_perm_mgr.json()["error"]["code"] == "PERMISSION_DENIED"

    # 4. Leader permanently purges camera -> 200 OK
    res_perm_ldr = client.delete(f"/api/v1/cameras/{cam_id}/permanent", headers=leader["headers"])
    assert res_perm_ldr.status_code == 200

    # Camera no longer exists anywhere
    res_get_deleted = client.get(f"/api/v1/cameras/{cam_id}", headers=leader["headers"])
    assert res_get_deleted.status_code == 404


def test_camera_remove_rtsp_keeps_camera(client):
    """DELETE /cameras/{id}/rtsp: the camera stays (SIGNAL_LOST, has_rtsp false) until a new link is set."""
    ts = int(time.time() * 1000) % 10000000
    leader = _register_user(client, f"096{ts:07d}", "Trưởng Nhóm RTSP")
    group_id = client.post(
        "/api/v1/groups",
        json={"name": "Khu phố RTSP", "address": "Quận 3", "my_nickname": "Trưởng"},
        headers=leader["headers"],
    ).json()["group_id"]
    subgroup_id = client.post(
        f"/api/v1/groups/{group_id}/subgroups",
        json={"name": "Ngõ 7", "description": ""},
        headers=leader["headers"],
    ).json()["subgroup_id"]
    cam_id = client.post(
        "/api/v1/cameras",
        json={
            "group_id": group_id,
            "subgroup_id": subgroup_id,
            "cam_name": "Camera Ngõ 7",
            "rtsp_url": "rtsp://admin:123456@192.168.1.20:554/live",
        },
        headers=leader["headers"],
    ).json()["cam_id"]

    res = client.delete(f"/api/v1/cameras/{cam_id}/rtsp", headers=leader["headers"])
    assert res.status_code == 200
    body = res.json()
    assert body["cam_id"] == cam_id
    assert body["status"] == "SIGNAL_LOST"
    assert body["has_rtsp"] is False

    detail = client.get(f"/api/v1/cameras/{cam_id}", headers=leader["headers"]).json()
    assert detail["cam_name"] == "Camera Ngõ 7"
    assert detail["status"] == "SIGNAL_LOST"
    assert detail["has_rtsp"] is False
    assert get_camera_repo().get_camera(cam_id).rtsp_url == ""

    # A new link (I8 "Thêm lại RTSP") brings it back.
    res_patch = client.patch(
        f"/api/v1/cameras/{cam_id}",
        json={"rtsp_url": "rtsp://admin:123456@192.168.1.21:554/live"},
        headers=leader["headers"],
    )
    assert res_patch.status_code == 200
    detail = client.get(f"/api/v1/cameras/{cam_id}", headers=leader["headers"]).json()
    assert detail["has_rtsp"] is True

    # Not for members.
    member = _register_user(client, f"097{ts:07d}", "Thành Viên RTSP")
    res_forbidden = client.delete(f"/api/v1/cameras/{cam_id}/rtsp", headers=member["headers"])
    assert res_forbidden.status_code == 403
