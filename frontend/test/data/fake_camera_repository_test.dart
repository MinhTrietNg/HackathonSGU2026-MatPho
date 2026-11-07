import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/errors.dart';
import '../fakes/fake_camera_repository.dart';
import '../fakes/fake_data.dart';
import '../fakes/fake_scenario.dart';
import '../fakes/fake_world.dart';
import 'package:mat_pho/data/models/models.dart';

FakeCameraRepository repo([Set<FakeCase> cases = const {}]) =>
    FakeCameraRepository(FakeWorld(FakeScenario.test(cases: cases)));

void main() {
  _getCameraTests();
  _memberStreamTests();

  test('Sky Garden cameras and areas (I7, I5)', () async {
    final r = repo();
    final cameras = await r.listCameras('g-sky');
    expect(cameras.map((c) => c.name), [
      'Khu sạc xe',
      'Lối lên dốc',
      'Lối xuống',
    ]);
    final lost = cameras.last;
    expect(lost.status, CameraStatus.signalLost);
    expect(lost.signalLostSince, DateTime(2025, 10, 23, 21, 30));
    expect((await r.listAreas('g-sky')).map((a) => a.name), [
      'Hầm B1',
      'Hầm B2',
      'Sảnh tầng 1',
    ]);
  });

  test('Nhà mình (I11) and member view of the office (I12)', () async {
    final r = repo();
    expect((await r.listCameras('g-home')).map((c) => c.name), [
      'Phòng khách',
      'Bếp',
      'Cửa trước',
    ]);
    expect((await r.listCameras('g-office')).map((c) => c.name), [
      'Kho hàng',
      'Cửa sau',
    ]);
  });

  test('connect + save with a new area (I2 → I9 → I5)', () async {
    final r = repo();
    final probe = await r.connect(FakeData.rtspExample);
    expect(probe.deviceName, 'Imou Ranger 2');
    final area = await r.createArea(
      groupId: 'g-sky',
      name: FakeData.newAreaExample,
    );
    final camera = await r.saveCamera(
      groupId: 'g-sky',
      rtspUrl: probe.rtspUrl,
      name: 'Khu sạc xe',
      areaId: area.id,
      watchArea: FakeData.chargerWatchArea,
    );
    expect((await r.listCameras('g-sky')).last, camera);
    expect((await r.listAreas('g-sky')).last.name, 'Bãi ô tô ngoài trời');
  });

  test('a member cannot add cameras (J13)', () async {
    await expectLater(
      repo().createArea(groupId: 'g-office', name: 'Kho 2'),
      throwsA(isA<PermissionDeniedException>()),
    );
  });

  test('connect errors (I4)', () async {
    final cases = {
      FakeCase.cameraNoResponse: isA<CameraNoResponseException>(),
      FakeCase.cameraAuthFailed: isA<CameraAuthFailedException>(),
      FakeCase.cameraNotOnCompanyWifi: isA<NotOnCompanyWifiException>(),
      FakeCase.cameraVendorBlocked: isA<VendorBlockedException>(),
    };
    for (final MapEntry(key: c, value: matcher) in cases.entries) {
      await expectLater(
        repo({c}).connect(FakeData.rtspExample),
        throwsA(
          allOf(
            matcher,
            isA<CameraConnectException>().having(
              (e) => e.cameraName,
              'cameraName',
              'Imou Ranger 2',
            ),
          ),
        ),
      );
    }
  });

  test('reconnect after signal lost (I8)', () async {
    final fixed = await repo().reconnect('cam-down');
    expect(fixed.status, CameraStatus.watching);
    expect(fixed.signalLostSince, isNull);
    await expectLater(
      repo({FakeCase.cameraReconnectFails}).reconnect('cam-down'),
      throwsA(isA<CameraNoResponseException>()),
    );
  });

  test('noCameras: every group is empty, areas stay', () async {
    final r = repo({FakeCase.noCameras});
    for (final id in ['g-sky', 'g-home', 'g-office', 'g-personal-u-minh-anh']) {
      expect(await r.listCameras(id), isEmpty);
    }
    expect(await r.listAreas('g-sky'), isNotEmpty);
    expect(await r.listAreas('g-personal-u-minh-anh'), isEmpty);
  });
}

void _getCameraTests() {
  test('getCamera finds a camera by id (E2 / I8)', () async {
    final r = repo();
    final camera = await r.getCamera('cam-down');
    expect(camera.groupId, 'g-sky');
    expect(camera.status, CameraStatus.signalLost);
    expect(() => r.getCamera('cam-none'), throwsStateError);
  });
}

void _memberStreamTests() {
  test('a member\'s cameras carry a stream link, others none', () async {
    final r = repo();
    final office = await r.listCameras('g-office');
    expect(office.every((c) => c.liveStreamUrl != null), isTrue);
    expect((await r.getCamera('cam-store')).liveStreamUrl, isNotNull);
    final sky = await r.listCameras('g-sky');
    expect(sky.every((c) => c.liveStreamUrl == null), isTrue);
  });
}
