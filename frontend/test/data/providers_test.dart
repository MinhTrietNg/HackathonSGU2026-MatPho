import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/remote/alert_remote.dart';
import 'package:mat_pho/data/remote/auth_remote.dart';
import 'package:mat_pho/data/remote/camera_remote.dart';
import 'package:mat_pho/data/remote/detection_remote.dart';
import 'package:mat_pho/data/remote/group_remote.dart';
import 'package:mat_pho/data/remote/history_remote.dart';
import 'package:mat_pho/data/remote/settings_remote.dart';
import 'package:mat_pho/data/repositories/repositories.dart';
import 'package:mat_pho/data/services/local_notification_service.dart';
import 'package:mat_pho/data/services/phone_dialer.dart';

import '../fakes/fake_alert_repository.dart';
import '../fakes/fake_auth_repository.dart';
import '../fakes/fake_camera_repository.dart';
import '../fakes/fake_data.dart';
import '../fakes/fake_detection_repository.dart';
import '../fakes/fake_group_repository.dart';
import '../fakes/fake_history_repository.dart';
import '../fakes/fake_notification_service.dart';
import '../fakes/fake_overrides.dart';
import '../fakes/fake_phone_dialer.dart';
import '../fakes/fake_scenario.dart';
import '../fakes/fake_settings_repository.dart';

class _StubHistory implements HistoryRepository {
  @override
  Future<List<FireEvent>> list({HistoryFilter filter = HistoryFilter.all}) =>
      Future.value(const []);

  @override
  Future<FireEvent> detail(String eventId) => throw const ServerException();
}

const _camera = Camera(id: 'cam-1', name: 'Hầm B1', groupId: 'g-1');

void main() {
  test('every repository defaults to the backend', () {
    final c = ProviderContainer.test();
    expect(c.read(authRepositoryProvider), isA<RemoteAuthRepository>());
    expect(
      c.read(detectionRepositoryProvider),
      isA<RemoteDetectionRepository>(),
    );
    expect(c.read(alertRepositoryProvider), isA<RemoteAlertRepository>());
    expect(c.read(historyRepositoryProvider), isA<RemoteHistoryRepository>());
    expect(c.read(settingsRepositoryProvider), isA<RemoteSettingsRepository>());
    expect(c.read(cameraRepositoryProvider), isA<RemoteCameraRepository>());
    expect(c.read(groupRepositoryProvider), isA<RemoteGroupRepository>());
    expect(
      c.read(notificationServiceProvider),
      isA<LocalNotificationService>(),
    );
    expect(c.read(phoneDialerProvider), isA<SystemPhoneDialer>());
  });

  test('the live feed is the camera\'s stream, else the illustration', () {
    final c = ProviderContainer.test();
    expect(c.read(cameraFeedProvider(_camera)), isNull);
    const url = 'https://stream.example/cam-1/index.m3u8';
    final live = c.read(
      cameraFeedProvider(
        const Camera(
          id: 'cam-1',
          name: 'Hầm B1',
          groupId: 'g-1',
          liveStreamUrl: url,
        ),
      ),
    );
    expect(live, networkFeed(url));
    expect(c.read(cameraStillProvider('cam-1')), isNull);
  });

  test('fakeOverrides swaps in the fakes', () {
    final c = ProviderContainer.test(overrides: fakeOverrides());
    expect(c.read(authRepositoryProvider), isA<FakeAuthRepository>());
    expect(c.read(detectionRepositoryProvider), isA<FakeDetectionRepository>());
    expect(c.read(alertRepositoryProvider), isA<FakeAlertRepository>());
    expect(c.read(historyRepositoryProvider), isA<FakeHistoryRepository>());
    expect(c.read(settingsRepositoryProvider), isA<FakeSettingsRepository>());
    expect(c.read(cameraRepositoryProvider), isA<FakeCameraRepository>());
    expect(c.read(groupRepositoryProvider), isA<FakeGroupRepository>());
    expect(c.read(notificationServiceProvider), isA<FakeNotificationService>());
    expect(c.read(phoneDialerProvider), isA<FakePhoneDialer>());
    expect(
      c.read(
        cameraFeedProvider(
          const Camera(
            id: 'cam-1',
            name: 'Hầm B1',
            groupId: 'g-1',
            liveStreamUrl: 'https://stream.test/cam-1/index.m3u8',
          ),
        ),
      ),
      isNull,
    );
  });

  test('fakes share one world (detection lands in history)', () async {
    final c = ProviderContainer.test(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(const FakeScenario.test()),
      ]),
    );
    final cameras = await c
        .read(cameraRepositoryProvider)
        .listCameras(FakeData.skyGarden.id);
    final fire = cameras.firstWhere((cam) => cam.id == FakeData.fireCameraId);
    await c.read(detectionRepositoryProvider).start(fire).toList();
    final rows = await c.read(historyRepositoryProvider).list();
    expect(rows, hasLength(5));
  });

  test('scenario override forces an edge state', () async {
    final c = ProviderContainer.test(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(
          const FakeScenario.test(cases: {FakeCase.historyNetworkError}),
        ),
      ]),
    );
    await expectLater(
      c.read(historyRepositoryProvider).list(),
      throwsA(isA<NetworkException>()),
    );
  });

  test('a provider passed to fakeOverrides replaces its fake', () async {
    final stub = _StubHistory();
    final c = ProviderContainer.test(
      overrides: fakeOverrides([
        historyRepositoryProvider.overrideWithValue(stub),
      ]),
    );
    expect(c.read(historyRepositoryProvider), same(stub));
    expect(await c.read(historyRepositoryProvider).list(), isEmpty);
    expect(c.read(alertRepositoryProvider), isA<FakeAlertRepository>());
  });
}
