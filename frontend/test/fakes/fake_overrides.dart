library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/remote/core/api_client.dart';
import 'package:mat_pho/data/remote/core/remote_providers.dart';

import 'fake_alert_repository.dart';
import 'fake_auth_repository.dart';
import 'fake_camera_repository.dart';
import 'fake_detection_repository.dart';
import 'fake_group_repository.dart';
import 'fake_history_repository.dart';
import 'fake_notification_service.dart';
import 'fake_phone_dialer.dart';
import 'fake_scenario.dart';
import 'fake_settings_repository.dart';
import 'fake_world.dart';
import 'remote_doubles.dart';

final fakeScenarioProvider = Provider<FakeScenario>(
  (ref) => const FakeScenario(),
);

final fakeWorldProvider = Provider<FakeWorld>((ref) {
  final world = FakeWorld(ref.watch(fakeScenarioProvider));
  ref.onDispose(world.dispose);
  return world;
});

List<Override> fakeOverrides([List<Override> overrides = const []]) {
  final replaced = {for (final o in overrides) o.origin};
  return [
    for (final o in _fakes)
      if (!replaced.contains(o.origin)) o,
    ...overrides,
  ];
}

final List<Override> _fakes = [
  clockProvider.overrideWith((ref) => ref.watch(fakeWorldProvider).now),
  demoSceneArtProvider.overrideWithValue(true),
  authRepositoryProvider.overrideWith(
    (ref) => FakeAuthRepository(ref.watch(fakeWorldProvider)),
  ),
  detectionRepositoryProvider.overrideWith((ref) {
    final repository = FakeDetectionRepository(ref.watch(fakeWorldProvider));
    ref.onDispose(repository.stop);
    return repository;
  }),
  alertRepositoryProvider.overrideWith(
    (ref) => FakeAlertRepository(ref.watch(fakeWorldProvider)),
  ),
  historyRepositoryProvider.overrideWith(
    (ref) => FakeHistoryRepository(ref.watch(fakeWorldProvider)),
  ),
  settingsRepositoryProvider.overrideWith(
    (ref) => FakeSettingsRepository(ref.watch(fakeWorldProvider)),
  ),
  cameraRepositoryProvider.overrideWith(
    (ref) => FakeCameraRepository(ref.watch(fakeWorldProvider)),
  ),
  groupRepositoryProvider.overrideWith(
    (ref) => FakeGroupRepository(ref.watch(fakeWorldProvider)),
  ),
  notificationServiceProvider.overrideWith((ref) {
    final service = FakeNotificationService(ref.watch(fakeScenarioProvider));
    ref.onDispose(service.dispose);
    return service;
  }),
  phoneDialerProvider.overrideWith((ref) => FakePhoneDialer()),
  cameraFeedProvider.overrideWith((ref, camera) => null),
  apiConfigProvider.overrideWithValue(testApiConfig),
  authTokenSourceProvider.overrideWith((ref) => FakeAuthTokenSource()),
  sessionStoreProvider.overrideWith((ref) => MemorySessionStore()),
  apiClientProvider.overrideWith((ref) {
    final client = ApiClient(
      config: testApiConfig,
      tokens: ref.watch(authTokenSourceProvider),
      httpClient: MockClient(
        (request) async =>
            http.Response('{"detail":"no network in tests"}', 503),
      ),
    );
    ref.onDispose(client.close);
    return client;
  }),
];
