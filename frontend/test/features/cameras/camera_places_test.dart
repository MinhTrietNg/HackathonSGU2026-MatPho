import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_scenario.dart';
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

  test('a group left (J14) leaves the place picker too', () async {
    container.listen(cameraPlacesProvider, (_, _) {});
    await container.read(groupActionsProvider).leaveGroup('g-office');
    expect(await places(), [personalId, 'g-sky', 'g-home']);
  });
}
