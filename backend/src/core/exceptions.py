"""
Domain Exceptions for Mắt Phố Backend
Unified format: { "error": { "code": "...", "message": "...", "details": {...} } }
"""

from typing import Optional, Dict, Any


class AppException(Exception):
    """Base application exception with unified code and structured details."""

    def __init__(
        self,
        code: str = "INTERNAL_ERROR",
        message: str = "Đã xảy ra lỗi trong quá trình xử lý.",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationException(AppException):
    def __init__(self, message: str = "Dữ liệu yêu cầu không hợp lệ.", details: Optional[Dict[str, Any]] = None):
        super().__init__(code="VALIDATION_ERROR", message=message, status_code=422, details=details)


class WrongPasswordException(AppException):
    def __init__(self, attempts_left: int = 4):
        super().__init__(
            code="WRONG_PASSWORD",
            message="Số điện thoại hoặc mật khẩu không chính xác.",
            status_code=422,
            details={"attempts_left": attempts_left},
        )


class OtpWrongException(AppException):
    def __init__(self, attempts_left: int = 2):
        super().__init__(
            code="OTP_WRONG",
            message="Mã OTP không chính xác.",
            status_code=422,
            details={"attempts_left": attempts_left},
        )


class AccountLockedException(AppException):
    def __init__(self, locked_until: str):
        super().__init__(
            code="ACCOUNT_LOCKED",
            message="Tài khoản tạm thời bị khóa do nhập sai mật khẩu quá 5 lần. Vui lòng thử lại sau.",
            status_code=423,
            details={"locked_until": locked_until},
        )


class OtpLockedException(AppException):
    def __init__(self, retry_at: str):
        super().__init__(
            code="OTP_LOCKED",
            message="Bạn đã nhập sai OTP quá 3 lần. Vui lòng thử lại sau 5 phút.",
            status_code=429,
            details={"retry_at": retry_at},
        )


class OtpResendCooldownException(AppException):
    def __init__(self, available_at: str):
        super().__init__(
            code="OTP_RESEND_COOLDOWN",
            message="Vui lòng chờ trước khi yêu cầu gửi lại OTP.",
            status_code=429,
            details={"available_at": available_at},
        )


class OtpExpiredException(AppException):
    def __init__(self):
        super().__init__(
            code="OTP_EXPIRED",
            message="Mã OTP đã hết hạn sau 60 giây. Vui lòng yêu cầu mã mới.",
            status_code=410,
        )


class InvitationUnavailableException(AppException):
    def __init__(self, message: str = "Lời mời không khả dụng hoặc đã được xử lý."):
        super().__init__(code="INVITATION_UNAVAILABLE", message=message, status_code=410)


class NotFoundException(AppException):
    def __init__(self, message: str = "Không tìm thấy tài nguyên yêu cầu.", code: str = "NOT_FOUND"):
        super().__init__(code=code, message=message, status_code=404)


class PermissionDeniedException(AppException):
    def __init__(self, message: str = "Bạn không có quyền thực hiện hành động này."):
        super().__init__(code="PERMISSION_DENIED", message=message, status_code=403)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Phiên làm việc không hợp lệ hoặc đã hết hạn.", code: str = "UNAUTHORIZED"):
        super().__init__(code=code, message=message, status_code=401)


class ConflictException(AppException):
    def __init__(self, message: str = "Dữ liệu bị xung đột.", code: str = "CONFLICT"):
        super().__init__(code=code, message=message, status_code=409)


class ServiceUnavailableException(AppException):
    def __init__(self, message: str = "Dịch vụ tạm thời không khả dụng.", code: str = "SERVICE_UNAVAILABLE"):
        super().__init__(code=code, message=message, status_code=503)
