library;

import 'dart:convert';

import '../../errors.dart';
import 'json.dart';

MpException decodeApiError(int statusCode, String body) {
  final (code, details) = _parse(body);
  try {
    return switch (code) {
      'WRONG_PASSWORD' => WrongPasswordException(
        attemptsLeft: readIntOrNull(details, 'attempts_left'),
      ),
      'ACCOUNT_LOCKED' => AccountLockedException(
        until: readDateTime(details, 'locked_until'),
      ),
      'PHONE_ALREADY_REGISTERED' => const PhoneAlreadyRegisteredException(),
      'PHONE_NOT_REGISTERED' => const PhoneNotRegisteredException(),
      'ALREADY_IN_GROUP' => const AlreadyInGroupException(),
      'OTP_WRONG' => OtpWrongException(
        attemptsLeft: readInt(details, 'attempts_left'),
      ),
      'OTP_EXPIRED' => const OtpExpiredException(),
      'OTP_LOCKED' => OtpLockedException(
        retryAt: readDateTime(details, 'retry_at'),
      ),
      'OTP_RESEND_COOLDOWN' => OtpResendCooldownException(
        availableAt: readDateTime(details, 'available_at'),
      ),
      'CAMERA_NO_RESPONSE' => CameraNoResponseException(
        cameraName: _deviceName(details),
      ),
      'CAMERA_AUTH_FAILED' => CameraAuthFailedException(
        cameraName: _deviceName(details),
      ),
      'CAMERA_NOT_REACHABLE' => NotOnCompanyWifiException(
        cameraName: _deviceName(details),
      ),
      'CAMERA_VENDOR_BLOCKED' => VendorBlockedException(
        cameraName: _deviceName(details),
      ),
      'SUBGROUP_HAS_CAMERAS' => const AreaNotEmptyException(),
      'PERMISSION_DENIED' => const PermissionDeniedException(),
      'INVITATION_UNAVAILABLE' => const InvitationUnavailableException(),
      _ when statusCode == 403 => const PermissionDeniedException(),
      _ => ServerException(code: code, message: 'HTTP $statusCode'),
    };
  } on ServerException catch (e) {
    return ServerException(code: code, message: e.message);
  }
}

String _deviceName(Map<String, Object?> details) {
  String? text(String key) {
    final value = details[key];
    return value is String && value.trim().isNotEmpty ? value.trim() : null;
  }

  return text('device_name') ?? text('host') ?? '';
}

(String?, Map<String, Object?>) _parse(String body) {
  Object? decoded;
  try {
    decoded = jsonDecode(body);
  } on FormatException {
    return (null, const {});
  }
  if (decoded is! Map<String, Object?>) return (null, const {});
  final error = decoded['error'];
  if (error is Map<String, Object?>) {
    final code = error['code'];
    final details = error['details'];
    return (
      code is String ? code : null,
      details is Map<String, Object?> ? details : const {},
    );
  }
  if (decoded['detail'] is List) return ('VALIDATION_ERROR', const {});
  return (null, const {});
}
