"""
Group, Subgroup, Member & Invitation Models and DTOs for Mắt Phố
"""

from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator
from .common import UserRole, InvitationStatus
from ..core.formatters import normalize_phone_e164


# ==============================================================================
# SUBGROUPS (Khu vực / Vị trí lắp đặt)
# ==============================================================================

class SubgroupModel(BaseModel):
    subgroup_id: str = Field(..., description="Mã khu vực (sub_xxx)")
    subgroup_name: str = Field(..., min_length=1, max_length=100, description="Tên khu vực (ví dụ: 'Bếp tầng 1')")
    description: Optional[str] = Field(None, max_length=255, description="Mô tả chi tiết")
    camera_count: int = Field(default=0, ge=0, description="Số lượng camera đang đặt tại khu vực")
    created_by: Optional[str] = Field(None, description="UID người tạo vị trí")
    created_at: Optional[Any] = Field(None, description="Thời điểm tạo")


class CreateSubgroupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Tên khu vực (ví dụ: 'Bếp tầng 1')")
    description: Optional[str] = Field(None, max_length=255)


class UpdateSubgroupRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=255)


# ==============================================================================
# MEMBERS (Thành viên nhóm)
# ==============================================================================

class MemberModel(BaseModel):
    user_id: str = Field(..., description="UID người dùng")
    role: UserRole = Field(..., description="Vai trò: LEADER | MEMBER_MANAGER | MEMBER | NOTIFIER")
    nickname: Optional[str] = Field(None, max_length=50, description="Biệt danh trong nhóm")
    note: Optional[str] = Field(None, max_length=200, description="Ghi chú thành viên")
    phone_number: str = Field(..., description="Snapshot số điện thoại E.164")
    full_name: str = Field(..., description="Snapshot họ và tên")
    camera_ids: Optional[List[str]] = Field(
        None,
        description="null = xem toàn bộ nhóm; mảng = chỉ xem các camera được chỉ định"
    )
    joined_at: Optional[Any] = Field(None, description="Thời điểm tham gia nhóm")
    updated_at: Optional[Any] = Field(None, description="Thời điểm cập nhật quyền")

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone_e164(v)


class MemberResponseDTO(BaseModel):
    user_id: str
    full_name: str
    phone_number: str
    role: str
    nickname: Optional[str] = None
    note: Optional[str] = None
    camera_ids: Optional[List[str]] = None
    joined_at: Optional[str] = None
    is_you: bool = False


class ChangeMemberRoleRequest(BaseModel):
    role: UserRole


class AssignCamerasRequest(BaseModel):
    camera_ids: Optional[List[str]] = None  # None/empty = all cameras


class ChangeNicknameRequest(BaseModel):
    nickname: Optional[str] = Field(None, max_length=50)


# ==============================================================================
# INVITATIONS (Lời mời tham gia nhóm)
# ==============================================================================

class InvitationModel(BaseModel):
    invitation_id: str = Field(..., description="Mã lời mời (inv_xxx)")
    group_id: str = Field(..., description="Mã nhóm gửi lời mời")
    group_name: str = Field(..., description="Snapshot tên nhóm")
    group_address: Optional[str] = Field(None, description="Snapshot địa chỉ nhóm")
    phone_number: str = Field(..., description="Số điện thoại được mời (E.164)")
    role: UserRole = Field(default=UserRole.MEMBER, description="Vai trò dự kiến")
    nickname: Optional[str] = Field(None, max_length=50)
    suggested_nickname: Optional[str] = Field(None, max_length=50)
    member_count: Optional[int] = Field(default=None)
    camera_count: Optional[int] = Field(default=0)
    camera_names: Optional[List[str]] = Field(default_factory=list)
    camera_ids: Optional[List[str]] = Field(None)
    invited_by: str = Field(..., description="UID người mời")
    invited_by_name: str = Field(..., description="Snapshot tên người mời")
    status: InvitationStatus = Field(default=InvitationStatus.PENDING)
    expires_at: Optional[Any] = None
    created_at: Optional[Any] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone_e164(v)


class InviteMemberRequest(BaseModel):
    phone_number: str
    role: UserRole = UserRole.MEMBER
    nickname: Optional[str] = Field(None, max_length=50)
    camera_ids: Optional[List[str]] = None


class AcceptInvitationRequest(BaseModel):
    nickname: Optional[str] = Field(None, max_length=50)


# ==============================================================================
# GROUPS (Nhóm liên gia & Nhóm cá nhân)
# ==============================================================================

class GroupModel(BaseModel):
    group_id: str = Field(..., description="Mã nhóm (grp_xxx hoặc grp_personal_{uid})")
    group_name: str = Field(..., min_length=1, max_length=100)
    is_personal: bool = Field(default=False)
    leader_id: str = Field(default="", description="UID Trưởng nhóm")
    creator_id: Optional[str] = None
    address: Optional[str] = Field(None, max_length=255, description="Địa chỉ cứu nạn 114")
    member_count: int = Field(default=1, ge=1)
    camera_count: int = Field(default=0, ge=0)
    is_deleted: bool = Field(default=False)
    deleted_at: Optional[Any] = None
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None

    @model_validator(mode="before")
    @classmethod
    def set_leader_fallback(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("leader_id") and data.get("creator_id"):
                data["leader_id"] = data["creator_id"]
        return data


class CreateGroupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    address: Optional[str] = Field(None, max_length=255)
    my_nickname: Optional[str] = Field(None, max_length=50)


class UpdateGroupRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    address: Optional[str] = Field(None, max_length=255)


class TransferOwnershipRequest(BaseModel):
    new_leader_id: str = Field(..., description="UID của thành viên tiếp quản quyền Trưởng nhóm")


class GroupResponseDTO(BaseModel):
    group_id: str
    group_name: str
    is_personal: bool
    leader_id: str
    address: Optional[str] = None
    member_count: int = 1
    camera_count: int = 0
    my_role: Optional[str] = None
    my_nickname: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
