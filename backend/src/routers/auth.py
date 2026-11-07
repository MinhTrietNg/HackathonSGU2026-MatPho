"""
Authentication & Session Router for Mắt Phố (Figma Rows A & B)
"""

import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from firebase_admin import auth as fb_auth

logger = logging.getLogger("backend.routers.auth")

from ..core.exceptions import (
    AppException,
    WrongPasswordException,
    AccountLockedException,
    PhoneAlreadyRegisteredException,
    PhoneNotRegisteredException,
    UnauthorizedException,
)
from ..core.security import (
    hash_password,
    verify_password,
    create_firebase_custom_token,
    otp_manager,
    get_current_user,
)
from ..core.formatters import normalize_phone_e164
from ..services.repositories.user_repo import get_user_repo
from ..models.user import (
    UserModel,
    CheckPhoneRequest,
    RegisterOtpRequest,
    VerifyOtpRequest,
    ResendOtpRequest,
    ForgotPasswordOtpRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
    UserLoginRequest,
    UserResponseDTO,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LogoutRequest(BaseModel):
    fcm_token: Optional[str] = None


@router.post("/check-phone", summary="Check phone availability")
def check_phone(payload: CheckPhoneRequest):
    """
    Check if a phone number is already registered in the system.
    Normalizes to E.164.
    """
    repo = get_user_repo()
    phone_e164 = normalize_phone_e164(payload.phone_number)
    user = repo.get_user_by_phone(phone_e164)
    return {
        "phone_number": phone_e164,
        "is_available": user is None,
    }


@router.post("/register/request-otp", summary="Request OTP for registration")
def request_register_otp(payload: RegisterOtpRequest):
    """
    Initiate user registration by requesting a 6-digit OTP (TTL 60s).
    """
    repo = get_user_repo()
    phone_e164 = normalize_phone_e164(payload.phone_number)
    user = repo.get_user_by_phone(phone_e164)
    if user:
        raise PhoneAlreadyRegisteredException()

    challenge, dev_otp = otp_manager.create_challenge(
        phone_number=phone_e164,
        purpose="register",
        data={
            "full_name": payload.full_name,
            "password": payload.password,
        },
    )

    resp = {
        "challenge_id": challenge.challenge_id,
        "expires_in": 60,
        "resend_cooldown": 60,
    }
    if dev_otp:
        resp["dev_otp"] = dev_otp
    return resp


@router.post("/forgot-password/request-otp", summary="Request OTP for password recovery")
def request_forgot_password_otp(payload: ForgotPasswordOtpRequest):
    """
    Initiate password reset by sending an OTP to the registered phone number.
    """
    repo = get_user_repo()
    phone_e164 = normalize_phone_e164(payload.phone_number)
    user = repo.get_user_by_phone(phone_e164)
    if not user:
        raise PhoneNotRegisteredException()

    challenge, dev_otp = otp_manager.create_challenge(
        phone_number=phone_e164,
        purpose="forgot_password",
    )

    resp = {
        "challenge_id": challenge.challenge_id,
        "expires_in": 60,
        "resend_cooldown": 60,
    }
    if dev_otp:
        resp["dev_otp"] = dev_otp
    return resp


@router.post("/verify-otp", summary="Verify OTP and complete registration or password recovery")
def verify_otp(payload: VerifyOtpRequest):
    """
    Verify OTP code:
    - If register: atomically creates user profile and default personal group, returns custom_token.
    - If forgot_password: returns a reset_token for resetting password.
    """
    challenge, reset_token = otp_manager.verify_code(payload.challenge_id, payload.code)
    repo = get_user_repo()

    if challenge.purpose == "register":
        user_data = challenge.data
        pw_hash = hash_password(user_data["password"])
        try:
            new_user = repo.register_user_transaction(
                phone_number=challenge.phone_number,
                password_hash=pw_hash,
                full_name=user_data["full_name"],
                fcm_token=payload.fcm_token,
            )
        except ValueError as e:
            if "PHONE_ALREADY_REGISTERED" in str(e):
                raise PhoneAlreadyRegisteredException()
            raise AppException(message=str(e), status_code=400, code="REGISTRATION_FAILED")

        custom_token = create_firebase_custom_token(new_user.user_id)
        return {
            "type": "REGISTER_SUCCESS",
            "custom_token": custom_token,
            "user": UserResponseDTO(
                user_id=new_user.user_id,
                phone_number=new_user.phone_number,
                full_name=new_user.full_name,
                loud_when_silent=new_user.loud_when_silent,
                personal_group_id=new_user.personal_group_id,
            ),
        }

    return {
        "type": "RESET_PASSWORD_VERIFIED",
        "reset_token": reset_token,
    }


@router.post("/register/resend-otp", summary="Resend registration OTP")
@router.post("/resend-otp", summary="Resend OTP")
def resend_otp(payload: ResendOtpRequest):
    """
    Resend OTP challenge with 60s cooldown enforcement.
    """
    challenge, dev_otp = otp_manager.resend_otp(payload.challenge_id)
    resp = {
        "challenge_id": challenge.challenge_id,
        "expires_in": 60,
        "resend_cooldown": 60,
    }
    if dev_otp:
        resp["dev_otp"] = dev_otp
    return resp


@router.post("/login", summary="Login with Phone & Password")
def login(payload: UserLoginRequest):
    """
    Authenticate user via Phone Number & bcrypt password.
    OWASP protection:
    - Returns 422 WRONG_PASSWORD if phone not found or wrong password (prevents username enumeration).
    - Locks account for 15 minutes after 5 consecutive failures (423 ACCOUNT_LOCKED).
    """
    repo = get_user_repo()
    phone_e164 = normalize_phone_e164(payload.phone_number)
    user = repo.get_user_by_phone(phone_e164)

    # 1. User not found -> Return WRONG_PASSWORD to prevent phone enumeration
    if not user:
        raise WrongPasswordException(attempts_left=4)

    # 2. Check if account is locked (Figma A6)
    if user.locked_until:
        locked_dt = user.locked_until
        if isinstance(locked_dt, str):
            locked_dt = datetime.fromisoformat(locked_dt.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if now < locked_dt:
            raise AccountLockedException(locked_until=locked_dt.isoformat())

    # 3. Verify password
    if not verify_password(payload.password, user.password_hash):
        fails, locked_until = repo.record_login_attempt(user.user_id, success=False)
        if locked_until:
            raise AccountLockedException(locked_until=locked_until.isoformat())
        attempts_left = max(0, 5 - fails)
        raise WrongPasswordException(attempts_left=attempts_left)

    # 4. Success -> Reset failed attempts
    repo.record_login_attempt(user.user_id, success=True)
    if payload.fcm_token:
        repo.add_user_fcm_token(user.user_id, payload.fcm_token)

    custom_token = create_firebase_custom_token(user.user_id)
    return {
        "custom_token": custom_token,
        "user": UserResponseDTO(
            user_id=user.user_id,
            phone_number=user.phone_number,
            full_name=user.full_name,
            loud_when_silent=user.loud_when_silent,
            personal_group_id=user.personal_group_id,
        ),
    }


@router.post("/forgot-password/reset", summary="Reset password using reset_token")
@router.post("/reset-password", summary="Reset password")
def reset_password(payload: ResetPasswordRequest):
    """
    Reset password with a verified reset_token.
    Revokes sessions & FCM tokens on other devices.
    """
    phone_number = otp_manager.verify_reset_token(payload.reset_token)
    repo = get_user_repo()
    pw_hash = hash_password(payload.new_password)
    success = repo.update_user_password_by_phone(phone_number, pw_hash)
    if not success:
        raise AppException(code="USER_NOT_FOUND", message="Không tìm thấy tài khoản để đặt lại mật khẩu.", status_code=404)

    user = repo.get_user_by_phone(phone_number)
    if user:
        repo.clear_user_fcm_tokens(user.user_id)

    return {
        "status": "success",
        "message": "Mật khẩu đã được thay đổi thành công. Máy khác đã đăng xuất.",
    }


@router.post("/change-password", summary="Change password for authenticated user")
def change_password(
    payload: ChangePasswordRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """
    Authenticated user changes password by verifying current password.
    """
    if not verify_password(payload.current_password, current_user.password_hash):
        raise WrongPasswordException(attempts_left=0)

    repo = get_user_repo()
    pw_hash = hash_password(payload.new_password)
    repo.update_user_password(current_user.user_id, pw_hash)
    return {
        "status": "success",
        "message": "Đổi mật khẩu thành công",
    }


@router.post("/logout", summary="Logout user and deregister device FCM token")
def logout(
    payload: LogoutRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """
    Remove current device FCM token on logout.
    """
    if payload.fcm_token:
        repo = get_user_repo()
        repo.remove_user_fcm_token(current_user.user_id, payload.fcm_token)
    return {
        "status": "success",
        "message": "Đã hủy đăng ký nhận thông báo cho thiết bị này",
    }
