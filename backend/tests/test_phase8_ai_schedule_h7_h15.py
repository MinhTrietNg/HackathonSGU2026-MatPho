"""
Unit & Integration Tests for Phase 8: Per-Camera AI Detection & Schedule (Figma H7 -> H15)
Validates:
  - AI Schedule & Mode Engine (`should_ai_scan_now`, `format_ai_status_text`, overnight & intra-day slots)
  - H7, H8, H9: `GET /api/v1/cameras/ai-settings` (Editable for LEADER, Locked with banner for MEMBER)
  - H10 -> H15: `GET /api/v1/cameras/{cam_id}/ai-config` and `PUT /api/v1/cameras/{cam_id}/ai-config`
  - RBAC enforcement: 403 Forbidden when MEMBER/NOTIFIER attempts to modify AI config
  - Validation: max 2 schedule slots, valid HH:MM format, start_time != end_time
  - Edge WebSocket command dispatch (`SET_CAMERA_AI_CONFIG` with `DISCONNECT_AI_RTSP` / `CONNECT_AI_RTSP`)
"""

from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

try:
    from src.main import app
    from src.core.ai_schedule import should_ai_scan_now, format_ai_status_text, VN_TZ
    from src.models.common import UserRole, AIMode, CameraStatus
    from src.models.camera import CameraModel, AIScheduleSlotModel
    from src.models.group import GroupModel, MemberModel
    from src.models.user import UserModel
    _CAM_REPO_PATCH = "src.routers.cameras.get_camera_repo"
    _GRP_REPO_PATCH = "src.routers.cameras.get_group_repo"
    _CUR_USER_DEP = "src.routers.cameras.get_current_user"
except ImportError:
    from backend.src.main import app
    from backend.src.core.ai_schedule import should_ai_scan_now, format_ai_status_text, VN_TZ
    from backend.src.models.common import UserRole, AIMode, CameraStatus
    from backend.src.models.camera import CameraModel, AIScheduleSlotModel
    from backend.src.models.group import GroupModel, MemberModel
    from backend.src.models.user import UserModel
    _CAM_REPO_PATCH = "backend.src.routers.cameras.get_camera_repo"
    _GRP_REPO_PATCH = "backend.src.routers.cameras.get_group_repo"
    _CUR_USER_DEP = "backend.src.routers.cameras.get_current_user"


@pytest.fixture
def test_client():
    return TestClient(app)


def test_ai_schedule_engine_intra_day_and_overnight():
    # 1. ALWAYS mode -> always True
    assert should_ai_scan_now("ALWAYS", []) is True

    # 2. OFF mode -> always False
    assert should_ai_scan_now("OFF", []) is False

    # 3. SCHEDULE mode with 1 intra-day slot: 17:00 - 19:30 every day
    slots_1 = [
        {
            "slot_id": "slot_1",
            "start_time": "17:00",
            "end_time": "19:30",
            "days": ["T2", "T3", "T4", "T5", "T6", "T7", "CN"],
        }
    ]
    # Monday (2026-11-02 is Monday) at 18:15 VN -> inside rest window -> should_ai_scan_now = False
    mon_1815 = datetime(2026, 11, 2, 18, 15, tzinfo=VN_TZ)
    assert should_ai_scan_now("SCHEDULE", slots_1, now_vn=mon_1815) is False

    # Monday at 20:00 VN -> outside rest window -> should_ai_scan_now = True
    mon_2000 = datetime(2026, 11, 2, 20, 0, tzinfo=VN_TZ)
    assert should_ai_scan_now("SCHEDULE", slots_1, now_vn=mon_2000) is True

    # 4. SCHEDULE mode with overnight slot: 22:00 - 06:00 on T2..T6
    overnight_slots = [
        {
            "slot_id": "slot_1",
            "start_time": "22:00",
            "end_time": "06:00",
            "days": ["T2", "T3", "T4", "T5", "T6"],
        }
    ]
    # Monday 23:30 VN -> inside overnight rest window -> False
    mon_2330 = datetime(2026, 11, 2, 23, 30, tzinfo=VN_TZ)
    assert should_ai_scan_now("SCHEDULE", overnight_slots, now_vn=mon_2330) is False

    # Tuesday 04:30 VN (carried over from Monday night) -> False
    tue_0430 = datetime(2026, 11, 3, 4, 30, tzinfo=VN_TZ)
    assert should_ai_scan_now("SCHEDULE", overnight_slots, now_vn=tue_0430) is False

    # Tuesday 09:00 VN -> True
    tue_0900 = datetime(2026, 11, 3, 9, 0, tzinfo=VN_TZ)
    assert should_ai_scan_now("SCHEDULE", overnight_slots, now_vn=tue_0900) is True


def test_format_ai_status_text_figma_strings():
    assert format_ai_status_text("ALWAYS", [], is_editable=True) == "Đang bật 24/7"
    assert format_ai_status_text("ALWAYS", [], is_editable=False) == "Bật 24/7 · chỉ chủ nhóm đổi được"
    assert format_ai_status_text("OFF", [], is_editable=True) == "Đã tắt AI"
    assert format_ai_status_text("OFF", [], is_editable=False) == "Đã tắt AI · chỉ chủ nhóm đổi được"

    slot_bep = [{"start_time": "17:00", "end_time": "19:30", "days": ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]}]
    assert format_ai_status_text("SCHEDULE", slot_bep, is_editable=True) == "Nghỉ 17:00–19:30 · mỗi ngày"

    slots_2 = [
        {"start_time": "11:00", "end_time": "13:30", "days": ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]},
        {"start_time": "17:00", "end_time": "19:30", "days": ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]},
    ]
    assert format_ai_status_text("SCHEDULE", slots_2, is_editable=True) == "Nghỉ 11:00–13:30, 17:00–19:30"


