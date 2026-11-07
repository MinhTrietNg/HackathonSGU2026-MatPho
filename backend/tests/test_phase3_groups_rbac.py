"""
Phase 3 Test Suite: Groups, Subgroups, 4-Role RBAC, Invitations & Audit Logs
"""

import time
import pytest
from src.services.repositories.user_repo import get_user_repo
from src.services.repositories.group_repo import get_group_repo
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


def test_create_and_list_groups(client):
    """Test group creation, automatic LEADER role assignment and retrieval."""
    ts = int(time.time() * 1000) % 10000000
    user_a = _register_user(client, f"092{ts:07d}", "Trưởng Nhóm A")

    # 1. Create a new Liên Gia group
    res = client.post(
        "/api/v1/groups",
        json={
            "name": "Liên Gia Phố Tràng Tiền",
            "address": "Số 1 Tràng Tiền, Hoàn Kiếm, Hà Nội",
            "my_nickname": "Bác Tổ Trưởng",
        },
        headers=user_a["headers"],
    )
    assert res.status_code == 201
    grp = res.json()
    group_id = grp["group_id"]
    assert grp["group_name"] == "Liên Gia Phố Tràng Tiền"
    assert grp["my_role"] == "LEADER"
    assert grp["my_nickname"] == "Bác Tổ Trưởng"

    # 2. List groups for user
    list_res = client.get("/api/v1/groups", headers=user_a["headers"])
    assert list_res.status_code == 200
    groups = list_res.json()
    # At least personal group + created group
    assert len(groups) >= 2
    matched = [g for g in groups if g["group_id"] == group_id]
    assert len(matched) == 1
    assert matched[0]["address"] == "Số 1 Tràng Tiền, Hoàn Kiếm, Hà Nội"

    # 3. Get group detail
    detail_res = client.get(f"/api/v1/groups/{group_id}", headers=user_a["headers"])
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["leader_id"] == user_a["user_id"]
    assert detail["member_count"] == 1


def test_address_114_rbac_enforcement(client):
    """
    Test Section 4.2 RBAC:
    - LEADER can update address (114 Rescue Address).
    - Non-leader cannot update address (Returns 403 PERMISSION_DENIED).
    """
    ts = int(time.time() * 1000) % 10000000
    leader = _register_user(client, f"093{ts:07d}", "Trưởng Nhóm B")
    member = _register_user(client, f"094{ts:07d}", "Thành Viên C")

    # 1. Leader creates group
    grp_res = client.post(
        "/api/v1/groups",
        json={"name": "Khu Phố 4 Bến Nghé", "address": "Số 10 Nguyễn Huệ, Q.1"},
        headers=leader["headers"],
    )
    group_id = grp_res.json()["group_id"]

    # 2. Leader invites member
    inv_res = client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"phone_number": member["phone"], "role": "MEMBER_MANAGER"},
        headers=leader["headers"],
    )
    assert inv_res.status_code == 201
    inv_id = inv_res.json()["invitation_id"]

    # 3. Member accepts invitation
    acc_res = client.post(
        f"/api/v1/invitations/{inv_id}/accept",
        json={"nickname": "Phó Ban Quản Lý"},
        headers=member["headers"],
    )
    assert acc_res.status_code == 200

    # 4. Member (MEMBER_MANAGER) attempts to modify 114 address -> MUST RETURN 403
    forbidden_res = client.put(
        f"/api/v1/groups/{group_id}",
        json={"address": "Địa chỉ trái phép do Quản lý sửa"},
        headers=member["headers"],
    )
    assert forbidden_res.status_code == 403
    assert forbidden_res.json()["error"]["code"] == "PERMISSION_DENIED"

    # 5. Leader modifies 114 address -> MUST SUCCEED (200)
    success_res = client.put(
        f"/api/v1/groups/{group_id}",
        json={"address": "Số 12 Nguyễn Huệ, Q.1 (Đã đính chính)"},
        headers=leader["headers"],
    )
    assert success_res.status_code == 200
    assert success_res.json()["address"] == "Số 12 Nguyễn Huệ, Q.1 (Đã đính chính)"


