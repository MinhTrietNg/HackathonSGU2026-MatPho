"""
Group, Member & Subgroup Management Router for Mắt Phố
Phase 3: Quản trị nhóm liên gia, vị trí Subgroup & Phân quyền 4 vai trò RBAC
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from ..core.security import get_current_user
from ..core.exceptions import (
    AppException,
    NotFoundException,
    PermissionDeniedException,
    ConflictException,
    PhoneNotRegisteredException,
)
from ..core.formatters import format_iso_utc, normalize_phone_e164
from ..models.user import UserModel
from ..models.common import UserRole
from ..models.group import (
    GroupResponseDTO,
    MemberModel,
    MemberResponseDTO,
    SubgroupModel,
    CreateSubgroupRequest,
    UpdateSubgroupRequest,
    CreateGroupRequest,
    UpdateGroupRequest,
    TransferOwnershipRequest,
    InviteMemberRequest,
    ChangeMemberRoleRequest,
    AssignCamerasRequest,
    ChangeNicknameRequest,
)
from ..services.repositories.group_repo import get_group_repo
from ..services.repositories.user_repo import get_user_repo

logger = logging.getLogger("backend.routers.groups")

router = APIRouter(prefix="/groups", tags=["Groups"])


def serialize_member(m: MemberModel, current_user_id: str) -> Dict[str, Any]:
    return {
        "user_id": m.user_id,
        "full_name": m.full_name,
        "phone_number": m.phone_number,
        "role": m.role.value if hasattr(m.role, "value") else str(m.role),
        "nickname": m.nickname,
        "note": m.note,
        "camera_ids": m.camera_ids,
        "joined_at": format_iso_utc(m.joined_at),
        "is_you": m.user_id == current_user_id,
    }


def check_group_permission(group_id: str, current_user_id: str, required_roles: List[UserRole]) -> MemberModel:
    repo = get_group_repo()
    member = repo.get_member(group_id, current_user_id)
    if not member:
        raise PermissionDeniedException("Bạn không phải thành viên của nhóm này.")
    if member.role not in required_roles:
        raise PermissionDeniedException("Bạn không có quyền thực hiện hành động này.")
    return member


# ==============================================================================
# 1. GROUP LIFECYCLE (Nhóm liên gia & cơ sở)
# ==============================================================================

@router.get("", summary="List groups current user belongs to")
def list_groups(current_user: UserModel = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """List all groups the authenticated user is a member of."""
    repo = get_group_repo()
    group_tuples = repo.list_groups_for_user(current_user.user_id)
    results = []
    for g, role, nickname in group_tuples:
        results.append({
            "group_id": g.group_id,
            "group_name": g.group_name,
            "is_personal": g.is_personal,
            "leader_id": g.leader_id,
            "address": g.address,
            "member_count": g.member_count,
            "camera_count": g.camera_count,
            "my_role": role,
            "my_nickname": nickname,
            "created_at": format_iso_utc(g.created_at),
            "updated_at": format_iso_utc(g.updated_at),
        })
    return results


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a new Group")
def create_group(
    payload: CreateGroupRequest,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Create a new Group (Family, Liên Gia, or Facility).
    Creator is atomically assigned the LEADER role.
    """
    repo = get_group_repo()
    group = repo.create_group(
        group_name=payload.name,
        leader_id=current_user.user_id,
        address=payload.address,
        my_nickname=payload.my_nickname,
    )
    return {
        "group_id": group.group_id,
        "group_name": group.group_name,
        "is_personal": False,
        "leader_id": group.leader_id,
        "address": group.address,
        "member_count": 1,
        "camera_count": 0,
        "my_role": "LEADER",
        "my_nickname": payload.my_nickname,
        "created_at": format_iso_utc(group.created_at),
    }


