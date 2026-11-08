import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/settings/settings_routes.dart';

import '../../fakes/fake_data.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_scenario.dart';
import '../../fakes/fake_world.dart';

class _SignedIn extends AuthSessionNotifier {
  @override
  AuthSession build() => const SignedIn(FakeData.user);
}

/// A world where "Lối lên dốc" (g-sky) was deleted a week ago.
Override _trashedWorld({GroupRole? skyRole}) =>
    fakeWorldProvider.overrideWith((ref) {
      final world = FakeWorld(ref.watch(fakeScenarioProvider));
      ref.onDispose(world.dispose);
      if (skyRole != null) {
        final sky = world.group('g-sky');
        world.replaceGroup(
          Group(
            id: sky.id,
            name: sky.name,
            myRole: skyRole,
            myNickname: sky.myNickname,
            cameraCount: sky.cameraCount,
            memberCount: sky.memberCount,
          ),
        );
      }
      final camera = world.cameras.firstWhere((c) => c.id == 'cam-ramp');
      world.cameras.remove(camera);
      final deletedAt = world.now().subtract(const Duration(days: 7));
      world.trash.add((
        entry: TrashedCamera(
          id: camera.id,
          groupId: camera.groupId,
          name: camera.name,
          areaId: camera.areaId,
          areaName: 'Hầm B1',
          deletedAt: deletedAt,
          purgeAt: deletedAt.add(FakeWorld.trashRetention),
        ),
        camera: camera,
      ));
      return world;
    });

Future<ProviderContainer> _pump(
  WidgetTester tester, {
  List<Override> overrides = const [],
}) async {
  tester.view
    ..physicalSize = const Size(360, 780) * 2
    ..devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  addTearDown(hideMpToast);
  final container = ProviderContainer(
    overrides: fakeOverrides([
      fakeScenarioProvider.overrideWithValue(const FakeScenario.test()),
      authSessionProvider.overrideWith(_SignedIn.new),
      ...overrides,
    ]),
  );
  addTearDown(container.dispose);
  final router = GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: SettingsRoutes.cameraTrash,
    routes: [
      GoRoute(
        path: AppRoutes.settings,
        builder: (_, _) => const Scaffold(body: Text('settings')),
        routes: settingsSubRoutes,
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: MaterialApp.router(theme: AppTheme.dark(), routerConfig: router),
    ),
  );
  await _settle(tester);
  return container;
}

Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 3; i++) {
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
  }
}

FakeWorld _world(ProviderContainer c) => c.read(fakeWorldProvider);

void main() {
  testWidgets('I18 · empty when nothing was deleted', (tester) async {
    await _pump(tester);
    expect(find.text('Chưa xoá camera nào'), findsOneWidget);
    expect(find.text('Khôi phục'), findsNothing);
  });

  testWidgets('I18 · lists the deleted camera with its place, area and days '
      'left', (tester) async {
    await _pump(tester, overrides: [_trashedWorld()]);
    expect(find.text('Chung cư Sky Garden'), findsOneWidget);
    expect(find.text('Lối lên dốc'), findsOneWidget);
    expect(find.text('Hầm B1 · còn 23 ngày'), findsOneWidget);
    expect(find.text('Khôi phục'), findsOneWidget);
    expect(find.text('Xoá hẳn'), findsOneWidget);
  });

  testWidgets('I18 · "Khôi phục" brings the camera back', (tester) async {
    final c = await _pump(tester, overrides: [_trashedWorld()]);
    await tester.tap(find.text('Khôi phục'));
    await _settle(tester);
    expect(_world(c).trash, isEmpty);
    expect(_world(c).cameras.any((cam) => cam.id == 'cam-ramp'), isTrue);
    expect(find.text('Chưa xoá camera nào'), findsOneWidget);
  });

  testWidgets('I18 · a manager cannot "Xoá hẳn"', (tester) async {
    await _pump(
      tester,
      overrides: [_trashedWorld(skyRole: GroupRole.manager)],
    );
    expect(find.text('Khôi phục'), findsOneWidget);
    expect(find.text('Xoá hẳn'), findsNothing);
  });

  testWidgets('I19 · the owner confirms "Xoá hẳn", then it is gone for good', (
    tester,
  ) async {
    final c = await _pump(tester, overrides: [_trashedWorld()]);
    await tester.tap(find.text('Xoá hẳn'));
    await tester.pumpAndSettle();
    expect(find.text('Xoá hẳn camera Lối lên dốc?'), findsOneWidget);

    await tester.tap(find.text('Huỷ'));
    await tester.pumpAndSettle();
    expect(_world(c).trash, hasLength(1));

    await tester.tap(find.text('Xoá hẳn'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Xoá hẳn').last);
    await _settle(tester);
    expect(_world(c).trash, isEmpty);
    expect(_world(c).cameras.any((cam) => cam.id == 'cam-ramp'), isFalse);
    expect(find.text('Chưa xoá camera nào'), findsOneWidget);
  });
}
