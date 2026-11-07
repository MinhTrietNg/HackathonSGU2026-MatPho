import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/errors.dart';
import '../fakes/fake_auth_repository.dart';
import '../fakes/fake_data.dart';
import '../fakes/fake_scenario.dart';
import '../fakes/fake_world.dart';
import 'package:mat_pho/data/models/models.dart';

FakeAuthRepository repo([Set<FakeCase> cases = const {}]) =>
    FakeAuthRepository(FakeWorld(FakeScenario.test(cases: cases)));

void main() {
  const phone = '0912 345 678';

  group('session (A1)', () {
    test('restores the signed-in user', () async {
      expect(await repo().restoreSession(), FakeData.user);
    });

    test('signedOut → null (A5)', () async {
      expect(await repo({FakeCase.signedOut}).restoreSession(), isNull);
    });
  });

  group('login (A5/A6)', () {
    test('a registered number cannot register again (B1)', () async {
      await expectLater(
        repo().checkPhoneAvailable(phone),
        throwsA(isA<PhoneAlreadyRegisteredException>()),
      );
      await repo().checkPhoneAvailable('0933 222 111');
    });

    test('correct credentials sign in', () async {
      final user = await repo().login(
        phone: phone,
        password: FakeData.password,
      );
      expect(user.fullName, 'Nguyễn Minh Anh');
    });

    test('wrong passwords count down then lock 15 minutes', () async {
      final auth = repo();
      for (final left in [4, 3, 2, 1]) {
        await expectLater(
          auth.login(phone: phone, password: 'sai'),
          throwsA(
            isA<WrongPasswordException>().having(
              (e) => e.attemptsLeft,
              'attemptsLeft',
              left,
            ),
          ),
        );
      }
      await expectLater(
        auth.login(phone: phone, password: 'sai'),
        throwsA(
          isA<AccountLockedException>().having(
            (e) => e.until,
            'until',
            FakeData.demoNow.add(const Duration(minutes: 15)),
          ),
        ),
      );
      await expectLater(
        auth.login(phone: phone, password: FakeData.password),
        throwsA(isA<AccountLockedException>()),
      );
    });

    test('forced A6 cases', () async {
      await expectLater(
        repo({FakeCase.wrongPassword}).login(phone: phone, password: 'x'),
        throwsA(
          isA<WrongPasswordException>().having(
            (e) => e.attemptsLeft,
            'attemptsLeft',
            3,
          ),
        ),
      );
      await expectLater(
        repo({
          FakeCase.accountLocked,
        }).login(phone: phone, password: FakeData.password),
        throwsA(isA<AccountLockedException>()),
      );
      await expectLater(
        repo({
          FakeCase.loginNetworkError,
        }).login(phone: phone, password: FakeData.password),
        throwsA(isA<NetworkException>()),
      );
    });
  });

  group('register (B1 → B2 → C1)', () {
    test('sends an OTP, correct code signs in', () async {
      final auth = repo();
      final challenge = await auth.register(
        fullName: 'Nguyễn Minh Anh',
        phone: '0933 222 111',
        password: 'matkhau123',
      );
      expect(challenge.purpose, OtpPurpose.register);
      expect(challenge.phone, '0933222111');
      expect(
        challenge.resendAvailableAt,
        FakeData.demoNow.add(FakeData.otpResendCooldown),
      );
      final result = await auth.verifyOtp(
        challenge: challenge,
        code: FakeData.otpCode,
      );
      expect(result, isA<RegistrationCompleted>());
      expect(await auth.restoreSession(), isNotNull);
    });

    test('a new account has only its personal group (verify-otp)', () async {
      final world = FakeWorld(const FakeScenario.test());
      final auth = FakeAuthRepository(world);
      final challenge = await auth.register(
        fullName: 'Trần Văn Bình',
        phone: '0933 222 111',
        password: 'matkhau789',
      );
      await auth.verifyOtp(challenge: challenge, code: FakeData.otpCode);
      final user = world.user;
      expect(user.fullName, 'Trần Văn Bình');
      final personal = world.groups.single;
      expect(personal, FakeData.personalGroupOf(user));
      expect(personal.id, 'g-personal-${user.id}');
      expect(personal.isPersonal, isTrue);
      expect(personal.myNickname, 'Trần Văn Bình');
      expect(world.members[personal.id]!.single.isYou, isTrue);
      expect(world.cameras, isEmpty);
      expect(world.areas, isEmpty);
      expect(world.events, isEmpty);
    });

    test('phone already registered (B1)', () async {
      await expectLater(
        repo({FakeCase.phoneExists}).checkPhoneAvailable(phone),
        throwsA(isA<PhoneAlreadyRegisteredException>()),
      );
      await expectLater(
        repo({
          FakeCase.phoneExists,
        }).register(fullName: 'A', phone: phone, password: 'matkhau123'),
        throwsA(isA<PhoneAlreadyRegisteredException>()),
      );
    });
  });

  group('OTP (B2/B3)', () {
    Future<(FakeAuthRepository, OtpChallenge)> start([
      Set<FakeCase> cases = const {},
    ]) async {
      final auth = repo(cases);
      return (auth, await auth.requestPasswordReset(phone));
    }

    test('wrong codes: 2, 1 left, then wait 5 minutes', () async {
      final (auth, challenge) = await start();
      for (final left in [2, 1]) {
        await expectLater(
          auth.verifyOtp(challenge: challenge, code: '482910'),
          throwsA(
            isA<OtpWrongException>().having(
              (e) => e.attemptsLeft,
              'attemptsLeft',
              left,
            ),
          ),
        );
      }
      await expectLater(
        auth.verifyOtp(challenge: challenge, code: '482910'),
        throwsA(
          isA<OtpLockedException>().having(
            (e) => e.retryAt,
            'retryAt',
            FakeData.demoNow.add(const Duration(minutes: 5)),
          ),
        ),
      );
    });

    test('forced B3 cases', () async {
      final (wrong, c1) = await start({FakeCase.otpWrong});
      await expectLater(
        wrong.verifyOtp(challenge: c1, code: FakeData.otpCode),
        throwsA(
          isA<OtpWrongException>().having((e) => e.attemptsLeft, 'left', 2),
        ),
      );
      final (expired, c2) = await start({FakeCase.otpExpired});
      await expectLater(
        expired.verifyOtp(challenge: c2, code: FakeData.otpCode),
        throwsA(isA<OtpExpiredException>()),
      );
      final (locked, c3) = await start({FakeCase.otpLocked});
      await expectLater(
        locked.verifyOtp(challenge: c3, code: FakeData.otpCode),
        throwsA(isA<OtpLockedException>()),
      );
    });

    test('resend waits for the countdown, except when expired', () async {
      final (auth, challenge) = await start();
      await expectLater(
        auth.resendOtp(challenge),
        throwsA(isA<OtpResendCooldownException>()),
      );
      final (expired, c2) = await start({FakeCase.otpExpired});
      final again = await expired.resendOtp(c2);
      expect(again.id, isNot(c2.id));
    });

    test('password reset → B5 → new password works', () async {
      final (auth, challenge) = await start();
      final result = await auth.verifyOtp(
        challenge: challenge,
        code: FakeData.otpCode,
      );
      final token = (result as PasswordResetAuthorized).resetToken;
      await auth.setNewPassword(resetToken: token, newPassword: 'moi12345');
      expect(
        (await auth.login(phone: phone, password: 'moi12345')).id,
        FakeData.user.id,
      );
    });

    test('phone not registered (B4)', () async {
      await expectLater(
        repo({FakeCase.phoneNotRegistered}).requestPasswordReset(phone),
        throwsA(isA<PhoneNotRegisteredException>()),
      );
    });
  });
}
