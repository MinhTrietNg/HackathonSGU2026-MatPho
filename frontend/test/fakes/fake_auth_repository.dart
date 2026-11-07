import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/user.dart';
import 'package:mat_pho/data/repositories/auth_repository.dart';
import 'fake_data.dart';
import 'fake_scenario.dart';
import 'fake_world.dart';

final class FakeAuthRepository implements AuthRepository {
  FakeAuthRepository(this._world);

  final FakeWorld _world;

  FakeScenario get _s => _world.scenario;

  @override
  Future<User?> restoreSession() async {
    await _world.delay();
    return _world.signedIn ? _world.user : null;
  }

  @override
  Future<User> login({required String phone, required String password}) async {
    await _world.delay();
    if (_s.has(FakeCase.loginNetworkError)) throw const NetworkException();
    final now = _world.now();
    if (_s.has(FakeCase.accountLocked)) {
      throw AccountLockedException(until: now.add(loginLockDuration));
    }
    if (_s.has(FakeCase.wrongPassword)) {
      throw const WrongPasswordException(attemptsLeft: 3);
    }
    final lockedUntil = _world.lockedUntil;
    if (lockedUntil != null && now.isBefore(lockedUntil)) {
      throw AccountLockedException(until: lockedUntil);
    }
    final digits = phone.replaceAll(' ', '');
    if (digits != _world.user.phone || password != _world.password) {
      _world.failedLogins++;
      final left = maxLoginAttempts - _world.failedLogins;
      if (left <= 0) {
        _world.failedLogins = 0;
        final until = now.add(loginLockDuration);
        _world.lockedUntil = until;
        throw AccountLockedException(until: until);
      }
      throw WrongPasswordException(attemptsLeft: left);
    }
    _world.failedLogins = 0;
    _world.lockedUntil = null;
    _world.signedIn = true;
    return _world.user;
  }

  @override
  Future<void> checkPhoneAvailable(String phone) async {
    await _world.delay();
    final digits = phone.replaceAll(' ', '');
    if (_s.has(FakeCase.phoneExists) ||
        digits == _world.user.phone ||
        FakeData.registeredPhones.contains(digits)) {
      throw const PhoneAlreadyRegisteredException();
    }
  }

  @override
  Future<OtpChallenge> register({
    required String fullName,
    required String phone,
    required String password,
  }) async {
    await checkPhoneAvailable(phone);
    _pendingRegistration = User(
      id: _world.newId('u'),
      fullName: fullName,
      phone: phone.replaceAll(' ', ''),
    );
    _pendingPassword = password;
    return _challenge(phone, OtpPurpose.register);
  }

  User? _pendingRegistration;
  String? _pendingPassword;

  @override
  Future<OtpChallenge> requestPasswordReset(String phone) async {
    await _world.delay();
    if (_s.has(FakeCase.phoneNotRegistered)) {
      throw const PhoneNotRegisteredException();
    }
    return _challenge(phone, OtpPurpose.passwordReset);
  }

  OtpChallenge _challenge(String phone, OtpPurpose purpose) {
    _world.failedOtps = 0;
    return OtpChallenge(
      id: _world.newId('otp'),
      phone: phone.replaceAll(' ', ''),
      purpose: purpose,
      resendAvailableAt: _world.now().add(FakeData.otpResendCooldown),
    );
  }

  @override
  Future<OtpVerified> verifyOtp({
    required OtpChallenge challenge,
    required String code,
  }) async {
    await _world.delay();
    if (_s.has(FakeCase.otpExpired)) throw const OtpExpiredException();
    if (_s.has(FakeCase.otpLocked)) {
      throw OtpLockedException(retryAt: _world.now().add(otpLockDuration));
    }
    if (_s.has(FakeCase.otpWrong)) {
      throw const OtpWrongException(attemptsLeft: 2);
    }
    if (code != FakeData.otpCode) {
      _world.failedOtps++;
      final left = maxOtpAttempts - _world.failedOtps;
      if (left <= 0) {
        throw OtpLockedException(retryAt: _world.now().add(otpLockDuration));
      }
      throw OtpWrongException(attemptsLeft: left);
    }
    switch (challenge.purpose) {
      case OtpPurpose.register:
        if (_pendingRegistration case final account?) {
          _world.startNewAccount(account);
        }
        _world.password = _pendingPassword ?? _world.password;
        _world.signedIn = true;
        return RegistrationCompleted(_world.user);
      case OtpPurpose.passwordReset:
        return const PasswordResetAuthorized('fake-reset-token');
    }
  }

  @override
  Future<OtpChallenge> resendOtp(OtpChallenge challenge) async {
    await _world.delay();
    final now = _world.now();
    if (!_s.has(FakeCase.otpExpired) &&
        now.isBefore(challenge.resendAvailableAt)) {
      throw OtpResendCooldownException(
        availableAt: challenge.resendAvailableAt,
      );
    }
    return _challenge(challenge.phone, challenge.purpose);
  }

  @override
  Future<void> setNewPassword({
    required String resetToken,
    required String newPassword,
  }) async {
    await _world.delay();
    _world.password = newPassword;
  }
}
