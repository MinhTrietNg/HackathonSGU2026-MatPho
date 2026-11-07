"""
Invitations Management Router for Mắt Phố
Phase 3: Tiếp nhận và xử lý lời mời tham gia nhóm liên gia (Figma J3)
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from ..core.security import get_current_user
from ..core.exceptions import (
    AppException,
    NotFoundException,
    PermissionDeniedException,
    InvitationUnavailableException,
)
from ..core.formatters import format_iso_utc
from ..models.user import UserModel
from ..models.common import InvitationStatus, UserRole
from ..models.group import AcceptInvitationRequest
from ..services.repositories.group_repo import get_group_repo

logger = logging.getLogger("backend.routers.invitations")

router = APIRouter(prefix="/invitations", tags=["Invitations"])


def serialize_invitation(inv) -> Dict[str, Any]:
    return {
        "invitation_id": inv.invitation_id,
        "id": inv.invitation_id,
        "group_id": inv.group_id,
        "group_name": inv.group_name,
        "group_address": inv.group_address,
        "invited_by_name": inv.invited_by_name,
        "inviter_name": inv.invited_by_name,
        "role": inv.role.value if hasattr(inv.role, "value") else str(inv.role),
        "nickname": inv.suggested_nickname or inv.nickname,
        "suggested_nickname": inv.suggested_nickname or inv.nickname,
        "member_count": getattr(inv, "member_count", None) or 1,
        "camera_count": inv.camera_count or (len(inv.camera_ids) if inv.camera_ids else 0),
        "camera_names": inv.camera_names or [],
        "status": inv.status.value if hasattr(inv.status, "value") else str(inv.status),
        "created_at": format_iso_utc(inv.created_at),
    }


@router.get("", summary="List pending invitations for current user")
@router.get("/my-invitations", summary="List pending invitations for current user (Alias)")
def list_my_invitations(
    current_user: UserModel = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Get all pending invitations sent to current user's phone number (Screen J3).
    """
    repo = get_group_repo()
    invitations = repo.list_invitations_for_user(current_user.phone_number)
    return [serialize_invitation(inv) for inv in invitations]


@router.get("/{invitation_id}", summary="Get invitation details")
def get_invitation(
    invitation_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Retrieve details of an invitation.
    Security: Only the recipient phone number or group leaders/managers can view.
    """
    repo = get_group_repo()
    inv = repo.get_invitation(invitation_id)
    if not inv or inv.status != InvitationStatus.PENDING:
        raise InvitationUnavailableException()

    # Verify authorization: recipient phone number OR leader/manager of group
    if inv.phone_number != current_user.phone_number:
        caller_member = repo.get_member(inv.group_id, current_user.user_id)
        if not caller_member or caller_member.role not in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
            raise InvitationUnavailableException()

    return serialize_invitation(inv)


@router.post("/{invitation_id}/accept", summary="Accept invitation and join group")
def accept_invitation(
    invitation_id: str,
    payload: Optional[AcceptInvitationRequest] = None,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Accept an invitation to join a group.
    Atomically updates invitation status, adds member, and creates user membership.
    """
    repo = get_group_repo()
    inv = repo.get_invitation(invitation_id)
    if not inv or inv.status != InvitationStatus.PENDING:
        raise InvitationUnavailableException()

    if inv.phone_number != current_user.phone_number:
        raise InvitationUnavailableException("Lời mời này không gửi tới số điện thoại của bạn.")

    chosen_nickname = (payload.nickname if payload else None) or inv.suggested_nickname or inv.nickname or current_user.full_name
    try:
        repo.accept_invitation_transaction(
            invitation_id=invitation_id,
            user_id=current_user.user_id,
            nickname=chosen_nickname,
        )
    except ValueError as e:
        err = str(e)
        if err == "ALREADY_IN_GROUP":
            raise AppException("CONFLICT", "Bạn đã là thành viên của nhóm này rồi.", status_code=409)
        raise InvitationUnavailableException()

    group = repo.get_group(inv.group_id)
    return {
        "status": "success",
        "message": f"Chào mừng bạn gia nhập {group.group_name if group else 'nhóm'}!",
        "group_id": inv.group_id,
        "group_name": group.group_name if group else inv.group_name,
        "role": inv.role.value if hasattr(inv.role, "value") else str(inv.role),
        "my_nickname": chosen_nickname,
    }


@router.post("/{invitation_id}/decline", summary="Decline invitation")
@router.post("/{invitation_id}/reject", summary="Decline invitation (Alias)")
def decline_invitation(
    invitation_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Decline/Reject an invitation."""
    repo = get_group_repo()
    inv = repo.get_invitation(invitation_id)
    if not inv or inv.status != InvitationStatus.PENDING:
        raise InvitationUnavailableException()

    if inv.phone_number != current_user.phone_number:
        raise InvitationUnavailableException("Lời mời này không gửi tới số điện thoại của bạn.")

    repo.decline_invitation(invitation_id)
    return {"status": "success", "message": "Đã từ chối lời mời tham gia nhóm."}


@router.delete("/{invitation_id}", summary="Cancel/Revoke invitation (Recipient or Group Leader)")
def revoke_invitation(
    invitation_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Cancel or revoke an invitation."""
    repo = get_group_repo()
    inv = repo.get_invitation(invitation_id)
    if not inv or inv.status != InvitationStatus.PENDING:
        raise InvitationUnavailableException()

    # Can be revoked by recipient OR group leader/manager
    if inv.phone_number != current_user.phone_number:
        member = repo.get_member(inv.group_id, current_user.user_id)
        if not member or member.role not in (UserRole.LEADER, UserRole.MEMBER_MANAGER):
            raise PermissionDeniedException("Bạn không có quyền hủy lời mời này.")

    repo.cancel_invitation(inv.group_id, invitation_id)
    return {"status": "success", "message": "Đã hủy lời mời thành công."}
