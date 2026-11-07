final class User {
  const User({
    required this.id,
    required this.fullName,
    required this.phone,
    this.loudWhenSilent = true,
    this.personalGroupId,
  });

  final String id;

  final String fullName;

  final String phone;

  final bool loudWhenSilent;

  final String? personalGroupId;

  @override
  bool operator ==(Object other) =>
      other is User &&
      other.id == id &&
      other.fullName == fullName &&
      other.phone == phone &&
      other.loudWhenSilent == loudWhenSilent &&
      other.personalGroupId == personalGroupId;

  @override
  int get hashCode =>
      Object.hash(id, fullName, phone, loudWhenSilent, personalGroupId);
}

enum OtpPurpose { register, passwordReset }

final class OtpChallenge {
  const OtpChallenge({
    required this.id,
    required this.phone,
    required this.purpose,
    required this.resendAvailableAt,
  });

  final String id;

  final String phone;
  final OtpPurpose purpose;

  final DateTime resendAvailableAt;
}

sealed class OtpVerified {
  const OtpVerified();
}

final class RegistrationCompleted extends OtpVerified {
  const RegistrationCompleted(this.user);

  final User user;
}

final class PasswordResetAuthorized extends OtpVerified {
  const PasswordResetAuthorized(this.resetToken);

  final String resetToken;
}

const minPasswordLength = 8;

const maxLoginAttempts = 5;
const loginLockDuration = Duration(minutes: 15);

const maxOtpAttempts = 3;
const otpLockDuration = Duration(minutes: 5);
const otpLength = 6;

typedef PasswordChecks = ({bool minLength, bool lettersAndDigits, bool match});

PasswordChecks checkNewPassword(String password, String confirmation) => (
  minLength: password.length >= minPasswordLength,
  lettersAndDigits:
      RegExp(r'\p{L}', unicode: true).hasMatch(password) &&
      RegExp(r'\d').hasMatch(password),
  match: password.isNotEmpty && password == confirmation,
);

extension PasswordChecksX on PasswordChecks {
  bool get allMet => minLength && lettersAndDigits && match;
}

bool isValidVnPhone(String input) =>
    RegExp(r'^0\d{9}$').hasMatch(input.replaceAll(' ', ''));

String formatPhone(String digits) => digits.length == 10
    ? '${digits.substring(0, 4)} ${digits.substring(4, 7)} '
          '${digits.substring(7)}'
    : digits;

String maskPhone(String digits) => digits.length == 10
    ? '${digits.substring(0, 4)} ••• ${digits.substring(7)}'
    : digits;
