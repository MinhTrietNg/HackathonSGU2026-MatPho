"""
User Profile & Settings Router for Mắt Phố
"""

from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..core.security import get_current_user
from ..services.repositories.user_repo import get_user_repo
from ..models.user import (
    UserModel,
    UserResponseDTO,
    UpdateSettingsRequest,
    AddFcmTokenRequest,
)

router = APIRouter(prefix="/users", tags=["Users"])


class UpdateLoudWhenSilentRequest(BaseModel):
    loud_when_silent: bool


@router.get("/me", response_model=UserResponseDTO, summary="Get current user profile")
def get_me(current_user: UserModel = Depends(get_current_user)):
    """Retrieve authenticated user's profile and default personal group."""
    return UserResponseDTO(
        user_id=current_user.user_id,
        phone_number=current_user.phone_number,
        full_name=current_user.full_name,
        loud_when_silent=current_user.loud_when_silent,
        personal_group_id=current_user.personal_group_id,
    )


@router.get("/me/settings", summary="Get user notification settings")
def get_my_settings(current_user: UserModel = Depends(get_current_user)):
    return {
        "loud_when_silent": current_user.loud_when_silent,
        "full_name": current_user.full_name,
    }


@router.patch("/me/settings", summary="Update user settings and display name")
@router.put("/me", summary="Update user profile")
def update_settings(
    payload: UpdateSettingsRequest,
    current_user: UserModel = Depends(get_current_user),
):
    repo = get_user_repo()
    repo.update_user_settings(
        current_user.user_id,
        loud_when_silent=payload.loud_when_silent,
        full_name=payload.full_name,
    )
    return {
        "loud_when_silent": payload.loud_when_silent if payload.loud_when_silent is not None else current_user.loud_when_silent,
        "full_name": payload.full_name if payload.full_name is not None else current_user.full_name,
    }


@router.patch("/me/loud-when-silent", summary="Toggle loud when silent mode")
def toggle_loud_when_silent(
    payload: UpdateLoudWhenSilentRequest,
    current_user: UserModel = Depends(get_current_user),
):
    repo = get_user_repo()
    repo.update_user_settings(current_user.user_id, loud_when_silent=payload.loud_when_silent)
    return {
        "loud_when_silent": payload.loud_when_silent,
    }


@router.post("/me/fcm-token", summary="Register FCM Device Token")
@router.post("/me/fcm-tokens", summary="Register FCM Device Token (alias)")
def register_fcm_token(
    payload: AddFcmTokenRequest,
    current_user: UserModel = Depends(get_current_user),
):
    repo = get_user_repo()
    repo.add_user_fcm_token(current_user.user_id, payload.fcm_token)
    return {
        "status": "success",
        "message": "FCM token đã được cập nhật thành công.",
    }
