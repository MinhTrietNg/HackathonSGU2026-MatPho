"""
User & Phone Registry Models for Mắt Phố
"""

from typing import Optional, List, Any
from datetime import datetime
from pydantic import Field, field_validator
from .common import BaseSchema
from ..core.formatters import normalize_phone_e164


class PhoneRegistryModel(BaseSchema):
    user_id: str = Field(..., description="Mã UID sở hữu số điện thoại này")
    created_at: Optional[Any] = Field(None, description="Thời điểm đăng ký khóa số")


class UserModel(BaseSchema):
    user_id: str = Field(..., description="Firebase Auth UID / Định danh hệ thống")
    phone_number: str = Field(..., description="Số điện thoại E.164 (+84...)")
    full_name: str = Field(..., min_length=2, max_length=100, description="Họ và tên hiển thị")
    password_hash: str = Field(..., description="Mật khẩu mã hóa bcrypt an toàn")
    failed_attempts: int = Field(default=0, ge=0, description="Số lần nhập sai mật khẩu (tối đa 5 lần)")
    locked_until: Optional[Any] = Field(None, description="Thời điểm hết hạn khóa tài khoản 15 phút")
    fcm_tokens: List[str] = Field(default_factory=list, description="Danh sách Device Tokens nhận còi hú FCM")
    loud_when_silent: bool = Field(default=True, description="Cài đặt: Báo động kêu cả khi điện thoại im lặng (H1)")
    personal_group_id: Optional[str] = Field(None, description="Mã Group Cá Nhân mặc định (grp_personal_{uid})")
    created_at: Optional[Any] = Field(None, description="Thời điểm tạo tài khoản")
    updated_at: Optional[Any] = Field(None, description="Thời điểm cập nhật hồ sơ gần nhất")

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone_e164(v)


# DTOs
class CheckPhoneRequest(BaseSchema):
    phone_number: str


class RegisterOtpRequest(BaseSchema):
    phone_number: str
    full_name: str
    password: str = Field(..., min_length=6)


class ForgotPasswordOtpRequest(BaseSchema):
    phone_number: str


class VerifyOtpRequest(BaseSchema):
    challenge_id: str
    code: str
    fcm_token: Optional[str] = None


class ResendOtpRequest(BaseSchema):
    challenge_id: str


class ResetPasswordRequest(BaseSchema):
    reset_token: str
    new_password: str = Field(..., min_length=6)


class ChangePasswordRequest(BaseSchema):
    current_password: str
    new_password: str = Field(..., min_length=6)


class UserLoginRequest(BaseSchema):
    phone_number: str
    password: str
    fcm_token: Optional[str] = None


class UserResponseDTO(BaseSchema):
    user_id: str
    phone_number: str
    full_name: str
    loud_when_silent: bool = True
    personal_group_id: str


class UpdateSettingsRequest(BaseSchema):
    loud_when_silent: Optional[bool] = None
    full_name: Optional[str] = None


class AddFcmTokenRequest(BaseSchema):
    fcm_token: str
