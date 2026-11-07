"""
Repositories Package
"""

from .base_repo import BaseRepository, BaseFirestoreRepository
from .user_repo import UserRepository, get_user_repository, get_user_repo
from .group_repo import GroupRepository, get_group_repository, get_group_repo
from .camera_repo import CameraRepository, get_camera_repository, get_camera_repo
from .alert_repo import AlertRepository, get_alert_repository

__all__ = [
    "BaseRepository",
    "BaseFirestoreRepository",
    "UserRepository",
    "get_user_repository",
    "get_user_repo",
    "GroupRepository",
    "get_group_repository",
    "get_group_repo",
    "CameraRepository",
    "get_camera_repository",
    "get_camera_repo",
    "AlertRepository",
    "get_alert_repository",
]
