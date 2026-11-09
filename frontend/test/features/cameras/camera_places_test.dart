import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/features/cameras/camera_actions.dart';
import 'package:mat_pho/features/cameras/camera_state.dart';
import 'package:mat_pho/features/groups/current_group.dart';
import 'package:mat_pho/features/groups/group_state.dart';

void main() {
  final personalId = FakeData.personal.id;
  late ProviderContainer container;

  setUp(() {
    container = ProviderContainer.test(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(const FakeScenario.test()),
      ]),
    );
  });

  Future<List<String>> places() async => [
    for (final p in await container.read(cameraPlacesProvider.future))
      p.group.id,
  ];

  test('I13 lists "Camera của tôi" first', () async {
    container.listen(cameraPlacesProvider, (_, _) {});
    final list = await container.read(cameraPlacesProvider.future);
    expect(list.map((p) => groupDisplayName(p.group)), [
      'Camera của tôi',
      'Chung cư Sky Garden',
      'Nhà mình',
      'Văn phòng công ty',
    ]);
    expect(list.first.group.name, 'Cá Nhân');
    expect(list.first.cameraCount, 0);
  });

  test('default place: the first shared group with a camera', () async {
    expect((await container.read(currentPlaceProvider.future)).id, 'g-sky');
    expect(defaultGroup(FakeData.groups), FakeData.skyGarden);
    expect(
      defaultGroup([
        FakeData.home.copyWith(cameraCount: 0),
        FakeData.personal,
        FakeData.office,
      ]),
      FakeData.office,
    );
  });

  test('a dissolved group leaves the place picker', () async {
    container.listen(cameraPlacesProvider, (_, _) {});
    expect(await places(), [personalId, 'g-sky', 'g-home', 'g-office']);

    await container.read(groupActionsProvider).dissolveGroup('g-sky');
    expect(await places(), [personalId, 'g-home', 'g-office']);
    expect((await container.read(currentPlaceProvider.future)).id, 'g-home');
  });

  test('a chosen place that is dissolved falls back to the default', () async {
    container.listen(currentPlaceProvider, (_, _) {});
    container.read(currentGroupIdProvider.notifier).select('g-home');
    expect((await container.read(currentPlaceProvider.future)).id, 'g-home');
    await container.read(groupActionsProvider).dissolveGroup('g-home');
    expect((await container.read(currentPlaceProvider.future)).id, 'g-sky');
  });

  test('every shared group gone: the personal group remains', () async {
    container.listen(placeCamerasProvider, (_, _) {});
    final actions = container.read(groupActionsProvider);
    await actions.dissolveGroup('g-sky');
    await actions.dissolveGroup('g-home');
    await actions.leaveGroup('g-office');
    final place = await container.read(currentPlaceProvider.future);
    expect(place.id, personalId);
    expect(groupDisplayName(place), 'Camera của tôi');
    expect(await container.read(placeCamerasProvider.future), isEmpty);
    expect(await container.read(placeAreasProvider.future), isEmpty);
  });

  test('noCameras: the default is the personal group', () async {
    final empty = ProviderContainer.test(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(
          const FakeScenario.test(cases: {FakeCase.noCameras}),
        ),
      ]),
    );
    final place = await empty.read(currentPlaceProvider.future);
    expect(place.id, personalId);
    expect(place.isPersonal, isTrue);
  });

  test('a camera saved on I5 updates the J7 count', () async {
    container.listen(groupsProvider, (_, _) {});
    Future<int> skyCount() async => (await container.read(
      groupsProvider.future,
    )).firstWhere((g) => g.id == 'g-sky').cameraCount;
    expect(await skyCount(), 5);
    final flow = container.read(addCameraProvider.notifier)..start();
    await flow.connect('rtsp://10.0.0.9:554/stream1');
    flow.setName('Cổng sau');
    await flow.save(areaId: 'a-b1');
    expect(await skyCount(), 6);
  });

  test('a camera saved on I5 shows on the group screens (J1/J2/J4)', () async {
    container
      ..listen(groupCamerasProvider('g-sky'), (_, _) {})
      ..listen(cameraPlacesProvider, (_, _) {});
    Future<int> groupCameras() async =>
        (await container.read(groupCamerasProvider('g-sky').future)).length;
    final before = await groupCameras();

    final flow = container.read(addCameraProvider.notifier)..start();
    expect(await flow.connect('rtsp://10.0.0.9:554/stream1'), isNull);
    flow.setName('Cửa hầm');
    final areas = await container.read(placeAreasProvider.future);
    await flow.save(areaId: areas.first.id);

    expect(await groupCameras(), before + 1);
    final places = await container.read(cameraPlacesProvider.future);
    final sky = places.firstWhere((p) => p.group.id == 'g-sky');
    expect(sky.cameraCount, before + 1);
  });

  test('I8 "Thêm lại RTSP" sends the new link to the same camera, in its '
      'place, not the current one', () async {
    container
      ..listen(groupsProvider, (_, _) {})
      ..listen(groupCamerasProvider('g-sky'), (_, _) {});
    container.read(currentGroupIdProvider.notifier).select('g-home');
    final old = (await container.read(
      groupCamerasProvider('g-sky').future,
    )).firstWhere((c) => c.id == 'cam-down');

    final flow = container.read(addCameraProvider.notifier)..startReplace(old);
    expect(container.read(addCameraProvider).rtspUrl, isEmpty);
    expect(container.read(addCameraProvider).name, 'Lối xuống');
    expect(container.read(addCameraProvider).areaId, 'a-b2');
    expect((await container.read(addCameraPlaceProvider.future)).id, 'g-sky');
    expect(
      [for (final a in await container.read(placeAreasProvider.future)) a.id],
      ['a-b1', 'a-b2', 'a-lobby'],
    );

    expect(await flow.connect('rtsp://10.0.0.9:554/stream1'), isNull);
    final saved = await flow.save(areaId: 'a-b2');
    expect(saved.id, 'cam-down');
    expect(saved.groupId, 'g-sky');
    expect(saved.areaId, 'a-b2');
    expect(saved.name, 'Lối xuống');
    expect(saved.rtspUrl, 'rtsp://10.0.0.9:554/stream1');
    expect(saved.status, CameraStatus.watching);

    final cameras = await container.read(groupCamerasProvider('g-sky').future);
    expect(cameras.where((c) => c.id == 'cam-down'), hasLength(1));
    final sky = (await container.read(
      groupsProvider.future,
    )).firstWhere((g) => g.id == 'g-sky');
    expect(sky.cameraCount, 5);
    expect((await container.read(currentPlaceProvider.future)).id, 'g-sky');
  });

  List<String> listed() => [
    for (final s in container.read(placeCamerasProvider).value ?? const [])
      for (final c in s.cameras) c.id,
  ];

  test('a camera saved on I5 is in the E1 list once save returns, so E2 '
      'draws it at once', () async {
    container.listen(placeCamerasProvider, (_, _) {});
    await container.read(placeCamerasProvider.future);

    final flow = container.read(addCameraProvider.notifier)..start();
    await flow.connect('rtsp://10.0.0.9:554/stream1');
    flow.setName('Cổng sau');
    final camera = await flow.save(areaId: 'a-b1');

    expect(listed(), contains(camera.id));
  });

  // What E1 shows: the server's list with this phone's edits on top.
  List<String> shown() => [
    for (final s in container.read(shownPlaceCamerasProvider) ?? const [])
      for (final c in s.cameras) c.id,
  ];

  Future<Camera> loaded([String? id]) async {
    container.listen(shownPlaceCamerasProvider, (_, _) {});
    final cameras = [
      for (final s in await container.read(placeCamerasProvider.future))
        ...s.cameras,
    ];
    return id == null ? cameras.first : cameras.firstWhere((c) => c.id == id);
  }

  test('I17 · a deleted camera leaves E1 before the server is asked; undo '
      'brings it back before the restore is sent', () async {
    final camera = await loaded('cam-ramp');
    final world = container.read(fakeWorldProvider);
    final actions = container.read(cameraActionsProvider);

    final deleting = actions.delete(camera);
    expect(shown(), isNot(contains('cam-ramp')));
    expect(world.trash, isEmpty);
    await deleting;
    await container.read(placeCamerasProvider.future);
    expect(shown(), isNot(contains('cam-ramp')));
    expect(world.trash.single.camera.id, 'cam-ramp');

    final restoring = actions.restore('cam-ramp', camera: camera);
    expect(shown(), contains('cam-ramp'));
    expect(world.trash, hasLength(1));
    await restoring;
    await pumpEventQueue();
    expect(world.trash, isEmpty);
    expect(shown(), contains('cam-ramp'));
    expect(container.read(cameraListEditsProvider).shown, isEmpty);
  });

  test('I17 · undo tapped before the delete lands: restored after it, '
      'shown the whole time', () async {
    final camera = await loaded('cam-ramp');
    final world = container.read(fakeWorldProvider);
    final actions = container.read(cameraActionsProvider);

    final deleting = actions.delete(camera);
    final restoring = actions.restore('cam-ramp', camera: camera);
    expect(shown(), contains('cam-ramp'));
    await deleting;
    expect(shown(), contains('cam-ramp'));
    await restoring;
    await pumpEventQueue();
    expect(world.trash, isEmpty);
    expect(world.cameras.where((c) => c.id == 'cam-ramp'), hasLength(1));
    expect(shown(), contains('cam-ramp'));
  });

  test('I17 · a delete the server refuses puts the camera back', () async {
    container.read(currentGroupIdProvider.notifier).select('g-office');
    final camera = await loaded();
    final actions = container.read(cameraActionsProvider);

    final deleting = actions.delete(camera);
    expect(shown(), isNot(contains(camera.id)));
    await expectLater(deleting, throwsA(isA<MpException>()));
    expect(shown(), contains(camera.id));
    final edits = container.read(cameraListEditsProvider);
    expect(edits.hidden, isEmpty);
    expect(edits.shown, isEmpty);
  });

  test('a group left (J14) leaves the place picker too', () async {
    container.listen(cameraPlacesProvider, (_, _) {});
    await container.read(groupActionsProvider).leaveGroup('g-office');
    expect(await places(), [personalId, 'g-sky', 'g-home']);
  });
}