@router.get("/invitations/me", summary="Alias for list my invitations (Flutter Client)")
def get_my_group_invitations(current_user: UserModel = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """Alias for GET /api/v1/invitations/my-invitations."""
    from .invitations import list_my_invitations
    return list_my_invitations(current_user=current_user)


@router.get("/{group_id}", summary="Get group details")
def get_group_detail(
    group_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve details of a group, including member count and 114 emergency address."""
    repo = get_group_repo()
    member = repo.get_member(group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không phải thành viên của nhóm này.")
    group = repo.get_group(group_id)
    if not group:
        raise NotFoundException("Không tìm thấy nhóm.", code="GROUP_NOT_FOUND")

    return {
        "group_id": group.group_id,
        "group_name": group.group_name,
        "is_personal": group.is_personal,
        "leader_id": group.leader_id,
        "address": group.address,
        "member_count": group.member_count,
        "camera_count": group.camera_count,
        "my_role": member.role.value if hasattr(member.role, "value") else str(member.role),
        "my_nickname": member.nickname,
        "created_at": format_iso_utc(group.created_at),
        "updated_at": format_iso_utc(group.updated_at),
    }


@router.put("/{group_id}", summary="Update group information")
@router.patch("/{group_id}", summary="Partial update group information")
def update_group(
    group_id: str,
    payload: UpdateGroupRequest,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Update group name and/or 114 emergency address.
    RBAC:
      - Updating address: ONLY LEADER is allowed (Section 4.2 in API_SPECIFICATION.md / ADR 0008).
      - Updating name: LEADER or MEMBER_MANAGER is allowed.
    """
    repo = get_group_repo()
    member = repo.get_member(group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không phải thành viên của nhóm này.")

    # Check 114 address restriction
    if payload.address is not None:
        if member.role != UserRole.LEADER:
            raise PermissionDeniedException("Chỉ Trưởng nhóm (LEADER) mới có quyền cập nhật địa chỉ cứu nạn 114.")

    # Name update requires at least MEMBER_MANAGER
    if payload.name is not None:
        if member.role not in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
            raise PermissionDeniedException("Chỉ Trưởng nhóm hoặc Người quản lý mới được đổi tên nhóm.")

    updated_group = repo.update_group(
        group_id=group_id,
        name=payload.name,
        address=payload.address,
    )
    if not updated_group:
        raise NotFoundException("Không tìm thấy nhóm.", code="GROUP_NOT_FOUND")

    return {
        "group_id": updated_group.group_id,
        "group_name": updated_group.group_name,
        "is_personal": updated_group.is_personal,
        "leader_id": updated_group.leader_id,
        "address": updated_group.address,
        "member_count": updated_group.member_count,
        "camera_count": updated_group.camera_count,
        "updated_at": format_iso_utc(updated_group.updated_at),
    }


@router.delete("/{group_id}", summary="Dissolve/Delete group (LEADER only)")
def delete_group(
    group_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Dissolve a group. Only the LEADER can dissolve the group.
    Personal groups cannot be dissolved.
    """
    check_group_permission(group_id, current_user.user_id, [UserRole.LEADER])
    repo = get_group_repo()
    try:
        repo.delete_group(group_id, current_user.user_id)
    except ValueError as e:
        if str(e) == "CANNOT_DELETE_PERSONAL_GROUP":
            raise AppException("FORBIDDEN", "Không thể giải tán nhóm cá nhân mặc định.", status_code=403)
        raise NotFoundException("Không tìm thấy nhóm.", code="GROUP_NOT_FOUND")

    return {"status": "success", "message": "Đã giải tán nhóm thành công"}


@router.post("/{group_id}/leave", summary="Leave group")
def leave_group(
    group_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Voluntarily leave a group.
    LEADER cannot leave before transferring leadership to another member.
    """
    repo = get_group_repo()
    member = repo.get_member(group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không phải thành viên của nhóm này.")
    if member.role == UserRole.LEADER:
        raise AppException(
            "PERMISSION_DENIED",
            "Trưởng nhóm không thể tự rời nhóm. Hãy chuyển giao quyền Trưởng nhóm trước khi rời hoặc giải tán nhóm.",
            status_code=403,
        )

    group = repo.get_group(group_id)
    if group and group.is_personal:
        raise AppException("FORBIDDEN", "Không thể rời khỏi nhóm cá nhân của chính bạn.", status_code=403)

    repo.remove_member(group_id, current_user.user_id)
    return {"status": "success", "message": "Đã rời khỏi nhóm thành công"}


@router.post("/{group_id}/transfer-ownership", summary="Transfer Group Leadership (LEADER only)")
def transfer_ownership(
    group_id: str,
    payload: TransferOwnershipRequest,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Transfer LEADER role to another existing member in the group.
    The former leader automatically becomes a standard MEMBER.
    """
    check_group_permission(group_id, current_user.user_id, [UserRole.LEADER])
    repo = get_group_repo()
    try:
        updated_group = repo.transfer_ownership(group_id, current_user.user_id, payload.new_leader_id)
    except ValueError as e:
        err = str(e)
        if err == "CANNOT_TRANSFER_PERSONAL_GROUP":
            raise AppException("FORBIDDEN", "Không thể chuyển giao nhóm cá nhân.", status_code=403)
        if err == "TARGET_NOT_A_MEMBER":
            raise NotFoundException("Người được chỉ định không phải thành viên nhóm này.", code="TARGET_NOT_MEMBER")
        raise AppException("VALIDATION_ERROR", f"Không thể chuyển quyền: {err}", status_code=422)

    return {
        "status": "success",
        "message": "Đã chuyển giao quyền Trưởng nhóm thành công.",
        "group_id": updated_group.group_id,
        "new_leader_id": updated_group.leader_id,
    }


# ==============================================================================
# 2. MEMBERS & 4-ROLE RBAC (Thành viên & Phân quyền)
# ==============================================================================

@router.get("/{group_id}/members", summary="List members and pending invitations")
def list_members(
    group_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """List all members and pending invitations in the group."""
    repo = get_group_repo()
    # Member must belong to group
    member = repo.get_member(group_id, current_user.user_id)
    if not member:
        raise PermissionDeniedException("Bạn không phải thành viên của nhóm này.")

    members = repo.list_members(group_id)
    invitations = repo.list_invitations(group_id)

    members_dto = [serialize_member(m, current_user.user_id) for m in members]
    invitations_dto = [
        {
            "invitation_id": inv.invitation_id,
            "phone_number": inv.phone_number,
            "role": inv.role.value if hasattr(inv.role, "value") else str(inv.role),
            "nickname": inv.nickname or inv.suggested_nickname,
            "camera_ids": inv.camera_ids,
            "camera_names": inv.camera_names or [],
            "created_at": format_iso_utc(inv.created_at),
        }
        for inv in invitations
    ]

    return {
        "members": members_dto,
        "pending_invitations": invitations_dto,
    }


@router.post("/{group_id}/invitations", status_code=status.HTTP_201_CREATED, summary="Invite member via phone number")
def invite_member(
    group_id: str,
    payload: InviteMemberRequest,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Invite a new member to the group via phone number.
    Permission: LEADER or MEMBER_MANAGER.
    """
    check_group_permission(group_id, current_user.user_id, [UserRole.LEADER, UserRole.MEMBER_MANAGER])
    repo = get_group_repo()
    user_repo = get_user_repo()

    group = repo.get_group(group_id)
    if not group:
        raise NotFoundException("Không tìm thấy nhóm.", code="GROUP_NOT_FOUND")
    if group.is_personal:
        raise AppException("FORBIDDEN", "Không thể mời thêm thành viên vào nhóm cá nhân.", status_code=403)

    phone_e164 = normalize_phone_e164(payload.phone_number)
    target_user = user_repo.get_user_by_phone(phone_e164)
    if not target_user:
        raise PhoneNotRegisteredException()

    # Check if already member
    existing_member = repo.get_member(group_id, target_user.user_id)
    if existing_member:
        raise ConflictException("Số điện thoại này đã là thành viên trong nhóm.", code="ALREADY_IN_GROUP")

    # Check if already has a pending invitation
    pending_invs = repo.list_invitations(group_id)
    if any(inv.phone_number == phone_e164 for inv in pending_invs):
        raise ConflictException("Số điện thoại này đã có lời mời đang chờ xử lý.", code="ALREADY_INVITED")

    invitation = repo.create_invitation(
        group_id=group_id,
        phone_number=phone_e164,
        role=payload.role,
        invited_by=current_user.user_id,
        nickname=payload.nickname,
        camera_ids=payload.camera_ids,
    )

    return {
        "invitation_id": invitation.invitation_id,
        "phone_number": invitation.phone_number,
        "role": invitation.role.value if hasattr(invitation.role, "value") else str(invitation.role),
        "nickname": invitation.nickname,
        "status": "PENDING",
        "created_at": format_iso_utc(invitation.created_at),
    }


@router.delete("/{group_id}/invitations/{invitation_id}", summary="Cancel pending invitation")
def cancel_invitation(
    group_id: str,
    invitation_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Revoke/Cancel a pending invitation."""
    check_group_permission(group_id, current_user.user_id, [UserRole.LEADER, UserRole.MEMBER_MANAGER])
    repo = get_group_repo()
    success = repo.cancel_invitation(group_id, invitation_id)
    if not success:
        raise NotFoundException("Không tìm thấy lời mời trong nhóm.", code="INVITATION_NOT_FOUND")
    return {"status": "success", "message": "Đã thu hồi lời mời thành công"}


@router.patch("/{group_id}/members/{user_id}/role", summary="Change member role (LEADER only)")
def change_member_role(
    group_id: str,
    user_id: str,
    payload: ChangeMemberRoleRequest,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Update member role (MEMBER_MANAGER, MEMBER, NOTIFIER).
    Only the LEADER can change member roles.
    Cannot assign LEADER role via this route (must use transfer-ownership).
    """
    check_group_permission(group_id, current_user.user_id, [UserRole.LEADER])
    repo = get_group_repo()
    group = repo.get_group(group_id)
    if not group:
        raise NotFoundException("Không tìm thấy nhóm.", code="GROUP_NOT_FOUND")

    target_member = repo.get_member(group_id, user_id)
    if not target_member:
        raise NotFoundException("Không tìm thấy thành viên trong nhóm.", code="MEMBER_NOT_FOUND")

    if user_id == group.leader_id or target_member.role == UserRole.LEADER:
        raise PermissionDeniedException("Không thể thay đổi vai trò của Trưởng nhóm (Leader).")

    if payload.role == UserRole.LEADER:
        raise PermissionDeniedException("Không thể gán vai trò Trưởng nhóm qua chức năng đổi vai trò. Hãy sử dụng chuyển quyền sở hữu.")

    repo.update_member_role(group_id, user_id, payload.role)
    updated_member = repo.get_member(group_id, user_id)
    return serialize_member(updated_member, current_user.user_id) if updated_member else {"user_id": user_id, "role": payload.role.value}


@router.put("/{group_id}/members/{user_id}/cameras", summary="Assign cameras to member")
@router.patch("/{group_id}/members/{user_id}/cameras", summary="Assign cameras to member (Patch)")
def assign_cameras(
    group_id: str,
    user_id: str,
    payload: AssignCamerasRequest,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Assign camera permissions to a member.
    null/empty = full group access; array of camera IDs = restricted access.
    Permission: LEADER or MEMBER_MANAGER.
    """
    check_group_permission(group_id, current_user.user_id, [UserRole.LEADER, UserRole.MEMBER_MANAGER])
    repo = get_group_repo()
    target_member = repo.get_member(group_id, user_id)
    if not target_member:
        raise NotFoundException("Không tìm thấy thành viên trong nhóm.", code="MEMBER_NOT_FOUND")

    if target_member.role == UserRole.LEADER:
        raise PermissionDeniedException("Trưởng nhóm luôn có toàn quyền xem tất cả camera.")

    repo.update_member_cameras(group_id, user_id, payload.camera_ids)
    updated_member = repo.get_member(group_id, user_id)
    return serialize_member(updated_member, current_user.user_id) if updated_member else {"user_id": user_id, "camera_ids": payload.camera_ids}


@router.patch("/{group_id}/members/{user_id}/nickname", summary="Change member nickname")
def change_member_nickname(
    group_id: str,
    user_id: str,
    payload: ChangeNicknameRequest,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Change member nickname. Allowed for the member themselves or LEADER/MEMBER_MANAGER."""
    repo = get_group_repo()
    if current_user.user_id != user_id:
        check_group_permission(group_id, current_user.user_id, [UserRole.LEADER, UserRole.MEMBER_MANAGER])

    repo.update_member_nickname(group_id, user_id, payload.nickname)
    member = repo.get_member(group_id, user_id)
    return serialize_member(member, current_user.user_id) if member else {"user_id": user_id, "nickname": payload.nickname}


@router.delete("/{group_id}/members/{user_id}", summary="Remove member from group")
def remove_member(
    group_id: str,
    user_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Remove a member from the group. Permission: LEADER or MEMBER_MANAGER."""
    check_group_permission(group_id, current_user.user_id, [UserRole.LEADER, UserRole.MEMBER_MANAGER])
    repo = get_group_repo()
    group = repo.get_group(group_id)
    if not group:
        raise NotFoundException("Không tìm thấy nhóm.", code="GROUP_NOT_FOUND")

    if user_id == group.leader_id:
        raise PermissionDeniedException("Không thể xóa Trưởng nhóm (Leader) khỏi nhóm.")

    if current_user.user_id == user_id:
        raise AppException("VALIDATION_ERROR", "Để tự rời nhóm, vui lòng sử dụng API /groups/{id}/leave.", status_code=400)

    success = repo.remove_member(group_id, user_id)
    if not success:
        # Check if user_id was an invitation_id
        if user_id.startswith("inv_"):
            inv_success = repo.cancel_invitation(group_id, user_id)
            if inv_success:
                return {"status": "success", "message": "Đã thu hồi lời mời thành công"}
        raise NotFoundException("Không tìm thấy thành viên trong nhóm.", code="MEMBER_NOT_FOUND")

    return {"status": "success", "message": "Đã xóa thành viên khỏi nhóm thành công"}


@router.get("/{group_id}/cameras", summary="List cameras belonging to group (Alias)")
def get_group_cameras(
    group_id: str,
    subgroup_id: Optional[str] = Query(None),
    current_user: UserModel = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """List cameras for a specific group. Detailed implementation in Phase 4."""
    check_group_permission(group_id, current_user.user_id, [
        UserRole.LEADER,
        UserRole.MEMBER_MANAGER,
        UserRole.MEMBER,
        UserRole.NOTIFIER,
    ])
    # Placeholder returning empty camera list until Phase 4 Cameras implementation
    return []


@router.get("/{group_id}/audit-logs", summary="List group security audit logs")
def get_group_audit_logs(
    group_id: str,
    limit: int = Query(50, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve immutable audit log history for group operations."""
    check_group_permission(group_id, current_user.user_id, [UserRole.LEADER, UserRole.MEMBER_MANAGER])
    repo = get_group_repo()
    logs = repo.list_audit_logs(group_id, limit=limit)
    return {
        "group_id": group_id,
        "items": logs,
        "total": len(logs),
    }


# ==============================================================================
# 3. SUBGROUPS / LOCATIONS (Khu vực / Vị trí lắp đặt)
# ==============================================================================

@router.get("/{group_id}/subgroups", summary="List subgroups / areas in group")
def list_subgroups(
    group_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """List all user-defined installation areas (subgroups) within the group."""
    check_group_permission(group_id, current_user.user_id, [
        UserRole.LEADER,
        UserRole.MEMBER_MANAGER,
        UserRole.MEMBER,
        UserRole.NOTIFIER,
    ])
    repo = get_group_repo()
    subgroups = repo.list_subgroups(group_id)
    return [
        {
            "subgroup_id": s.subgroup_id,
            "name": s.subgroup_name,
            "description": s.description,
            "camera_count": s.camera_count,
            "created_at": format_iso_utc(s.created_at),
        }
        for s in subgroups
    ]


@router.post("/{group_id}/subgroups", status_code=status.HTTP_201_CREATED, summary="Create a new subgroup / area")
def create_subgroup(
    group_id: str,
    payload: CreateSubgroupRequest,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Create a new installation area / subgroup (e.g., 'Bếp tầng 1')."""
    check_group_permission(group_id, current_user.user_id, [UserRole.LEADER, UserRole.MEMBER_MANAGER])
    repo = get_group_repo()
    subgroup = repo.create_subgroup(
        group_id=group_id,
        subgroup_name=payload.name,
        description=payload.description,
        created_by=current_user.user_id,
    )
    return {
        "subgroup_id": subgroup.subgroup_id,
        "name": subgroup.subgroup_name,
        "description": subgroup.description,
        "camera_count": subgroup.camera_count,
        "created_at": format_iso_utc(subgroup.created_at),
    }


@router.put("/{group_id}/subgroups/{subgroup_id}", summary="Update subgroup / area")
@router.patch("/{group_id}/subgroups/{subgroup_id}", summary="Partial update subgroup")
def update_subgroup(
    group_id: str,
    subgroup_id: str,
    payload: UpdateSubgroupRequest,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update subgroup name and description."""
    check_group_permission(group_id, current_user.user_id, [UserRole.LEADER, UserRole.MEMBER_MANAGER])
    repo = get_group_repo()
    subgroup = repo.update_subgroup(
        group_id=group_id,
        subgroup_id=subgroup_id,
        name=payload.name,
        description=payload.description,
    )
    if not subgroup:
        raise NotFoundException("Không tìm thấy khu vực trong nhóm.", code="SUBGROUP_NOT_FOUND")
    return {
        "subgroup_id": subgroup.subgroup_id,
        "name": subgroup.subgroup_name,
        "description": subgroup.description,
        "camera_count": subgroup.camera_count,
    }


@router.delete("/{group_id}/subgroups/{subgroup_id}", summary="Delete subgroup / area")
def delete_subgroup(
    group_id: str,
    subgroup_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Delete a subgroup / area."""
    check_group_permission(group_id, current_user.user_id, [UserRole.LEADER, UserRole.MEMBER_MANAGER])
    repo = get_group_repo()
    success = repo.delete_subgroup(group_id, subgroup_id)
    if not success:
        raise NotFoundException("Không tìm thấy khu vực trong nhóm.", code="SUBGROUP_NOT_FOUND")
    return {"status": "success", "message": "Đã xóa khu vực thành công"}
