"""
Security, Authentication & OTP Management for Mắt Phố Backend
"""

import os
import time
import uuid
import hashlib
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from fastapi import Header, Depends, HTTPException, status
import bcrypt
import firebase_admin
from firebase_admin import auth as fb_auth

from .config import settings
from .exceptions import (
    AppException,
    UnauthorizedException,
    WrongPasswordException,
    AccountLockedException,
    OtpWrongException,
    OtpExpiredException,
    OtpLockedException,
    OtpResendCooldownException,
)

logger = logging.getLogger("backend.security")


def hash_password(password: str) -> str:
    """Hash password using bcrypt with salt rounds 12."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def generate_emergency_token(alert_id: str) -> str:
    """Generates a verifiable short-lived emergency token for an alert (valid 3 hours)."""
    secret = settings.INTERNAL_API_SECRET_KEY
    ts = int(time.time())
    sig = hashlib.sha256(f"{alert_id}:{ts}:{secret}".encode()).hexdigest()[:16]
    return f"emg_{ts}_{sig}"


def verify_emergency_token(alert_id: str, token: str) -> bool:
    """Verifies emergency token for zero-friction access during fire incidents."""
    try:
        parts = token.split("_")
        if len(parts) != 3 or parts[0] != "emg":
            return False
        ts = int(parts[1])
        if abs(time.time() - ts) > 10800:  # 3 hours validity
            return False
        secret = settings.INTERNAL_API_SECRET_KEY
        expected = hashlib.sha256(f"{alert_id}:{ts}:{secret}".encode()).hexdigest()[:16]
        return parts[2] == expected
    except Exception:
        return False


def create_firebase_custom_token(user_id: str) -> str:
    """Create Firebase Custom Token for Flutter App to sign in to Firebase SDK."""
    try:
        from ..services.firebase_service import init_firebase
        init_firebase()
        custom_token_bytes = fb_auth.create_custom_token(user_id)
        if isinstance(custom_token_bytes, bytes):
            return custom_token_bytes.decode("utf-8")
        return str(custom_token_bytes)
    except Exception as e:
        logger.warning(f"Firebase create_custom_token warning: {e}, falling back to mock custom token")
        return f"mock_custom_token_{user_id}_{int(time.time())}"


# ==============================================================================
# HYBRID REDIS + IN-MEMORY OTP SERVICE
# ==============================================================================

import json as _json
try:
    import redis as _redis_mod
except ImportError:
    _redis_mod = None


class OTPChallenge:
    def __init__(
        self,
        challenge_id: str,
        phone_number: str,
        purpose: str,  # "register" or "forgot_password"
        code: str = "123456",
        expires_at: Optional[datetime] = None,
        cooldown_until: Optional[datetime] = None,
        failed_attempts: int = 0,
        locked_until: Optional[datetime] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        self.challenge_id = challenge_id
        self.phone_number = phone_number
        self.purpose = purpose
        self.code = code
        self.expires_at = expires_at or (datetime.now(timezone.utc) + timedelta(seconds=60))
        self.cooldown_until = cooldown_until or (datetime.now(timezone.utc) + timedelta(seconds=60))
        self.failed_attempts = failed_attempts
        self.locked_until: Optional[datetime] = locked_until
        self.data = data or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "phone_number": self.phone_number,
            "purpose": self.purpose,
            "code": self.code,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "failed_attempts": self.failed_attempts,
            "locked_until": self.locked_until.isoformat() if self.locked_until else None,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OTPChallenge":
        return cls(
            challenge_id=d["challenge_id"],
            phone_number=d["phone_number"],
            purpose=d["purpose"],
            code=d.get("code", "123456"),
            expires_at=datetime.fromisoformat(d["expires_at"]) if d.get("expires_at") else None,
            cooldown_until=datetime.fromisoformat(d["cooldown_until"]) if d.get("cooldown_until") else None,
            failed_attempts=int(d.get("failed_attempts", 0)),
            locked_until=datetime.fromisoformat(d["locked_until"]) if d.get("locked_until") else None,
            data=d.get("data") or {},
        )


class OTPManager:
    """
    Hybrid Redis + In-Memory OTP Manager.
    Persists OTP challenges & password reset tokens in Redis (if available) with 10-minute TTL
    so challenges survive container restarts and work across multiple workers, while maintaining
    an automatic in-memory fallback.
    """
    def __init__(self):
        self._challenges: Dict[str, OTPChallenge] = {}
        self._reset_tokens: Dict[str, Dict[str, Any]] = {}
        self._redis = None
        self._init_redis()

    def _init_redis(self):
        if _redis_mod:
            try:
                redis_url = os.getenv("REDIS_URL", settings.REDIS_URL)
                self._redis = _redis_mod.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
                self._redis.ping()
            except Exception:
                self._redis = None

    def _save_challenge(self, challenge: OTPChallenge):
        self._challenges[challenge.challenge_id] = challenge
        if self._redis:
            try:
                self._redis.set(f"otp:challenge:{challenge.challenge_id}", _json.dumps(challenge.to_dict()), ex=600)
            except Exception:
                pass

    def _get_challenge(self, challenge_id: str) -> Optional[OTPChallenge]:
        if self._redis:
            try:
                raw = self._redis.get(f"otp:challenge:{challenge_id}")
                if raw:
                    chl = OTPChallenge.from_dict(_json.loads(raw))
                    self._challenges[challenge_id] = chl
                    return chl
            except Exception:
                pass
        return self._challenges.get(challenge_id)

    def create_challenge(
        self,
        phone_number: str,
        purpose: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[OTPChallenge, Optional[str]]:
        challenge_id = f"otp_chl_{purpose}_{uuid.uuid4().hex[:12]}"
        code = "123456"  # Dev default

        challenge = OTPChallenge(
            challenge_id=challenge_id,
            phone_number=phone_number,
            purpose=purpose,
            code=code,
            data=data,
        )
        self._save_challenge(challenge)
        dev_otp = code if settings.ENVIRONMENT == "development" else None
        return challenge, dev_otp

    def resend_otp(self, challenge_id: str) -> Tuple[OTPChallenge, Optional[str]]:
        challenge = self._get_challenge(challenge_id)
        if not challenge:
            raise OtpExpiredException()

        now = datetime.now(timezone.utc)
        if challenge.cooldown_until and now < challenge.cooldown_until:
            available_at = challenge.cooldown_until.isoformat()
            raise OtpResendCooldownException(available_at=available_at)

        new_chl, dev_otp = self.create_challenge(
            phone_number=challenge.phone_number,
            purpose=challenge.purpose,
            data=challenge.data,
        )
        # Keep old challenge valid so either ID can be verified
        challenge.code = new_chl.code
        challenge.expires_at = new_chl.expires_at
        challenge.failed_attempts = 0
        self._save_challenge(challenge)
        return new_chl, dev_otp

    def verify_code(self, challenge_id: str, code: str) -> Tuple[OTPChallenge, Optional[str]]:
        challenge = self._get_challenge(challenge_id)
        if not challenge:
            raise OtpExpiredException()

        now = datetime.now(timezone.utc)
        if challenge.locked_until and now < challenge.locked_until:
            retry_at = challenge.locked_until.isoformat()
            raise OtpLockedException(retry_at=retry_at)

        if now > challenge.expires_at:
            raise OtpExpiredException()

        if challenge.code != code.strip():
            challenge.failed_attempts += 1
            if challenge.failed_attempts >= 3:
                challenge.locked_until = now + timedelta(minutes=5)
                self._save_challenge(challenge)
                retry_at = challenge.locked_until.isoformat()
                raise OtpLockedException(retry_at=retry_at)
            self._save_challenge(challenge)
            attempts_left = 3 - challenge.failed_attempts
            raise OtpWrongException(attempts_left=attempts_left)

        # Success - generate reset token if purpose is forgot_password
        reset_token = None
        if challenge.purpose == "forgot_password":
            reset_token = f"rst_tok_{uuid.uuid4().hex}"
            tok_payload = {
                "phone_number": challenge.phone_number,
                "expires_at": (now + timedelta(minutes=15)).isoformat(),
            }
            self._reset_tokens[reset_token] = {
                "phone_number": challenge.phone_number,
                "expires_at": now + timedelta(minutes=15),
            }
            if self._redis:
                try:
                    self._redis.set(f"otp:reset_token:{reset_token}", _json.dumps(tok_payload), ex=900)
                except Exception:
                    pass

        return challenge, reset_token

    def verify_reset_token(self, token: str) -> str:
        now = datetime.now(timezone.utc)
        if self._redis:
            try:
                raw = self._redis.get(f"otp:reset_token:{token}")
                if raw:
                    parsed = _json.loads(raw)
                    exp = datetime.fromisoformat(parsed["expires_at"])
                    self._redis.delete(f"otp:reset_token:{token}")
                    if token in self._reset_tokens:
                        del self._reset_tokens[token]
                    if now > exp:
                        raise AppException(code="EXPIRED_RESET_TOKEN", message="Mã khôi phục đã hết hạn.", status_code=400)
                    return parsed["phone_number"]
            except AppException:
                raise
            except Exception:
                pass

        data = self._reset_tokens.get(token)
        if not data:
            raise AppException(code="INVALID_RESET_TOKEN", message="Mã khôi phục không hợp lệ hoặc đã hết hạn.", status_code=400)
        if now > data["expires_at"]:
            del self._reset_tokens[token]
            raise AppException(code="EXPIRED_RESET_TOKEN", message="Mã khôi phục đã hết hạn.", status_code=400)
        phone = data["phone_number"]
        del self._reset_tokens[token]
        return phone


otp_manager = OTPManager()


# ==============================================================================
# AUTHENTICATION DEPENDENCY
# ==============================================================================

async def get_current_user(
    authorization: Optional[str] = Header(None),
) -> Any:
    """
    Extracts Bearer token from header and authenticates user.
    Supports Firebase ID Token and development shortcut (usr_... token).
    """
    if not authorization:
        raise UnauthorizedException("Thiếu header xác thực Authorization.")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedException("Định dạng token không hợp lệ (yêu cầu Bearer token).", code="INVALID_TOKEN")

    user_id = None
    # Allow dev fallback for testing without blocking on external Google auth endpoints
    if settings.ENVIRONMENT == "development":
        if token.startswith("usr_"):
            clean_id = token
            while clean_id.startswith("usr_usr_"):
                clean_id = clean_id[4:]
            user_id = clean_id
        elif token.startswith("mock_custom_token_"):
            without_prefix = token[len("mock_custom_token_"):]
            user_id = without_prefix.rsplit("_", 1)[0]
        elif token == "demo_token":
            user_id = "usr_leader_matpho_01"
        elif token.startswith("eyJ"):
            # Allow dev testing with Firebase Custom Token in Postman
            try:
                import base64
                import json
                parts = token.split(".")
                if len(parts) >= 2:
                    payload_b64 = parts[1]
                    padding = len(payload_b64) % 4
                    if padding:
                        payload_b64 += "=" * (4 - padding)
                    payload_data = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
                    user_id = payload_data.get("uid") or payload_data.get("user_id") or payload_data.get("sub")
            except Exception as ex:
                logger.debug(f"Failed to decode dev JWT payload: {ex}")

    if not user_id:
        try:
            decoded = fb_auth.verify_id_token(token)
            user_id = decoded.get("uid")
        except Exception as e:
            logger.debug(f"Firebase token verification failed: {e}")

    if not user_id:
        raise UnauthorizedException("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", code="TOKEN_EXPIRED")

    from ..services.repositories.user_repo import get_user_repo
    repo = get_user_repo()
    user = repo.get_user_by_id(user_id)
    if not user:
        raise UnauthorizedException("Tài khoản không tồn tại trong hệ thống.", code="USER_NOT_FOUND")

    return user


async def get_optional_current_user(
    authorization: Optional[str] = Header(None),
) -> Optional[Any]:
    if not authorization:
        return None
    try:
        return await get_current_user(authorization)
    except Exception:
        return None


def verify_internal_secret(
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
) -> bool:
    """Verifies internal secret key for Edge AI / FireWatch Webhooks."""
    secret = settings.INTERNAL_API_SECRET_KEY
    if not x_internal_secret or x_internal_secret != secret:
        raise UnauthorizedException("Mã bảo mật nội bộ không hợp lệ hoặc bị thiếu.", code="INVALID_INTERNAL_SECRET")
    return True

