import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_icon_button.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/features/cameras/camera_routes.dart';
import 'package:mat_pho/features/detection/detection_routes.dart';

import '../../fakes/fake_data.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_scenario.dart';
import '../../fakes/fake_world.dart';

// Not the camera whose scripted fire would open F2 mid-test.
const _camera = 'cam-ramp';
const _name = 'Lối lên dốc';

Override _skyRole(GroupRole role) => fakeWorldProvider.overrideWith((ref) {
  final world = FakeWorld(ref.watch(fakeScenarioProvider));
  ref.onDispose(world.dispose);
  final sky = world.group('g-sky');
  world.replaceGroup(
    Group(
      id: sky.id,
      name: sky.name,
      myRole: role,
      myNickname: sky.myNickname,
      cameraCount: sky.cameraCount,
      memberCount: sky.memberCount,
    ),
  );
  return world;
});

late GoRouter _router;

Future<ProviderContainer> _open(
  WidgetTester tester, {
  List<Override> overrides = const [],
}) async {
  tester.view
    ..physicalSize = const Size(360, 780)
    ..devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  addTearDown(hideMpToast);
  _router = GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: AppRoutes.monitor,
    routes: [
      GoRoute(
        path: AppRoutes.monitor,
        builder: (_, _) => const Scaffold(body: Text('E1')),
        routes: [...detectionRoutes, ...cameraSubRoutes],
      ),
    ],
  );
  addTearDown(_router.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(const FakeScenario.test()),
        clockProvider.overrideWithValue(() => FakeData.demoNow),
        ...overrides,
      ]),
      child: MaterialApp.router(
        theme: AppTheme.dark(),
        routerConfig: _router,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(disableAnimations: true),
          child: child!,
        ),
      ),
    ),
  );
  unawaited(_router.push(AppRoutes.watch(_camera)));
  await _settle(tester);
  return ProviderScope.containerOf(tester.element(find.byType(Navigator).first));
}

// Four fake repository calls (camera, places, areas, members) rebuild I8.
Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
  }
}

Finder get _trashButton => find.byWidgetPredicate(
  (w) => w is MpIconButton && w.semanticLabel == 'Xoá camera',
);

void main() {
  testWidgets('E2 · the owner sees the trash button in the header', (
    tester,
  ) async {
    await _open(tester);
    expect(find.text('Hầm B1 · $_name'), findsOneWidget);
    expect(_trashButton, findsOneWidget);
  });

  for (final role in [GroupRole.member, GroupRole.alertsOnly]) {
    testWidgets('E2 · a ${role.name} has no trash button', (tester) async {
      await _open(tester, overrides: [_skyRole(role)]);
      expect(_trashButton, findsNothing);
    });
  }

  testWidgets('I20 · the trash button opens the sheet with both actions', (
    tester,
  ) async {
    await _open(tester);
    await tester.tap(_trashButton);
    await tester.pumpAndSettle();
    expect(find.text('Gỡ đường dẫn RTSP'), findsOneWidget);
    expect(find.text('Xoá camera'), findsOneWidget);
  });

  testWidgets('I20 → I21 "Gỡ RTSP": the camera stays, I8 says there is no '
      'link', (tester) async {
    final c = await _open(tester);
    final world = c.read(fakeWorldProvider);
    final before = world.cameras.length;

    await tester.tap(_trashButton);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Gỡ đường dẫn RTSP'));
    await tester.pumpAndSettle();
    expect(find.text('Gỡ đường dẫn RTSP của $_name?'), findsOneWidget);
    await tester.tap(find.text('Gỡ RTSP'));
    await _settle(tester);

    final camera = world.cameras.firstWhere((cam) => cam.id == _camera);
    expect(camera.hasRtsp, isFalse);
    expect(camera.status, CameraStatus.signalLost);
    expect(world.cameras.length, before);
    expect(_router.state.uri.path, AppRoutes.signalLost(_camera));
    expect(find.text('Chưa có đường dẫn RTSP'), findsOneWidget);
    expect(find.text('Thử kết nối lại'), findsNothing);
    expect(find.text('Thêm lại RTSP'), findsOneWidget);
    expect(find.text('Đã gỡ RTSP · $_name'), findsOneWidget);
    await tester.pump(const Duration(seconds: 5)); // the toast's timer
  });

  testWidgets('I17 · cancel keeps the camera', (tester) async {
    final c = await _open(tester);
    await tester.tap(_trashButton);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Xoá camera'));
    await tester.pumpAndSettle();
    expect(find.text('Xoá camera $_name?'), findsOneWidget);
    expect(find.textContaining('30 ngày'), findsOneWidget);

    await tester.tap(find.text('Huỷ'));
    await tester.pumpAndSettle();
    expect(c.read(fakeWorldProvider).trash, isEmpty);
    expect(_router.state.uri.path, AppRoutes.watch(_camera));
  });

  testWidgets('I17 "Xoá" → E1 with "Hoàn tác"; undo restores the camera', (
    tester,
  ) async {
    final c = await _open(tester);
    final world = c.read(fakeWorldProvider);
    final before = world.cameras.length;

    await tester.tap(_trashButton);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Xoá camera'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Xoá'));
    await _settle(tester);

    expect(_router.state.uri.path, AppRoutes.monitor);
    expect(world.cameras.length, before - 1);
    expect(world.trash.single.camera.id, _camera);
    expect(find.text('Đã xoá camera · $_name'), findsOneWidget);

    await tester.tap(find.text('Hoàn tác'));
    await _settle(tester);
    expect(world.trash, isEmpty);
    expect(world.cameras.length, before);
  });
}
