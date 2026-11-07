"""
Common Enums, Models & Semantic ID Helpers for Mắt Phố
"""

import uuid
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict


class UserRole(str, Enum):
    LEADER = "LEADER"
    MEMBER_MANAGER = "MEMBER_MANAGER"
    MEMBER = "MEMBER"
    NOTIFIER = "NOTIFIER"


class CameraStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DISABLED = "DISABLED"


class AlertStatus(str, Enum):
    NEW = "NEW"
    CONFIRMED = "CONFIRMED"
    FALSE_ALARM = "FALSE_ALARM"
    RESOLVED = "RESOLVED"


class AlertVerification(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    SUPPRESSED = "SUPPRESSED"


class SignType(str, Enum):
    FIRE = "FIRE"
    SMOKE = "SMOKE"
    BOTH = "BOTH"


class InvitationStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class AuditAction(str, Enum):
    CREATE_GROUP = "CREATE_GROUP"
    UPDATE_GROUP = "UPDATE_GROUP"
    TRANSFER_OWNERSHIP = "TRANSFER_OWNERSHIP"
    INVITE_MEMBER = "INVITE_MEMBER"
    ACCEPT_INVITATION = "ACCEPT_INVITATION"
    REJECT_INVITATION = "REJECT_INVITATION"
    UPDATE_ROLE = "UPDATE_ROLE"
    ASSIGN_CAMERAS = "ASSIGN_CAMERAS"
    REMOVE_MEMBER = "REMOVE_MEMBER"
    CREATE_CAMERA = "CREATE_CAMERA"
    UPDATE_CAMERA = "UPDATE_CAMERA"
    DELETE_CAMERA = "DELETE_CAMERA"
    RESTORE_CAMERA = "RESTORE_CAMERA"
    UPDATE_WATCH_AREA = "UPDATE_WATCH_AREA"
    CALL_114 = "CALL_114"
    RESOLVE_ALERT = "RESOLVE_ALERT"
    FALSE_ALARM = "FALSE_ALARM"
    DISMISS_SUSPECT = "DISMISS_SUSPECT"


def generate_semantic_id(prefix: str) -> str:
    """
    Generate an ID with a semantic prefix and random 12-char hex.
    Examples:
        usr_9fdf1552e32f
        grp_4fa3a72888dd
        cam_12a4b8c9e011
        alt_88d011e2f334
        sub_22c4a9e10ff4
        inv_77f012e4d9aa
        log_33b8a1c9e44d
    """
    random_hex = uuid.uuid4().hex[:12]
    return f"{prefix}_{random_hex}"


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        arbitrary_types_allowed=True,
    )
