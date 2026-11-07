import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/models/settings.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/repositories/settings_repository.dart';
import 'package:mat_pho/data/services/notification_service.dart';
import 'package:mat_pho/features/settings/settings_state.dart';

import '../../fakes/fake_notification_service.dart';
import '../../fakes/fake_scenario.dart';

/// Backend whose FCM test push never reaches the phone, as on iOS without APNs.
final class _NoPushSettings implements SettingsRepository {
  int sent = 0;

  @override
  Future<bool> loudWhenSilent() async => false;

  @override
  Future<void> setLoudWhenSilent(bool enabled) async {}

  @override
  Future<TestAlertResult> sendTestAlert() async {
    sent++;
    throw StateError('test push not received');
  }

  @override
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {}

  @override
  Future<void> logout() async {}
}

Future<AsyncValue<TestAlertResult>> _send(
  TargetPlatform platform,
  _NoPushSettings settings,
  FakeNotificationService notifications,
) async {
  debugDefaultTargetPlatformOverride = platform;
  addTearDown(() => debugDefaultTargetPlatformOverride = null);
  final container = ProviderContainer(
    overrides: [
      settingsRepositoryProvider.overrideWithValue(settings),
      notificationServiceProvider.overrideWithValue(notifications),
    ],
  );
  addTearDown(container.dispose);
  final done = Completer<AsyncValue<TestAlertResult>>();
  container.listen(testAlertProvider, (_, next) {
    if (!next.isLoading && !done.isCompleted) done.complete(next);
  });
  return done.future;
}

void main() {
  test('iOS shows the local test alert without waiting for FCM', () async {
    final settings = _NoPushSettings();
    final notifications = FakeNotificationService(const FakeScenario.test());

    final result = await _send(TargetPlatform.iOS, settings, notifications);

    expect(settings.sent, 0);
    expect(notifications.shown.single.title, testAlertTitle);
    expect(result.value?.loudWhenSilent, isFalse);
  });

  test('Android still waits for the FCM round trip', () async {
    final settings = _NoPushSettings();
    final notifications = FakeNotificationService(const FakeScenario.test());

    final result = await _send(TargetPlatform.android, settings, notifications);

    expect(settings.sent, 1);
    expect(notifications.shown, isEmpty);
    expect(result.hasError, isTrue);
  });
}