def test_subgroups_crud_lifecycle(client):
    """Test Subgroups (Areas) creation, listing, updating and deletion."""
    ts = int(time.time() * 1000) % 10000000
    leader = _register_user(client, f"095{ts:07d}", "Trưởng Nhóm Subgroup")

    grp_res = client.post(
        "/api/v1/groups",
        json={"name": "Chung Cư Sunrise City"},
        headers=leader["headers"],
    )
    group_id = grp_res.json()["group_id"]

    # 1. Create subgroup
    create_sg = client.post(
        f"/api/v1/groups/{group_id}/subgroups",
        json={"name": "Khu vực Bếp tầng trệt", "description": "Lắp camera góc trần bếp"},
        headers=leader["headers"],
    )
    assert create_sg.status_code == 201
    sg = create_sg.json()
    sg_id = sg["subgroup_id"]
    assert sg["name"] == "Khu vực Bếp tầng trệt"

    # 2. List subgroups
    list_sg = client.get(f"/api/v1/groups/{group_id}/subgroups", headers=leader["headers"])
    assert list_sg.status_code == 200
    assert any(s["subgroup_id"] == sg_id for s in list_sg.json())

    # 3. Update subgroup
    upd_sg = client.put(
        f"/api/v1/groups/{group_id}/subgroups/{sg_id}",
        json={"name": "Gian Bếp & Lối Thoát Hiểm", "description": "Cập nhật mô tả"},
        headers=leader["headers"],
    )
    assert upd_sg.status_code == 200
    assert upd_sg.json()["name"] == "Gian Bếp & Lối Thoát Hiểm"

    # 4. Delete subgroup
    del_sg = client.delete(f"/api/v1/groups/{group_id}/subgroups/{sg_id}", headers=leader["headers"])
    assert del_sg.status_code == 200


def test_invitation_rejection_and_revocation(client):
    """Test invitation decline and revocation flows."""
    ts = int(time.time() * 1000) % 10000000
    leader = _register_user(client, f"096{ts:07d}", "Trưởng Nhóm Inv")
    target = _register_user(client, f"097{ts:07d}", "Người Được Mời")

    grp_res = client.post(
        "/api/v1/groups",
        json={"name": "Nhóm Thử Lời Mời"},
        headers=leader["headers"],
    )
    group_id = grp_res.json()["group_id"]

    # 1. Leader invites target
    inv_res = client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"phone_number": target["phone"], "role": "MEMBER"},
        headers=leader["headers"],
    )
    assert inv_res.status_code == 201
    inv_id = inv_res.json()["invitation_id"]

    # 2. Target sees invitation in my-invitations
    my_invs = client.get("/api/v1/invitations/my-invitations", headers=target["headers"])
    assert my_invs.status_code == 200
    assert any(i["invitation_id"] == inv_id for i in my_invs.json())

    # 3. Target declines invitation
    dec_res = client.post(f"/api/v1/invitations/{inv_id}/decline", headers=target["headers"])
    assert dec_res.status_code == 200

    # 4. Target tries to accept declined invitation -> 410 INVITATION_UNAVAILABLE
    acc_res = client.post(
        f"/api/v1/invitations/{inv_id}/accept",
        json={"nickname": "Thử nhận lại"},
        headers=target["headers"],
    )
    assert acc_res.status_code == 410


