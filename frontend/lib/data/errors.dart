library;

sealed class MpException implements Exception {
  const MpException();
}

final class NetworkException extends MpException {
  const NetworkException();

  @override
  String toString() => 'NetworkException()';
}

final class ServerException extends MpException {
  const ServerException({this.code, this.message});

  final String? code;
  final String? message;

  @override
  String toString() => 'ServerException(code: $code, message: $message)';
}

final class SessionExpiredException extends MpException {
  const SessionExpiredException();

  @override
  String toString() => 'SessionExpiredException()';
}

final class WrongPasswordException extends MpException {
  const WrongPasswordException({this.attemptsLeft});

  final int? attemptsLeft;

  @override
  String toString() => 'WrongPasswordException(attemptsLeft: $attemptsLeft)';
}

final class AccountLockedException extends MpException {
  const AccountLockedException({required this.until});

  final DateTime until;

  @override
  String toString() => 'AccountLockedException(until: $until)';
}

final class PhoneAlreadyRegisteredException extends MpException {
  const PhoneAlreadyRegisteredException();

  @override
  String toString() => 'PhoneAlreadyRegisteredException()';
}

final class PhoneNotRegisteredException extends MpException {
  const PhoneNotRegisteredException();

  @override
  String toString() => 'PhoneNotRegisteredException()';
}

final class AlreadyInGroupException extends MpException {
  const AlreadyInGroupException();

  @override
  String toString() => 'AlreadyInGroupException()';
}

final class OtpWrongException extends MpException {
  const OtpWrongException({required this.attemptsLeft});

  final int attemptsLeft;

  @override
  String toString() => 'OtpWrongException(attemptsLeft: $attemptsLeft)';
}

final class OtpExpiredException extends MpException {
  const OtpExpiredException();

  @override
  String toString() => 'OtpExpiredException()';
}

final class OtpLockedException extends MpException {
  const OtpLockedException({required this.retryAt});

  final DateTime retryAt;

  @override
  String toString() => 'OtpLockedException(retryAt: $retryAt)';
}

final class OtpResendCooldownException extends MpException {
  const OtpResendCooldownException({required this.availableAt});

  final DateTime availableAt;

  @override
  String toString() => 'OtpResendCooldownException(availableAt: $availableAt)';
}

sealed class CameraConnectException extends MpException {
  const CameraConnectException({required this.cameraName});

  final String cameraName;
}

final class CameraNoResponseException extends CameraConnectException {
  const CameraNoResponseException({required super.cameraName});

  @override
  String toString() => 'CameraNoResponseException($cameraName)';
}

final class CameraAuthFailedException extends CameraConnectException {
  const CameraAuthFailedException({required super.cameraName});

  @override
  String toString() => 'CameraAuthFailedException($cameraName)';
}

final class NotOnCompanyWifiException extends CameraConnectException {
  const NotOnCompanyWifiException({required super.cameraName});

  @override
  String toString() => 'NotOnCompanyWifiException($cameraName)';
}

final class VendorBlockedException extends CameraConnectException {
  const VendorBlockedException({required super.cameraName});

  @override
  String toString() => 'VendorBlockedException($cameraName)';
}

final class AreaNotEmptyException extends MpException {
  const AreaNotEmptyException();

  @override
  String toString() => 'AreaNotEmptyException()';
}

final class PermissionDeniedException extends MpException {
  const PermissionDeniedException();

  @override
  String toString() => 'PermissionDeniedException()';
}

final class InvitationUnavailableException extends MpException {
  const InvitationUnavailableException();

  @override
  String toString() => 'InvitationUnavailableException()';
}
