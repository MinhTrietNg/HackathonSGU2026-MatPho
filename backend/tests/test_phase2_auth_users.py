"""
Phase 2 Test Suite: Authentication, Identity, E.164, OTP, Password Bcrypt & User Profile
"""

import time
import pytest
from src.core.security import otp_manager
from src.services.repositories.user_repo import get_user_repo


def _generate_unique_phone() -> str:
    return f"091{int(time.time() * 1000) % 10000000:07d}"


def test_check_phone_available_and_taken(client):
    """Verify phone check returns availability and E.164 normalized phone."""
    phone = _generate_unique_phone()
    res = client.post("/api/v1/auth/check-phone", json={"phone_number": phone})
    assert res.status_code == 200
    data = res.json()
    assert data["is_available"] is True
    assert data["phone_number"].startswith("+84")


def test_full_registration_flow_with_otp_and_personal_group(client):
    """
    Test complete registration:
    1. Request OTP -> receives challenge_id and dev_otp.
    2. Verify with wrong code -> returns 422 OTP_WRONG.
    3. Verify with correct code -> creates user, personal group, and returns custom_token.
    """
    phone = _generate_unique_phone()
    full_name = "Nguyễn Văn Phase2"
    password = "SecurePassword123@"

    # 1. Request OTP
    req_res = client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": phone, "full_name": full_name, "password": password},
    )
    assert req_res.status_code == 200
    req_data = req_res.json()
    assert "challenge_id" in req_data
    assert req_data["expires_in"] == 60
    assert req_data["dev_otp"] == "123456"
    challenge_id = req_data["challenge_id"]

    # 2. Verify with wrong OTP -> 422
    wrong_res = client.post(
        "/api/v1/auth/verify-otp",
        json={"challenge_id": challenge_id, "code": "999999"},
    )
    assert wrong_res.status_code == 422
    wrong_data = wrong_res.json()
    assert wrong_data["error"]["code"] == "OTP_WRONG"
    assert wrong_data["error"]["details"]["attempts_left"] == 2

    # 3. Verify with correct OTP -> 200
    verify_res = client.post(
        "/api/v1/auth/verify-otp",
        json={"challenge_id": challenge_id, "code": "123456", "fcm_token": "fcm_device_test_123"},
    )
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert verify_data["type"] == "REGISTER_SUCCESS"
    assert "custom_token" in verify_data
    user = verify_data["user"]
    assert user["full_name"] == full_name
    assert user["personal_group_id"].startswith("grp_personal_")

    # 4. Verify in DB
    repo = get_user_repo()
    db_user = repo.get_user_by_id(user["user_id"])
    assert db_user is not None
    assert db_user.phone_number.startswith("+84")
    assert "fcm_device_test_123" in db_user.fcm_tokens


def test_duplicate_registration_prevented(client):
    """Verify phone cannot be registered twice (409 Conflict)."""
    phone = _generate_unique_phone()
    # Register once
    r1 = client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": phone, "full_name": "User 1", "password": "Password123@"},
    )
    client.post(
        "/api/v1/auth/verify-otp",
        json={"challenge_id": r1.json()["challenge_id"], "code": "123456"},
    )

    # Attempt second registration with same phone
    r2 = client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": phone, "full_name": "User 2", "password": "Password123@"},
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "PHONE_ALREADY_REGISTERED"


def test_login_success_and_wrong_password(client):
    """Verify login authentication and attempts decrement."""
    phone = _generate_unique_phone()
    password = "MyStrongPassword123@"
    # Register user
    r1 = client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": phone, "full_name": "Login Tester", "password": password},
    )
    client.post(
        "/api/v1/auth/verify-otp",
        json={"challenge_id": r1.json()["challenge_id"], "code": "123456"},
    )

    # 1. Login with wrong password -> 422
    wrong_login = client.post(
        "/api/v1/auth/login",
        json={"phone_number": phone, "password": "WrongPassword999"},
    )
    assert wrong_login.status_code == 422
    assert wrong_login.json()["error"]["code"] == "WRONG_PASSWORD"
    assert wrong_login.json()["error"]["details"]["attempts_left"] == 4

    # 2. Login with correct password -> 200
    success_login = client.post(
        "/api/v1/auth/login",
        json={"phone_number": phone, "password": password, "fcm_token": "fcm_token_login_001"},
    )
    assert success_login.status_code == 200
    assert "custom_token" in success_login.json()
    assert success_login.json()["user"]["phone_number"].startswith("+84")