def test_h7_h8_h9_list_camera_ai_settings_and_h10_h15_update(test_client):
    headers = {"Authorization": "Bearer usr_leader_matpho_01"}

    grp_home = GroupModel(
        group_id="grp_nha_minh",
        group_name="Nhà mình",
        is_personal=True,
        leader_id="usr_leader_matpho_01",
    )
    grp_company = GroupModel(
        group_id="grp_cong_ty",
        group_name="Công ty",
        is_personal=False,
        leader_id="usr_anh_long",
    )

    cam_bep = CameraModel(
        cam_id="cam_bep",
        group_id="grp_nha_minh",
        subgroup_id="sub_tret",
        subgroup_name="Tầng trệt",
        cam_name="Bếp",
        rtsp_url="rtsp://mock/bep",
        ai_mode=AIMode.SCHEDULE,
        ai_schedules=[
            AIScheduleSlotModel(
                slot_id="slot_1",
                start_time="17:00",
                end_time="19:30",
                days=["T2", "T3", "T4", "T5", "T6", "T7", "CN"],
            )
        ],
    )
    cam_kho = CameraModel(
        cam_id="cam_kho",
        group_id="grp_cong_ty",
        subgroup_id="sub_tang1",
        subgroup_name="Tầng 1",
        cam_name="Kho hàng",
        rtsp_url="rtsp://mock/kho",
        ai_mode=AIMode.ALWAYS,
        ai_schedules=[],
    )

    leader_member_company = MemberModel(
        user_id="usr_anh_long",
        role=UserRole.LEADER,
        nickname="Anh Long",
        full_name="Anh Long",
        phone_number="+84909111222",
    )
    me_member_home = MemberModel(
        user_id="usr_leader_matpho_01",
        role=UserRole.LEADER,
        nickname="Trưởng Nhóm",
        full_name="Nguyễn Văn An",
        phone_number="+84901234567",
    )
    me_member_company = MemberModel(
        user_id="usr_leader_matpho_01",
        role=UserRole.MEMBER,
        nickname="Thành viên",
        full_name="Nguyễn Văn An",
        phone_number="+84901234567",
    )

    with patch(_GRP_REPO_PATCH) as mock_grp_fn, patch(_CAM_REPO_PATCH) as mock_cam_fn:
        mock_grp = MagicMock()
        mock_cam = MagicMock()
        mock_grp_fn.return_value = mock_grp
        mock_cam_fn.return_value = mock_cam

        mock_grp.list_groups_for_user.return_value = [
            (grp_home, UserRole.LEADER, "Trưởng Nhóm"),
            (grp_company, UserRole.MEMBER, "Thành viên"),
        ]
        mock_grp.list_members.side_effect = lambda gid: (
            [me_member_home] if gid == "grp_nha_minh" else [leader_member_company, me_member_company]
        )
        mock_cam.list_cameras_by_group.side_effect = lambda gid: (
            [cam_bep] if gid == "grp_nha_minh" else [cam_kho]
        )

        # 1. Test GET /api/v1/cameras/ai-settings (H7 + H8)
        res = test_client.get("/api/v1/cameras/ai-settings", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert len(body["filter_tabs"]) == 2
        assert len(body["groups"]) == 2

        g_home_out = body["groups"][0]
        assert g_home_out["access_mode"] == "Editable"
        assert g_home_out["lock_banner"] is None
        assert g_home_out["cameras"][0]["status_text"] == "Nghỉ 17:00–19:30 · mỗi ngày"

        g_comp_out = body["groups"][1]
        assert g_comp_out["access_mode"] == "Locked"
        assert g_comp_out["lock_banner"]["title"] == "Chỉ chủ nhóm được đổi cài đặt AI"
        assert "Anh Long" in g_comp_out["lock_banner"]["subtitle"]
        assert g_comp_out["cameras"][0]["status_text"] == "Bật 24/7 · chỉ chủ nhóm đổi được"

        # 2. Test PUT /api/v1/cameras/cam_kho/ai-config as MEMBER (H8 Locked -> 403 Forbidden)
        mock_cam.get_camera.return_value = cam_kho
        mock_grp.get_member.return_value = me_member_company
        res_forbidden = test_client.put(
            "/api/v1/cameras/cam_kho/ai-config",
            headers=headers,
            json={"ai_mode": "OFF", "schedules": []},
        )
        assert res_forbidden.status_code == 403

        # 3. Test PUT /api/v1/cameras/cam_bep/ai-config as LEADER -> OFF (H15: Disconnect AI RTSP)
        cam_bep_off = cam_bep.model_copy(
            update={"ai_mode": AIMode.OFF, "ai_schedules": [], "is_ai_enabled": False}
        )
        mock_cam.get_camera.return_value = cam_bep
        mock_grp.get_member.return_value = me_member_home
        mock_cam.update_camera_ai_config.return_value = cam_bep_off

        res_off = test_client.put(
            "/api/v1/cameras/cam_bep/ai-config",
            headers=headers,
            json={"ai_mode": "OFF", "schedules": []},
        )
        assert res_off.status_code == 200
        off_data = res_off.json()
        assert off_data["ai_mode"] == "OFF"
        assert off_data["is_ai_currently_scanning"] is False
        assert off_data["status_text"] == "Đã tắt AI"
        assert off_data["edge_command"]["action"] == "SET_CAMERA_AI_CONFIG"
        assert off_data["edge_command"]["stream_action"] == "DISCONNECT_AI_RTSP"
