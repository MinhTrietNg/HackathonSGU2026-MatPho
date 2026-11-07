import '../models/user.dart';

abstract interface class AuthRepository {
  Future<User?> restoreSession();

  Future<User> login({required String phone, required String password});

  Future<void> checkPhoneAvailable(String phone);

  Future<OtpChallenge> register({
    required String fullName,
    required String phone,
    required String password,
  });

  Future<OtpChallenge> requestPasswordReset(String phone);

  Future<OtpVerified> verifyOtp({
    required OtpChallenge challenge,
    required String code,
  });

  Future<OtpChallenge> resendOtp(OtpChallenge challenge);

  Future<void> setNewPassword({
    required String resetToken,
    required String newPassword,
  });
}
