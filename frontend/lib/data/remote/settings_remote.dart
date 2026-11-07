library;

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../errors.dart';
import '../models/settings.dart';
import '../repositories/settings_repository.dart';
import '../services/push_inbox.dart';
import '../session/push_token_source.dart';
import 'auth_remote.dart';
import 'core/api_client.dart';
import 'core/json.dart';
import 'core/remote_providers.dart';

const testAlertNotReceived = 'TEST_ALERT_NOT_RECEIVED';

final class RemoteSettingsRepository implements SettingsRepository {
  RemoteSettingsRepository({
    required this._api,
    required this._session,
    required this._push,
    required this._testAlertPushes,
    this.testAlertTimeout = const Duration(seconds: 20),
  });

  final ApiClient _api;
  final RemoteSession _session;
  final PushTokenSource _push;
  final Stream<void> _testAlertPushes;

  final Duration testAlertTimeout;

  bool? _loudWhenSilent;

  @override
  Future<bool> loudWhenSilent() async {
    final json = asJsonMap(await _api.get('/users/me'));
    return _loudWhenSilent = readBoolOrNull(json, 'loud_when_silent') ?? true;
  }

  @override
  Future<void> setLoudWhenSilent(bool enabled) async {
    await _api.patch('/users/me/settings', body: {'loud_when_silent': enabled});
    _loudWhenSilent = enabled;
  }

  @override
  Future<TestAlertResult> sendTestAlert() async {
    final token = await _push.token();
    final received = Completer<void>();
    void notReceived() {
      if (!received.isCompleted) received.completeError(_notReceived());
    }

    final subscription = _testAlertPushes.listen((_) {
      if (!received.isCompleted) received.complete();
    }, onDone: notReceived);
    final timeout = Timer(testAlertTimeout, notReceived);
    received.future.ignore();
    final stopwatch = Stopwatch()..start();
    try {
      await _api.post('/settings/test-alert', body: {'fcm_token': ?token});
      await received.future;
      final receivedAfter = stopwatch.elapsed;
      return TestAlertResult(
        receivedAfter: receivedAfter,
        loudWhenSilent: _loudWhenSilent ?? await loudWhenSilent(),
      );
    } finally {
      timeout.cancel();
      unawaited(subscription.cancel());
    }
  }

  @override
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    await _api.post(
      '/auth/change-password',
      body: {'current_password': currentPassword, 'new_password': newPassword},
    );
  }

  @override
  Future<void> logout() async {
    final token = await _push.token();
    _loudWhenSilent = null;
    await _session.end(
      () => _api.post('/auth/logout', body: {'fcm_token': ?token}),
    );
  }

  static ServerException _notReceived() => const ServerException(
    code: testAlertNotReceived,
    message: 'No TEST_ALERT push before the timeout',
  );
}

final testAlertPushesProvider = Provider<Stream<void>>(
  (ref) => ref.watch(pushInboxProvider).testAlertPushes,
);

final remoteSettingsRepositoryProvider = Provider<SettingsRepository>(
  (ref) => RemoteSettingsRepository(
    api: ref.watch(apiClientProvider),
    session: ref.watch(remoteSessionProvider),
    push: ref.watch(pushTokenSourceProvider),
    testAlertPushes: ref.watch(testAlertPushesProvider),
  ),
);
