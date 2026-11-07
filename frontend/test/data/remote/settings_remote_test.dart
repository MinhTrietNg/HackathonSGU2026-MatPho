import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/remote/settings_remote.dart';

import 'remote_harness.dart';

void main() {
  late RemoteHarness h;

  setUp(() {
    h = RemoteHarness(idToken: 'tok-1');
    h.store.user = contractUser;
  });
  tearDown(() => h.dispose());

  group('H1 · §4.1 / §4.2 loud when silent', () {
    test('read from GET /users/me with the bearer', () async {
      h.on(
        'GET',
        '/users/me',
        (_) => jsonResponse({...contractUser, 'loud_when_silent': false}),
      );
      expect(await h.settings().loudWhenSilent(), isFalse);
      expect(h.last.headers['Authorization'], 'Bearer tok-1');
    });

    test('saved with PATCH /users/me/settings', () async {
      h.on(
        'PATCH',
        '/users/me/settings',
        (_) => jsonResponse({'loud_when_silent': false}),
      );
      await h.settings().setLoudWhenSilent(false);
      expect(h.last.method, 'PATCH');
      expect(h.bodyOf(h.last), {'loud_when_silent': false});
      expect(h.last.headers['Authorization'], 'Bearer tok-1');
    });
  });

  group('H5 · §3.8 change-password', () {
    test('body with the bearer', () async {
      h.on(
        'POST',
        '/auth/change-password',
        (_) => jsonResponse({'status': 'success'}),
      );
      await h.settings().changePassword(
        currentPassword: 'passcu12',
        newPassword: 'passmoi12',
      );
      expect(h.bodyOf(h.last), {
        'current_password': 'passcu12',
        'new_password': 'passmoi12',
      });
      expect(h.last.headers['Authorization'], 'Bearer tok-1');
    });

    test('wrong current password → WrongPasswordException', () async {
      h.on(
        'POST',
        '/auth/change-password',
        (_) => errorResponse(422, 'WRONG_PASSWORD', {'attempts_left': 0}),
      );
      await expectLater(
        h.settings().changePassword(
          currentPassword: 'sai',
          newPassword: 'passmoi12',
        ),
        throwsA(isA<WrongPasswordException>()),
      );
    });
  });

  group('H4 · §10.1 test alert', () {
    void answerTestAlert([void Function()? whileSending]) =>
        h.on('POST', '/settings/test-alert', (_) {
          whileSending?.call();
          return jsonResponse({
            'sent_at': '2026-11-04T12:00:00.000Z',
            'status': 'dispatched',
          });
        });

    test('sends fcm_token and measures until the first push', () async {
      final pushes = StreamController<void>.broadcast();
      addTearDown(pushes.close);
      answerTestAlert();
      h.on('GET', '/users/me', (_) => jsonResponse(contractUser));
      final result = h.settings(testAlertPushes: pushes.stream).sendTestAlert();
      await Future<void>.delayed(const Duration(milliseconds: 30));
      pushes.add(null);
      final received = await result;
      expect(received.receivedAfter, greaterThan(Duration.zero));
      expect(received.loudWhenSilent, isTrue);
      final send = h.requests.firstWhere(
        (r) => r.url.path == '/api/v1/settings/test-alert',
      );
      expect(h.bodyOf(send), {'fcm_token': 'fcm_device_token_xyz'});
      expect(send.headers['Authorization'], 'Bearer tok-1');
      expect(pushes.hasListener, isFalse);
    });

    test('a push faster than the HTTP reply still counts', () async {
      final pushes = StreamController<void>.broadcast();
      addTearDown(pushes.close);
      answerTestAlert(() => pushes.add(null));
      h.on(
        'PATCH',
        '/users/me/settings',
        (_) => jsonResponse({'loud_when_silent': false}),
      );
      final settings = h.settings(testAlertPushes: pushes.stream);
      await settings.setLoudWhenSilent(false);
      final received = await settings.sendTestAlert();
      expect(received.loudWhenSilent, isFalse);
      expect(h.requests.map((r) => r.method), ['PATCH', 'POST']);
    });

    test('no push in time → ServerException, listener cancelled', () async {
      final pushes = StreamController<void>.broadcast();
      addTearDown(pushes.close);
      answerTestAlert();
      await expectLater(
        h
            .settings(
              testAlertPushes: pushes.stream,
              testAlertTimeout: const Duration(milliseconds: 30),
            )
            .sendTestAlert(),
        throwsA(
          isA<ServerException>().having(
            (e) => e.code,
            'code',
            testAlertNotReceived,
          ),
        ),
      );
      expect(pushes.hasListener, isFalse);
    });

    test('no push source wired (empty stream) → fails at once', () async {
      answerTestAlert();
      await expectLater(
        h.settings().sendTestAlert(),
        throwsA(isA<ServerException>()),
      );
    });

    test('a failed send is its own error', () async {
      h.on(
        'POST',
        '/settings/test-alert',
        (_) => throw http.ClientException('offline'),
      );
      final pushes = StreamController<void>.broadcast();
      addTearDown(pushes.close);
      await expectLater(
        h.settings(testAlertPushes: pushes.stream).sendTestAlert(),
        throwsA(isA<NetworkException>()),
      );
      expect(pushes.hasListener, isFalse);
    });
  });

  group('H6 · §3.9 logout', () {
    test('cache and socket go first, then the server is told with the '
        'bearer and fcm_token, then Firebase signs out', () async {
      h.ws.connect();
      await pumpEventQueue();
      h.channels.single.accept();
      await pumpEventQueue();
      Map<String, Object?>? cacheDuringCall = {};
      h.on('POST', '/auth/logout', (_) {
        cacheDuringCall = h.store.user;
        return jsonResponse({'status': 'success'});
      });

      await h.settings().logout();

      expect(cacheDuringCall, isNull);
      expect(h.bodyOf(h.last), {'fcm_token': 'fcm_device_token_xyz'});
      expect(h.last.headers['Authorization'], 'Bearer tok-1');
      expect(h.channels.single.closedByClient, isTrue);
      expect(h.tokens.isSignedIn, isFalse);
    });

    test('a failing server still clears this phone', () async {
      h.on('POST', '/auth/logout', (_) => throw http.ClientException('x'));
      await expectLater(
        h.settings().logout(),
        throwsA(isA<NetworkException>()),
      );
      expect(h.store.user, isNull);
      expect(h.tokens.isSignedIn, isFalse);
    });
  });
}
