import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/user.dart';

import 'remote_harness.dart';

void main() {
  late RemoteHarness h;

  setUp(() => h = RemoteHarness());
  tearDown(() => h.dispose());

  final now = DateTime.utc(2026, 11, 4, 12);

  group('§3.1 login', () {
    void answerLogin() => h.on(
      'POST',
      '/auth/login',
      (_) => jsonResponse({
        'custom_token': 'eyJhbGciOiJSUzI1NiIs',
        'user': contractUser,
      }),
    );

    test('sends phone, password and fcm_token without a bearer', () async {
      answerLogin();
      await h.auth().login(phone: '0912 345 678', password: 'matkhau123');
      final request = h.last;
      expect(request.method, 'POST');
      expect(request.url.toString(), 'https://api.test/api/v1/auth/login');
      expect(request.headers.containsKey('Authorization'), isFalse);
      expect(h.bodyOf(request), {
        'phone_number': '0912345678',
        'password': 'matkhau123',
        'fcm_token': 'fcm_device_token_xyz',
      });
    });

    test('no push token: fcm_token is left out', () async {
      h.push.value = null;
      answerLogin();
      await h.auth().login(phone: '0912345678', password: 'matkhau123');
      expect(h.bodyOf(h.last).containsKey('fcm_token'), isFalse);
    });

    test('parses the user, signs in with the custom token, saves the '
        'session and opens the socket', () async {
      answerLogin();
      final user = await h.auth().login(
        phone: '0912345678',
        password: 'matkhau123',
      );
      expect(
        user,
        const User(
          id: 'usr_abc123',
          fullName: 'Nguyễn Minh Anh',
          phone: '0912345678',
          loudWhenSilent: true,
          personalGroupId: 'grp_personal_usr_abc123',
        ),
      );
      expect(h.tokens.customTokens, ['eyJhbGciOiJSUzI1NiIs']);
      expect(h.tokens.isSignedIn, isTrue);
      expect(h.store.user, contractUser);
      await pumpEventQueue();
      expect(h.channels, hasLength(1));
      expect(h.channels.single.headers, {
        'Authorization': 'Bearer id-for-eyJhbGciOiJSUzI1NiIs',
      });
    });

    test('422 WRONG_PASSWORD → attempts left (A6)', () async {
      h.on(
        'POST',
        '/auth/login',
        (_) => errorResponse(422, 'WRONG_PASSWORD', {'attempts_left': 3}),
      );
      await expectLater(
        h.auth().login(phone: '0912345678', password: 'sai'),
        throwsA(
          isA<WrongPasswordException>().having(
            (e) => e.attemptsLeft,
            'attemptsLeft',
            3,
          ),
        ),
      );
      expect(h.tokens.isSignedIn, isFalse);
      expect(h.store.user, isNull);
    });

    test('423 ACCOUNT_LOCKED → locked until, local time (A6)', () async {
      h.on(
        'POST',
        '/auth/login',
        (_) => errorResponse(423, 'ACCOUNT_LOCKED', {
          'locked_until': '2026-11-04T12:15:00.000Z',
        }),
      );
      await expectLater(
        h.auth().login(phone: '0912345678', password: 'sai'),
        throwsA(
          isA<AccountLockedException>().having(
            (e) => e.until,
            'until',
            DateTime.utc(2026, 11, 4, 12, 15).toLocal(),
          ),
        ),
      );
    });

    test('a reply without custom_token is a server error', () async {
      h.on('POST', '/auth/login', (_) => jsonResponse({'user': contractUser}));
      await expectLater(
        h.auth().login(phone: '0912345678', password: 'matkhau123'),
        throwsA(isA<ServerException>()),
      );
      expect(h.store.user, isNull);
    });
  });

  group('§3.2 check-phone (B1)', () {
    test('available → ok; sent without a bearer', () async {
      h.on(
        'POST',
        '/auth/check-phone',
        (_) => jsonResponse({
          'phone_number': '+84912345678',
          'is_available': true,
        }),
      );
      await h.auth().checkPhoneAvailable('0912 345 678');
      expect(h.bodyOf(h.last), {'phone_number': '0912345678'});
      expect(h.last.headers.containsKey('Authorization'), isFalse);
    });

    test('taken → PhoneAlreadyRegisteredException', () async {
      h.on(
        'POST',
        '/auth/check-phone',
        (_) => jsonResponse({
          'phone_number': '+84912345678',
          'is_available': false,
        }),
      );
      await expectLater(
        h.auth().checkPhoneAvailable('0912345678'),
        throwsA(isA<PhoneAlreadyRegisteredException>()),
      );
    });
  });

  group('§3.3 / §3.4 request OTP', () {
    const challengeReply = {
      'challenge_id': 'otp_chl_reg_88a91c',
      'expires_in': 60,
      'resend_cooldown': 60,
      'dev_otp': '123456',
    };

    test('register: body, challenge with a 60 s countdown', () async {
      h.on(
        'POST',
        '/auth/register/request-otp',
        (_) => jsonResponse(challengeReply),
      );
      final challenge = await h
          .auth(now: () => now)
          .register(
            fullName: 'Nguyễn Minh Anh',
            phone: '0912 345 678',
            password: 'matkhau123',
          );
      expect(h.bodyOf(h.last), {
        'phone_number': '0912345678',
        'full_name': 'Nguyễn Minh Anh',
        'password': 'matkhau123',
      });
      expect(h.last.headers.containsKey('Authorization'), isFalse);
      expect(challenge.id, 'otp_chl_reg_88a91c');
      expect(challenge.phone, '0912345678');
      expect(challenge.purpose, OtpPurpose.register);
      expect(challenge.resendAvailableAt, now.add(const Duration(seconds: 60)));
    });

    test('register: 409 PHONE_ALREADY_REGISTERED (B1)', () async {
      h.on(
        'POST',
        '/auth/register/request-otp',
        (_) => errorResponse(409, 'PHONE_ALREADY_REGISTERED'),
      );
      await expectLater(
        h.auth().register(
          fullName: 'A',
          phone: '0912345678',
          password: 'matkhau123',
        ),
        throwsA(isA<PhoneAlreadyRegisteredException>()),
      );
    });

    test('forgot password: body and a reset challenge', () async {
      h.on(
        'POST',
        '/auth/forgot-password/request-otp',
        (_) => jsonResponse({
          ...challengeReply,
          'challenge_id': 'otp_chl_reset_55f2b',
        }),
      );
      final challenge = await h.auth().requestPasswordReset('0912 345 678');
      expect(h.bodyOf(h.last), {'phone_number': '0912345678'});
      expect(challenge.id, 'otp_chl_reset_55f2b');
      expect(challenge.purpose, OtpPurpose.passwordReset);
    });

    test('forgot password: 404 PHONE_NOT_REGISTERED (B4)', () async {
      h.on(
        'POST',
        '/auth/forgot-password/request-otp',
        (_) => errorResponse(404, 'PHONE_NOT_REGISTERED'),
      );
      await expectLater(
        h.auth().requestPasswordReset('0912345678'),
        throwsA(isA<PhoneNotRegisteredException>()),
      );
    });
  });

  group('§3.5 verify-otp', () {
    final registerChallenge = OtpChallenge(
      id: 'otp_chl_reg_88a91c',
      phone: '0912345678',
      purpose: OtpPurpose.register,
      resendAvailableAt: now,
    );

    test('REGISTER_SUCCESS: body with fcm_token, signed in, saved', () async {
      const user = {
        'user_id': 'usr_abc123',
        'phone_number': '+84912345678',
        'full_name': 'Nguyễn Minh Anh',
        'personal_group_id': 'grp_personal_usr_abc123',
      };
      h.on(
        'POST',
        '/auth/verify-otp',
        (_) => jsonResponse({
          'type': 'REGISTER_SUCCESS',
          'custom_token': 'eyJhbGciOiJSUzI1NiIs',
          'user': user,
        }),
      );
      final verified = await h.auth().verifyOtp(
        challenge: registerChallenge,
        code: '123456',
      );
      expect(h.bodyOf(h.last), {
        'challenge_id': 'otp_chl_reg_88a91c',
        'code': '123456',
        'fcm_token': 'fcm_device_token_xyz',
      });
      expect(h.last.headers.containsKey('Authorization'), isFalse);
      expect(
        verified,
        isA<RegistrationCompleted>().having(
          (r) => r.user,
          'user',
          const User(
            id: 'usr_abc123',
            fullName: 'Nguyễn Minh Anh',
            phone: '0912345678',
            personalGroupId: 'grp_personal_usr_abc123',
          ),
        ),
      );
      expect(h.tokens.customTokens, ['eyJhbGciOiJSUzI1NiIs']);
      expect(h.store.user, user);
    });

    test('RESET_PASSWORD_VERIFIED → reset token, no session', () async {
      h.on(
        'POST',
        '/auth/verify-otp',
        (_) => jsonResponse({
          'type': 'RESET_PASSWORD_VERIFIED',
          'reset_token': 'rst_tok_v1_9921abcf',
        }),
      );
      final verified = await h.auth().verifyOtp(
        challenge: OtpChallenge(
          id: 'otp_chl_reset_55f2b',
          phone: '0912345678',
          purpose: OtpPurpose.passwordReset,
          resendAvailableAt: now,
        ),
        code: '123456',
      );
      expect(
        verified,
        isA<PasswordResetAuthorized>().having(
          (r) => r.resetToken,
          'resetToken',
          'rst_tok_v1_9921abcf',
        ),
      );
      expect(h.tokens.isSignedIn, isFalse);
      expect(h.store.user, isNull);
    });

    test('B3 errors: OTP_WRONG, OTP_EXPIRED, OTP_LOCKED', () async {
      Future<void> expectError(
        int status,
        String code,
        Map<String, Object?>? details,
        Matcher matcher,
      ) async {
        h.on(
          'POST',
          '/auth/verify-otp',
          (_) => errorResponse(status, code, details),
        );
        await expectLater(
          h.auth().verifyOtp(challenge: registerChallenge, code: '482910'),
          throwsA(matcher),
        );
      }

      await expectError(
        422,
        'OTP_WRONG',
        {'attempts_left': 2},
        isA<OtpWrongException>().having(
          (e) => e.attemptsLeft,
          'attemptsLeft',
          2,
        ),
      );
      await expectError(410, 'OTP_EXPIRED', null, isA<OtpExpiredException>());
      await expectError(
        429,
        'OTP_LOCKED',
        {'retry_at': '2026-11-04T12:05:00+00:00'},
        isA<OtpLockedException>().having(
          (e) => e.retryAt,
          'retryAt',
          DateTime.utc(2026, 11, 4, 12, 5).toLocal(),
        ),
      );
    });
  });

  group('§3.6 resend-otp', () {
    final challenge = OtpChallenge(
      id: 'otp_chl_reg_88a91c',
      phone: '0912345678',
      purpose: OtpPurpose.register,
      resendAvailableAt: now,
    );

    test('contract reply (no resend_cooldown): the app counts 60 s', () async {
      h.on(
        'POST',
        '/auth/resend-otp',
        (_) => jsonResponse({
          'challenge_id': 'otp_chl_reg_new',
          'expires_in': 60,
          'dev_otp': '123456',
        }),
      );
      final later = now.add(const Duration(seconds: 70));
      final next = await h.auth(now: () => later).resendOtp(challenge);
      expect(h.bodyOf(h.last), {'challenge_id': 'otp_chl_reg_88a91c'});
      expect(next.id, 'otp_chl_reg_new');
      expect(next.phone, '0912345678');
      expect(next.purpose, OtpPurpose.register);
      expect(next.resendAvailableAt, later.add(const Duration(seconds: 60)));
    });

    test('router reply with resend_cooldown is followed', () async {
      h.on(
        'POST',
        '/auth/resend-otp',
        (_) => jsonResponse({
          'challenge_id': 'otp_chl_reg_new',
          'expires_in': 60,
          'resend_cooldown': 30,
        }),
      );
      final next = await h.auth(now: () => now).resendOtp(challenge);
      expect(next.resendAvailableAt, now.add(const Duration(seconds: 30)));
    });

    test('429 OTP_RESEND_COOLDOWN → available at', () async {
      h.on(
        'POST',
        '/auth/resend-otp',
        (_) => errorResponse(429, 'OTP_RESEND_COOLDOWN', {
          'available_at': '2026-11-04T12:00:42.000Z',
        }),
      );
      await expectLater(
        h.auth().resendOtp(challenge),
        throwsA(
          isA<OtpResendCooldownException>().having(
            (e) => e.availableAt,
            'availableAt',
            DateTime.utc(2026, 11, 4, 12, 0, 42).toLocal(),
          ),
        ),
      );
    });
  });

  test('§3.7 reset-password: body, no bearer', () async {
    h.on(
      'POST',
      '/auth/reset-password',
      (_) => jsonResponse({'status': 'success', 'message': 'ok'}),
    );
    await h.auth().setNewPassword(
      resetToken: 'rst_tok_v1_9921abcf',
      newPassword: 'matkhaumoi123',
    );
    expect(h.bodyOf(h.last), {
      'reset_token': 'rst_tok_v1_9921abcf',
      'new_password': 'matkhaumoi123',
    });
    expect(h.last.headers.containsKey('Authorization'), isFalse);
  });

  group('A1 restore (§4.1 GET /users/me)', () {
    void signedInBefore() {
      h.tokens.token = 'tok-1';
      h.store.user = contractUser;
    }

    test('nothing saved → null, no request', () async {
      expect(await h.auth().restoreSession(), isNull);
      expect(h.requests, isEmpty);
    });

    test(
      'saved user without a Firebase session → null, cache cleared',
      () async {
        h.store.user = contractUser;
        expect(await h.auth().restoreSession(), isNull);
        expect(h.store.user, isNull);
        expect(h.requests, isEmpty);
      },
    );

    test('Firebase session without a saved user → null, signed out', () async {
      h.tokens.token = 'tok-1';
      expect(await h.auth().restoreSession(), isNull);
      expect(h.tokens.isSignedIn, isFalse);
    });

    test('valid session → fresh user, cache updated, socket opened', () async {
      signedInBefore();
      final fresh = {...contractUser, 'full_name': 'Nguyễn Minh Anh B'};
      h.on('GET', '/users/me', (_) => jsonResponse(fresh));
      final user = await h.auth().restoreSession();
      expect(user?.fullName, 'Nguyễn Minh Anh B');
      expect(user?.phone, '0912345678');
      expect(h.last.headers['Authorization'], 'Bearer tok-1');
      expect(h.store.user, fresh);
      await pumpEventQueue();
      expect(h.channels, hasLength(1));
    });

    test('expired session (401 after a refresh) → null, all cleared', () async {
      signedInBefore();
      h.on('GET', '/users/me', (_) => errorResponse(401, 'TOKEN_EXPIRED'));
      var expired = 0;
      h.api.sessionExpired.listen((_) => expired++);
      expect(await h.auth().restoreSession(), isNull);
      expect(h.requests, hasLength(2));
      expect(h.store.user, isNull);
      expect(h.tokens.isSignedIn, isFalse);
      expect(expired, 1);
      await pumpEventQueue();
      expect(h.channels, isEmpty);
    });

    test('offline → the cached user', () async {
      signedInBefore();
      h.on('GET', '/users/me', (_) => throw http.ClientException('offline'));
      final user = await h.auth().restoreSession();
      expect(user?.id, 'usr_abc123');
      expect(h.store.user, contractUser);
    });

    test('slow server → the cached user once restoreWait passes', () async {
      signedInBefore();
      final reply = Completer<void>();
      h.on('GET', '/users/me', (_) async {
        await reply.future;
        return jsonResponse(contractUser);
      });
      final user = await h
          .auth(restoreWait: const Duration(milliseconds: 20))
          .restoreSession();
      expect(user?.id, 'usr_abc123');
      reply.complete();
      await pumpEventQueue();
    });
  });
}