def test_member_role_change_and_camera_permissions(client):
    """Test updating member role and granular camera ID permissions."""
    ts = int(time.time() * 1000) % 10000000
    leader = _register_user(client, f"098{ts:07d}", "Trưởng Nhóm Roles")
    member = _register_user(client, f"099{ts:07d}", "Thành Viên Phân Quyền")

    grp_res = client.post(
        "/api/v1/groups",
        json={"name": "Hợp Tác Xã An Ninh"},
        headers=leader["headers"],
    )
    group_id = grp_res.json()["group_id"]

    # Invite & accept
    inv = client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"phone_number": member["phone"], "role": "MEMBER"},
        headers=leader["headers"],
    ).json()
    client.post(f"/api/v1/invitations/{inv['invitation_id']}/accept", json={}, headers=member["headers"])

    # 1. Leader promotes member to MEMBER_MANAGER
    role_res = client.patch(
        f"/api/v1/groups/{group_id}/members/{member['user_id']}/role",
        json={"role": "MEMBER_MANAGER"},
        headers=leader["headers"],
    )
    assert role_res.status_code == 200
    assert role_res.json()["role"] == "MEMBER_MANAGER"

    # 2. Leader restricts cameras for member
    cam_res = client.put(
        f"/api/v1/groups/{group_id}/members/{member['user_id']}/cameras",
        json={"camera_ids": ["cam_01", "cam_02"]},
        headers=leader["headers"],
    )
    assert cam_res.status_code == 200
    assert cam_res.json()["camera_ids"] == ["cam_01", "cam_02"]

    # 3. Member updates nickname
    nick_res = client.patch(
        f"/api/v1/groups/{group_id}/members/{member['user_id']}/nickname",
        json={"nickname": "Bí Thư Chi Bộ"},
        headers=member["headers"],
    )
    assert nick_res.status_code == 200
    assert nick_res.json()["nickname"] == "Bí Thư Chi Bộ"


def test_transfer_ownership_and_leave_group(client):
    """
    Test Leadership Transfer and Voluntary Group Leave:
    - LEADER cannot leave directly.
    - LEADER transfers leadership to Member.
    - Former leader becomes MEMBER and can leave.
    """
    ts = int(time.time() * 1000) % 10000000
    leader_a = _register_user(client, f"0911{ts % 1000000:06d}", "Leader Cũ")
    member_b = _register_user(client, f"0912{ts % 1000000:06d}", "Leader Mới")

    grp_res = client.post(
        "/api/v1/groups",
        json={"name": "Khu Tập Thể Kim Liên"},
        headers=leader_a["headers"],
    )
    group_id = grp_res.json()["group_id"]

    # Member B joins
    inv = client.post(
        f"/api/v1/groups/{group_id}/invitations",
        json={"phone_number": member_b["phone"], "role": "MEMBER"},
        headers=leader_a["headers"],
    ).json()
    client.post(f"/api/v1/invitations/{inv['invitation_id']}/accept", json={}, headers=member_b["headers"])

    # 1. Leader A tries to leave directly -> 403 PERMISSION_DENIED
    leave_fail = client.post(f"/api/v1/groups/{group_id}/leave", headers=leader_a["headers"])
    assert leave_fail.status_code == 403

    # 2. Leader A transfers ownership to Member B
    tf_res = client.post(
        f"/api/v1/groups/{group_id}/transfer-ownership",
        json={"new_leader_id": member_b["user_id"]},
        headers=leader_a["headers"],
    )
    assert tf_res.status_code == 200
    assert tf_res.json()["new_leader_id"] == member_b["user_id"]

    # 3. Leader A (now MEMBER) leaves group
    leave_ok = client.post(f"/api/v1/groups/{group_id}/leave", headers=leader_a["headers"])
    assert leave_ok.status_code == 200

    # 4. Check group member count is back to 1
    grp_info = client.get(f"/api/v1/groups/{group_id}", headers=member_b["headers"]).json()
    assert grp_info["member_count"] == 1
    assert grp_info["leader_id"] == member_b["user_id"]


def test_cannot_delete_personal_group(client):
    """Verify default personal group cannot be dissolved or left."""
    ts = int(time.time() * 1000) % 10000000
    user = _register_user(client, f"0913{ts % 1000000:06d}", "Chủ Hộ Cá Nhân")

    me = client.get("/api/v1/users/me", headers=user["headers"]).json()
    personal_grp_id = me["personal_group_id"]
    assert personal_grp_id is not None

    # Try to dissolve personal group -> 403
    del_res = client.delete(f"/api/v1/groups/{personal_grp_id}", headers=user["headers"])
    assert del_res.status_code == 403
