import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/remote/core/api_errors.dart';

String body(String code, [Map<String, Object?> details = const {}]) =>
    jsonEncode({
      'error': {'code': code, 'message': 'server text', 'details': details},
    });

void main() {
  group('decodeApiError: contract codes', () {
    test('WRONG_PASSWORD carries attempts_left (contract §3.1)', () {
      final e = decodeApiError(
        422,
        body('WRONG_PASSWORD', {'attempts_left': 3}),
      );
      expect(e, isA<WrongPasswordException>());
      expect((e as WrongPasswordException).attemptsLeft, 3);
    });

    test('WRONG_PASSWORD without details has no counter (H5)', () {
      final e = decodeApiError(422, body('WRONG_PASSWORD'));
      expect((e as WrongPasswordException).attemptsLeft, isNull);
    });

    test('ACCOUNT_LOCKED carries locked_until as local time', () {
      final e = decodeApiError(
        423,
        body('ACCOUNT_LOCKED', {'locked_until': '2026-11-04T12:15:00.000Z'}),
      );
      final until = (e as AccountLockedException).until;
      expect(until.isUtc, isFalse);
      expect(until.toUtc(), DateTime.utc(2026, 11, 4, 12, 15));
    });

    test('ACCOUNT_LOCKED with the backend isoformat (+00:00, micros)', () {
      final e = decodeApiError(
        423,
        body('ACCOUNT_LOCKED', {
          'locked_until': '2026-11-04T12:15:00.123456+00:00',
        }),
      );
      expect(
        (e as AccountLockedException).until.toUtc(),
        DateTime.utc(2026, 11, 4, 12, 15, 0, 123, 456),
      );
    });

    test('phone and group conflicts', () {
      expect(
        decodeApiError(409, body('PHONE_ALREADY_REGISTERED')),
        isA<PhoneAlreadyRegisteredException>(),
      );
      expect(
        decodeApiError(404, body('PHONE_NOT_REGISTERED')),
        isA<PhoneNotRegisteredException>(),
      );
      expect(
        decodeApiError(409, body('ALREADY_IN_GROUP')),
        isA<AlreadyInGroupException>(),
      );
    });

    test('OTP_WRONG carries attempts_left', () {
      final e = decodeApiError(422, body('OTP_WRONG', {'attempts_left': 2}));
      expect((e as OtpWrongException).attemptsLeft, 2);
    });

    test('OTP_EXPIRED', () {
      expect(
        decodeApiError(410, body('OTP_EXPIRED')),
        isA<OtpExpiredException>(),
      );
    });

    test('OTP_LOCKED carries retry_at', () {
      final e = decodeApiError(
        429,
        body('OTP_LOCKED', {'retry_at': '2026-11-04T12:05:00.000Z'}),
      );
      expect(
        (e as OtpLockedException).retryAt.toUtc(),
        DateTime.utc(2026, 11, 4, 12, 5),
      );
    });

    test('OTP_RESEND_COOLDOWN carries available_at', () {
      final e = decodeApiError(
        429,
        body('OTP_RESEND_COOLDOWN', {
          'available_at': '2026-11-04T12:01:00.000Z',
        }),
      );
      expect(
        (e as OtpResendCooldownException).availableAt.toUtc(),
        DateTime.utc(2026, 11, 4, 12, 1),
      );
    });

    test('the four I4 camera errors take details.device_name (§8.1)', () {
      const details = {'device_name': 'Hikvision', 'host': '192.168.1.100'};
      final cases = {
        'CAMERA_NO_RESPONSE': isA<CameraNoResponseException>(),
        'CAMERA_AUTH_FAILED': isA<CameraAuthFailedException>(),
        'CAMERA_NOT_REACHABLE': isA<NotOnCompanyWifiException>(),
        'CAMERA_VENDOR_BLOCKED': isA<VendorBlockedException>(),
      };
      for (final MapEntry(key: code, value: matcher) in cases.entries) {
        final e = decodeApiError(400, body(code, details));
        expect(e, matcher, reason: code);
        expect((e as CameraConnectException).cameraName, 'Hikvision');
      }
    });

    test('camera name falls back to details.host, then empty', () {
      final byHost = decodeApiError(
        400,
        body('CAMERA_VENDOR_BLOCKED', {'host': '192.168.1.100'}),
      );
      expect((byHost as VendorBlockedException).cameraName, '192.168.1.100');
      final none = decodeApiError(400, body('CAMERA_NO_RESPONSE'));
      expect((none as CameraNoResponseException).cameraName, '');
    });

    test('PERMISSION_DENIED and INVITATION_UNAVAILABLE', () {
      expect(
        decodeApiError(403, body('PERMISSION_DENIED')),
        isA<PermissionDeniedException>(),
      );
      expect(
        decodeApiError(410, body('INVITATION_UNAVAILABLE')),
        isA<InvitationUnavailableException>(),
      );
    });
  });

  group('decodeApiError: fallbacks', () {
    test('unknown code → ServerException with the code', () {
      final e = decodeApiError(404, body('NOT_FOUND'));
      expect(e, isA<ServerException>());
      expect((e as ServerException).code, 'NOT_FOUND');
    });

    test('unknown code on 403 → PermissionDeniedException', () {
      expect(
        decodeApiError(403, body('FORBIDDEN')),
        isA<PermissionDeniedException>(),
      );
    });

    test('backend validation error (wrapped 422)', () {
      final e = decodeApiError(
        422,
        body('VALIDATION_ERROR', {
          'errors': [
            {
              'loc': ['body', 'phone_number'],
              'msg': 'Field required',
            },
          ],
        }),
      );
      expect((e as ServerException).code, 'VALIDATION_ERROR');
    });

    test("FastAPI's bare {detail: [...]} → VALIDATION_ERROR", () {
      final e = decodeApiError(
        422,
        jsonEncode({
          'detail': [
            {
              'loc': ['body'],
              'msg': 'x',
            },
          ],
        }),
      );
      expect((e as ServerException).code, 'VALIDATION_ERROR');
    });

    test('known code with malformed details → ServerException', () {
      final e = decodeApiError(422, body('OTP_WRONG', {'attempts_left': 'x'}));
      expect(e, isA<ServerException>());
      expect((e as ServerException).code, 'OTP_WRONG');
      final missing = decodeApiError(423, body('ACCOUNT_LOCKED'));
      expect(missing, isA<ServerException>());
    });

    test('non-JSON body (tunnel error page) → ServerException', () {
      final e = decodeApiError(502, '<html>Bad gateway</html>');
      expect(e, isA<ServerException>());
      expect((e as ServerException).code, isNull);
    });
  });
}