def test_login_account_lockout_after_5_failures(client):
    """Verify account is locked for 15 minutes after 5 consecutive failures (423 Locked)."""
    phone = _generate_unique_phone()
    # Register user
    r1 = client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": phone, "full_name": "Lockout Tester", "password": "PassWord123!"},
    )
    client.post(
        "/api/v1/auth/verify-otp",
        json={"challenge_id": r1.json()["challenge_id"], "code": "123456"},
    )

    # Fail 4 times
    for _ in range(4):
        res = client.post("/api/v1/auth/login", json={"phone_number": phone, "password": "bad"})
        assert res.status_code == 422

    # 5th failure -> Account locked (423)
    res5 = client.post("/api/v1/auth/login", json={"phone_number": phone, "password": "bad"})
    assert res5.status_code == 423
    assert res5.json()["error"]["code"] == "ACCOUNT_LOCKED"
    assert "locked_until" in res5.json()["error"]["details"]


def test_forgot_password_and_reset_flow(client):
    """Verify forgot password OTP and password reset."""
    phone = _generate_unique_phone()
    old_pw = "OldPassword123@"
    new_pw = "NewSecurePassword456!"

    # Register user
    r1 = client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": phone, "full_name": "Reset Tester", "password": old_pw},
    )
    client.post(
        "/api/v1/auth/verify-otp",
        json={"challenge_id": r1.json()["challenge_id"], "code": "123456"},
    )

    # 1. Request forgot password OTP
    forgot_res = client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"phone_number": phone},
    )
    assert forgot_res.status_code == 200
    challenge_id = forgot_res.json()["challenge_id"]

    # 2. Verify OTP -> receives reset_token
    v_res = client.post(
        "/api/v1/auth/verify-otp",
        json={"challenge_id": challenge_id, "code": "123456"},
    )
    assert v_res.status_code == 200
    assert v_res.json()["type"] == "RESET_PASSWORD_VERIFIED"
    reset_token = v_res.json()["reset_token"]

    # 3. Reset password
    reset_res = client.post(
        "/api/v1/auth/forgot-password/reset",
        json={"reset_token": reset_token, "new_password": new_pw},
    )
    assert reset_res.status_code == 200
    assert reset_res.json()["status"] == "success"

    # 4. Old password fails
    fail_login = client.post("/api/v1/auth/login", json={"phone_number": phone, "password": old_pw})
    assert fail_login.status_code == 422

    # 5. New password succeeds
    good_login = client.post("/api/v1/auth/login", json={"phone_number": phone, "password": new_pw})
    assert good_login.status_code == 200


def test_user_profile_and_settings(client):
    """Verify /users/me and updating profile preferences."""
    phone = _generate_unique_phone()
    r1 = client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": phone, "full_name": "Profile Tester", "password": "Password123@"},
    )
    v1 = client.post(
        "/api/v1/auth/verify-otp",
        json={"challenge_id": r1.json()["challenge_id"], "code": "123456"},
    )
    user_id = v1.json()["user"]["user_id"]
    headers = {"Authorization": f"Bearer {user_id}"}

    # 1. Get profile
    me_res = client.get("/api/v1/users/me", headers=headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["user_id"] == user_id
    assert me_data["full_name"] == "Profile Tester"
    assert me_data["loud_when_silent"] is True

    # 2. Update profile name & settings
    up_res = client.patch(
        "/api/v1/users/me/settings",
        json={"full_name": "Tên Đã Đổi", "loud_when_silent": False},
        headers=headers,
    )
    assert up_res.status_code == 200
    assert up_res.json()["full_name"] == "Tên Đã Đổi"
    assert up_res.json()["loud_when_silent"] is False

    # 3. Add FCM Token
    fcm_res = client.post(
        "/api/v1/users/me/fcm-token",
        json={"fcm_token": "new_fcm_token_device_xyz"},
        headers=headers,
    )
    assert fcm_res.status_code == 200
    assert fcm_res.json()["status"] == "success"
