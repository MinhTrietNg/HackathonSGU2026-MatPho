import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_icon_button.dart';
import 'package:mat_pho/core/widgets/mp_illustration.dart';
import 'package:mat_pho/core/widgets/mp_list_card.dart';
import 'package:mat_pho/core/widgets/mp_still.dart';
import 'package:mat_pho/data/providers.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_scenario.dart';
import '../../fakes/fake_world.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/features/cameras/camera_monitor_screen.dart';
import 'package:mat_pho/features/cameras/camera_routes.dart';

Future<GoRouter> _pumpCameras(
  WidgetTester tester, {
  Set<FakeCase> cases = const {},
  String initialLocation = AppRoutes.monitor,
  List<Override> overrides = const [],
  FakeScenario? scenario,
}) async {
  tester.view
    ..physicalSize = const Size(360, 780) * 2
    ..devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  final router = GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: initialLocation,
    routes: [
      GoRoute(
        path: AppRoutes.monitor,
        builder: (_, _) => const CameraMonitorScreen(),
        routes: [
          ...cameraSubRoutes,
          GoRoute(
            path: 'watch/:id',
            builder: (_, state) => Text('watch ${state.pathParameters['id']}'),
          ),
        ],
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(
          scenario ?? FakeScenario.test(cases: cases),
        ),
        ...overrides,
      ]),
      child: MaterialApp.router(
        theme: AppTheme.dark(),
        locale: const Locale('vi'),
        supportedLocales: const [Locale('vi')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        routerConfig: router,
      ),
    ),
  );
  await _settle(tester);
  return router;
}

Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 3; i++) {
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
  }
}

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await _settle(tester);
}

final _plus = find.byWidgetPredicate(
  (w) => w is MpIconButton && w.semanticLabel == 'Thêm camera',
);

Future<void> _connect(WidgetTester tester) async {
  await _tap(tester, find.bySemanticsLabel('Thêm camera'));
  expect(find.text('Thêm camera RTSP'), findsOneWidget);
  await tester.enterText(find.byType(TextField), FakeData.rtspExample);
  await _tap(tester, find.text('Kết nối'));
}

void main() {
  testWidgets('I7 shows cameras by area, then the "Thêm camera RTSP" card', (
    tester,
  ) async {
    await _pumpCameras(tester);
    expect(find.text('Chung cư Sky Garden'), findsOneWidget);
    expect(find.text('HẦM B1'), findsOneWidget);
    expect(find.text('2 camera'), findsOneWidget);
    expect(find.text('Khu sạc xe'), findsOneWidget);
    expect(find.text('Lối lên dốc'), findsOneWidget);
    expect(find.text('Đang theo dõi'), findsNWidgets(2));
    expect(find.text('HẦM B2'), findsOneWidget);
    expect(find.text('· 1 mất tín hiệu'), findsOneWidget);
    expect(find.text('Mất tín hiệu từ 21:30'), findsOneWidget);
    expect(find.text('VIDEO MÔ PHỎNG'), findsNothing);
    expect(find.text('Thêm camera RTSP'), findsOneWidget);
    expect(find.text('Dán đường dẫn RTSP · AI quét 24/7'), findsOneWidget);
    expect(find.text('Thành viên'), findsNothing);

    await _tap(tester, find.text('Dán đường dẫn RTSP · AI quét 24/7'));
    expect(find.text('Kết nối'), findsOneWidget);
    await _tap(tester, find.bySemanticsLabel('Quay lại'));
    expect(find.text('HẦM B1'), findsOneWidget);
  });

  testWidgets('a frame captured on E2 is the row thumbnail at once', (
    tester,
  ) async {
    await _pumpCameras(tester);
    expect(find.byType(MpStill), findsNothing);

    final png = base64Decode(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA'
      '60e6kgAAAABJRU5ErkJggg==',
    );
    ProviderScope.containerOf(
        tester.element(find.byType(CameraMonitorScreen)),
      ).read(cameraThumbnailsProvider.notifier)
      ..capture('cam-charger', png)
      ..capture('cam-down', png);
    await _settle(tester);

    final still = find.descendant(
      of: find.ancestor(
        of: find.text('Khu sạc xe'),
        matching: find.byType(MpListCard),
      ),
      matching: find.byType(MpStill),
    );
    expect(tester.widget<MpStill>(still).image, MemoryImage(png));
    expect(find.byType(MpStill), findsOneWidget);
    final lost = find.ancestor(
      of: find.text('Lối xuống'),
      matching: find.byType(MpListCard),
    );
    expect(
      find.descendant(
        of: lost,
        matching: find.byWidgetPredicate(
          (w) => w is MpIllustration && w.asset == MpIllustrations.camOffline,
        ),
      ),
      findsOneWidget,
    );
  });

  testWidgets('no camera anywhere: "Camera của tôi" with only the card', (
    tester,
  ) async {
    await _pumpCameras(tester, cases: {FakeCase.noCameras});
    expect(find.text('Camera của tôi'), findsOneWidget);
    expect(find.text('HẦM B1'), findsNothing);
    expect(find.text('Khu sạc xe'), findsNothing);
    expect(find.text('Thêm camera RTSP'), findsOneWidget);
  });

  testWidgets('a new account opens on its personal group, enterMonitor → I2', (
    tester,
  ) async {
    final router = await _pumpCameras(
      tester,
      overrides: [
        fakeWorldProvider.overrideWith((ref) {
          final world = FakeWorld(ref.watch(fakeScenarioProvider));
          ref.onDispose(world.dispose);
          world.startNewAccount(
            const User(id: 'u-new', fullName: 'Trần Văn Bình', phone: '0933'),
          );
          return world;
        }),
      ],
    );
    expect(find.text('Camera của tôi'), findsOneWidget);
    expect(find.text('Thêm camera RTSP'), findsOneWidget);

    final element = tester.element(find.byType(CameraMonitorScreen));
    await enterMonitor(element, element as WidgetRef);
    await _settle(tester);
    expect(router.state.uri.path, CameraRoutes.add);
    expect(find.text('Kết nối'), findsOneWidget);
  });

  testWidgets('the place picker switches the tab to another place', (
    tester,
  ) async {
    await _pumpCameras(tester);
    await _tap(tester, find.bySemanticsLabel('Chọn nơi: Chung cư Sky Garden'));
    expect(find.text('Chọn nơi'), findsOneWidget);
    expect(find.text('Camera của tôi'), findsOneWidget);
    expect(find.text('0 camera · Chủ sở hữu'), findsOneWidget);
    expect(find.text('3 camera · Chủ sở hữu'), findsNWidgets(2));
    expect(find.text('2 camera · Thành viên'), findsOneWidget);

    await _tap(tester, find.text('Nhà mình'));
    expect(find.text('Chọn nơi'), findsNothing);
    expect(find.text('TRONG NHÀ'), findsOneWidget);
    expect(find.text('3 camera'), findsOneWidget);
    for (final name in ['Phòng khách', 'Bếp', 'Cửa trước']) {
      expect(find.text(name), findsOneWidget);
    }
    expect(find.text('Khu sạc xe'), findsNothing);
  });

  testWidgets('while a picked place loads, the cameras of the last one are '
      'not shown under its name', (tester) async {
    await _pumpCameras(tester, scenario: const FakeScenario(freezeClock: true));
    expect(find.text('Khu sạc xe'), findsOneWidget);
    await _tap(tester, find.bySemanticsLabel('Chọn nơi: Chung cư Sky Garden'));

    await tester.tap(find.text('Nhà mình'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    Finder onMonitor(String text) => find.descendant(
      of: find.byType(CameraMonitorScreen),
      matching: find.text(text),
    );
    expect(onMonitor('Chung cư Sky Garden'), findsNothing);
    expect(onMonitor('Khu sạc xe'), findsNothing);
    expect(onMonitor('HẦM B1'), findsNothing);

    await _settle(tester);
    expect(onMonitor('Nhà mình'), findsOneWidget);
    expect(onMonitor('Phòng khách'), findsOneWidget);
    expect(onMonitor('Khu sạc xe'), findsNothing);
  });

  testWidgets('rows say when AI is paused by schedule or off, and flip at '
      'the end of the window', (tester) async {
    var now = DateTime(2025, 10, 23, 18);
    await _pumpCameras(
      tester,
      overrides: [
        clockProvider.overrideWithValue(() => now),
        fakeWorldProvider.overrideWith((ref) {
          final world = FakeWorld(ref.watch(fakeScenarioProvider));
          ref.onDispose(world.dispose);
          world.cameras = [
            for (final c in world.cameras)
              c.id == 'cam-front' ? c.copyWith(ai: CameraAi.off) : c,
          ];
          return world;
        }),
      ],
    );
    await _tap(tester, find.bySemanticsLabel('Chọn nơi: Chung cư Sky Garden'));
    await _tap(tester, find.text('Nhà mình'));
    String subtitleOf(String name) => tester
        .widget<MpListCard>(
          find.ancestor(of: find.text(name), matching: find.byType(MpListCard)),
        )
        .subtitle;
    expect(subtitleOf('Bếp'), 'Nghỉ AI theo lịch');
    expect(subtitleOf('Cửa trước'), 'AI đã tắt');
    expect(subtitleOf('Phòng khách'), 'AI đang quét');
    expect(find.text('Đang theo dõi'), findsNWidgets(3));

    now = DateTime(2025, 10, 23, 19, 30);
    await tester.pump(const Duration(seconds: 1));
    expect(subtitleOf('Bếp'), 'AI đang quét');
    expect(subtitleOf('Cửa trước'), 'AI đã tắt');
  });

  testWidgets('a member sees only assigned cameras and no "+"', (tester) async {
    await _pumpCameras(tester);
    await _tap(tester, find.bySemanticsLabel('Chọn nơi: Chung cư Sky Garden'));
    await _tap(tester, find.text('Văn phòng công ty'));
    expect(find.text('KHO TẦNG 1'), findsOneWidget);
    expect(find.text('2 camera được giao'), findsOneWidget);
    expect(find.text('Kho hàng'), findsOneWidget);
    expect(find.text('Cửa sau'), findsOneWidget);
    expect(find.text('Thành viên'), findsOneWidget);
    expect(_plus, findsNothing);
    expect(find.text('Thêm camera RTSP'), findsNothing);
  });

  testWidgets(
    'add camera: connect → name and area → saved → E2 over the list',
    (tester) async {
      final router = await _pumpCameras(tester);
      await _connect(tester);
      expect(find.text('Đặt tên camera'), findsOneWidget);
      expect(find.text('Vùng theo dõi'), findsNothing);

      await tester.enterText(find.byType(TextField), 'Cửa hầm');
      await tester.pump();
      await _tap(tester, find.text('+ Khu vực mới'));
      expect(find.text('Khu vực mới'), findsOneWidget);
      await tester.enterText(find.byType(TextField).last, 'Bãi ô tô');
      await _tap(tester, find.text('Tạo khu vực'));
      expect(find.text('Khu vực mới'), findsNothing);
      expect(
        tester.getSemantics(find.bySemanticsLabel('Bãi ô tô')),
        matchesSemantics(
          isButton: true,
          hasSelectedState: true,
          isSelected: true,
        ),
      );

      await _tap(tester, find.text('Lưu'));
      final matches = router.routerDelegate.currentConfiguration.matches;
      expect(matches.first.matchedLocation, AppRoutes.monitor);
      expect(matches.last.matchedLocation, startsWith('/monitor/watch/cam-'));
      expect(find.textContaining('watch cam-'), findsOneWidget);

      router.pop();
      await _settle(tester);
      expect(find.text('Cửa hầm'), findsOneWidget);
      expect(find.text('BÃI Ô TÔ'), findsOneWidget);
    },
  );

  for (final failure in [
    FakeCase.cameraNoResponse,
    FakeCase.cameraAuthFailed,
    FakeCase.cameraNotOnCompanyWifi,
    FakeCase.cameraVendorBlocked,
  ]) {
    testWidgets('a failed connection (${failure.name}) opens I4', (
      tester,
    ) async {
      await _pumpCameras(tester, cases: {failure});
      await _connect(tester);
      expect(find.text(FakeData.probedDeviceName), findsOneWidget);
      expect(find.text('Không kết nối được'), findsOneWidget);
      expect(find.text('Xem lại mật khẩu'), findsOneWidget);
      expect(find.text('Điện thoại phải dùng Wi-Fi công ty'), findsOneWidget);
      expect(find.text('Nhờ IT cấp quyền cho camera'), findsOneWidget);

      await _tap(tester, find.bySemanticsLabel('Quay lại'));
      expect(find.text('Thêm camera RTSP'), findsOneWidget);
      expect(
        tester.widget<TextField>(find.byType(TextField)).controller!.text,
        FakeData.rtspExample,
      );
    });
  }

  testWidgets('a camera row opens its watch screen (E2)', (tester) async {
    final router = await _pumpCameras(tester);
    await _tap(tester, find.text('Khu sạc xe'));
    expect(
      router.routerDelegate.currentConfiguration.last.matchedLocation,
      AppRoutes.watch('cam-charger'),
    );
    expect(find.text('watch cam-charger'), findsOneWidget);
  });

  testWidgets('a lost camera row opens I8', (tester) async {
    final router = await _pumpCameras(tester);
    await _tap(tester, find.text('Lối xuống'));
    expect(
      router.routerDelegate.currentConfiguration.last.matchedLocation,
      CameraRoutes.signalLost('cam-down'),
    );
    expect(find.text('Hầm B2 · Lối xuống'), findsOneWidget);
  });

  testWidgets('a lost camera shows I8; reconnecting opens its watch screen', (
    tester,
  ) async {
    final router = await _pumpCameras(
      tester,
      initialLocation: CameraRoutes.signalLost('cam-down'),
    );
    expect(find.text('Hầm B2 · Lối xuống'), findsOneWidget);
    expect(find.text('Mất tín hiệu từ 21:30'), findsOneWidget);
    expect(
      find.text('Khu này đang không được canh cháy. Đã báo Phạm Thị Lan.'),
      findsOneWidget,
    );
    await _tap(tester, find.text('Thử kết nối lại'));
    expect(find.text('Mất tín hiệu từ 21:30'), findsNothing);
    expect(
      router.routerDelegate.currentConfiguration.last.matchedLocation,
      AppRoutes.watch('cam-down'),
    );
    expect(find.text('watch cam-down'), findsOneWidget);
  });

  testWidgets('I8 stays when reconnecting still fails', (tester) async {
    await _pumpCameras(
      tester,
      cases: {FakeCase.cameraReconnectFails},
      initialLocation: CameraRoutes.signalLost('cam-down'),
    );
    await _tap(tester, find.text('Thử kết nối lại'));
    expect(find.text('Mất tín hiệu từ 21:30'), findsOneWidget);
    expect(find.textContaining('watch '), findsNothing);
    await _toastGone(tester);
  });

  _i8Tests();
  _deleteTests();
  _noRtspTests();
}

Override _skyRole(GroupRole role) => fakeWorldProvider.overrideWith((ref) {
  final world = FakeWorld(ref.watch(fakeScenarioProvider));
  ref.onDispose(world.dispose);
  final sky = world.group(FakeData.skyGarden.id);
  world.replaceGroup(
    Group(
      id: sky.id,
      name: sky.name,
      myRole: role,
      myNickname: sky.myNickname,
      cameraCount: sky.cameraCount,
      memberCount: sky.memberCount,
      address: sky.address,
    ),
  );
  return world;
});

FakeWorld _world(WidgetTester tester) => ProviderScope.containerOf(
  tester.element(find.byType(Navigator).first),
).read(fakeWorldProvider);

Future<void> _toastGone(WidgetTester tester) async {
  await tester.pump(const Duration(seconds: 5));
  await tester.pumpAndSettle();
}

const _stillDown = 'Vẫn chưa kết nối được';
const _readd = 'Thêm lại RTSP';

Future<GoRouter> _pumpLost(
  WidgetTester tester, {
  int failures = 2,
  Set<FakeCase> cases = const {},
  List<Override> overrides = const [],
}) async {
  final router = await _pumpCameras(
    tester,
    cases: {FakeCase.cameraReconnectFails, ...cases},
    initialLocation: CameraRoutes.signalLost('cam-down'),
    overrides: overrides,
  );
  for (var i = 0; i < failures; i++) {
    await _tap(tester, find.text('Thử kết nối lại'));
  }
  return router;
}

void _i8Tests() {
  testWidgets('I8 · a failed reconnect shows "$_stillDown"; the second one '
      'adds "$_readd"', (tester) async {
    await _pumpLost(tester, failures: 0);
    expect(find.text(_readd), findsNothing);

    await _tap(tester, find.text('Thử kết nối lại'));
    expect(find.text(_stillDown), findsOneWidget);
    expect(find.text('Mất tín hiệu từ 21:30'), findsOneWidget);
    expect(find.text(_readd), findsNothing);

    await _tap(tester, find.text('Thử kết nối lại'));
    expect(find.text(_stillDown), findsOneWidget);
    expect(find.text(_readd), findsOneWidget);
    await _toastGone(tester);
  });

  testWidgets('I8 · a manager gets "$_readd" too', (tester) async {
    await _pumpLost(tester, overrides: [_skyRole(GroupRole.manager)]);
    expect(find.text(_readd), findsOneWidget);
    await _toastGone(tester);
  });

  for (final role in [GroupRole.member, GroupRole.alertsOnly]) {
    testWidgets('I8 · ${role.name} never gets "$_readd"', (tester) async {
      await _pumpLost(tester, failures: 3, overrides: [_skyRole(role)]);
      expect(find.text(_stillDown), findsOneWidget);
      expect(find.text(_readd), findsNothing);
      await _toastGone(tester);
    });
  }

  testWidgets('I8 "$_readd": I2 empty → I5 with the camera\'s name and area '
      '→ "Lưu" gives the same camera the new link and opens its E2', (
    tester,
  ) async {
    final router = await _pumpLost(tester);
    await _toastGone(tester);
    final before = _world(tester).cameras.length;

    await _tap(tester, find.text(_readd));
    expect(find.text('Thêm camera RTSP'), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      isEmpty,
    );
    await tester.enterText(find.byType(TextField), FakeData.rtspExample);
    await _tap(tester, find.text('Kết nối'));

    expect(find.text('Đặt tên camera'), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      'Lối xuống',
    );
    expect(
      tester.getSemantics(find.bySemanticsLabel('Hầm B2')),
      matchesSemantics(
        isButton: true,
        hasSelectedState: true,
        isSelected: true,
      ),
    );

    await _tap(tester, find.text('Lưu'));
    final world = _world(tester);
    expect(world.cameras, hasLength(before));
    final same = world.cameras.firstWhere((c) => c.id == 'cam-down');
    expect(same.name, 'Lối xuống');
    expect(same.groupId, 'g-sky');
    expect(same.areaId, 'a-b2');
    expect(same.rtspUrl, FakeData.rtspExample);
    expect(same.status, CameraStatus.watching);
    final matches = router.routerDelegate.currentConfiguration.matches;
    expect(matches.first.matchedLocation, AppRoutes.monitor);
    expect(matches.last.matchedLocation, AppRoutes.watch('cam-down'));
    expect(find.text('watch cam-down'), findsOneWidget);

    router.pop();
    await _settle(tester);
    expect(find.text('Lối xuống'), findsOneWidget);
    expect(find.text('· 1 mất tín hiệu'), findsNothing);
    expect(find.text('Mất tín hiệu từ 21:30'), findsNothing);
  });

  testWidgets('I8 "$_readd": the server refuses the new link → a toast, '
      'still on I5, the camera unchanged', (tester) async {
    await _pumpLost(tester, cases: {FakeCase.cameraUpdateFails});
    await _toastGone(tester);
    final before = _world(tester).cameras.firstWhere((c) => c.id == 'cam-down');
    await _tap(tester, find.text(_readd));
    await tester.enterText(find.byType(TextField), FakeData.rtspExample);
    await _tap(tester, find.text('Kết nối'));
    await _tap(tester, find.text('Lưu'));

    expect(find.text('Máy chủ đang bận. Thử lại sau ít phút.'), findsOneWidget);
    expect(find.text('Đặt tên camera'), findsOneWidget);
    final after = _world(tester).cameras.firstWhere((c) => c.id == 'cam-down');
    expect(after.rtspUrl, before.rtspUrl);
    expect(after.status, CameraStatus.signalLost);
    await _toastGone(tester);
  });

  testWidgets('I8 "$_readd" then back from I2: back on I8, nothing changed', (
    tester,
  ) async {
    final router = await _pumpLost(tester);
    await _toastGone(tester);
    final before = [..._world(tester).cameras];

    await _tap(tester, find.text(_readd));
    expect(find.text('Thêm camera RTSP'), findsOneWidget);
    await _tap(tester, find.bySemanticsLabel('Quay lại'));
    expect(
      router.routerDelegate.currentConfiguration.last.matchedLocation,
      CameraRoutes.signalLost('cam-down'),
    );
    expect(find.text('Mất tín hiệu từ 21:30'), findsOneWidget);
    expect(find.text(_readd), findsOneWidget);
    expect(_world(tester).cameras, before);
  });
}

const _delete = 'Xoá camera';

void _deleteTests() {
  testWidgets('I8 · owners and managers get "$_delete"; members do not', (
    tester,
  ) async {
    await _pumpLost(tester, failures: 0);
    expect(find.bySemanticsLabel(_delete), findsOneWidget);
    await _toastGone(tester);
  });

  for (final role in [GroupRole.member, GroupRole.alertsOnly]) {
    testWidgets('I8 · ${role.name} never gets "$_delete"', (tester) async {
      await _pumpLost(tester, failures: 0, overrides: [_skyRole(role)]);
      expect(find.bySemanticsLabel(_delete), findsNothing);
      await _toastGone(tester);
    });
  }

  testWidgets('I8 "$_delete" → I17 → "Xoá": E1 with "Hoàn tác", which '
      'restores the camera', (tester) async {
    final router = await _pumpLost(tester, failures: 0);
    final world = _world(tester);
    final before = world.cameras.length;

    await _tap(tester, find.bySemanticsLabel(_delete));
    await _tap(tester, find.text(_delete));
    expect(find.text('Xoá camera Lối xuống?'), findsOneWidget);
    await _tap(tester, find.text('Huỷ'));
    expect(world.cameras.length, before);

    await _tap(tester, find.bySemanticsLabel(_delete));
    await _tap(tester, find.text(_delete));
    await _tap(tester, find.text('Xoá'));
    expect(router.state.uri.path, AppRoutes.monitor);
    expect(world.cameras.length, before - 1);
    expect(world.trash.single.camera.id, 'cam-down');
    expect(find.text('Đã xoá camera · Lối xuống'), findsOneWidget);

    await _tap(tester, find.text('Hoàn tác'));
    expect(world.trash, isEmpty);
    expect(world.cameras.length, before);
    await _toastGone(tester);
  });
}

const _noLink = 'Chưa có đường dẫn RTSP';

Override _noRtspDown({GroupRole? role}) => fakeWorldProvider.overrideWith((ref) {
  final world = FakeWorld(ref.watch(fakeScenarioProvider));
  ref.onDispose(world.dispose);
  if (role != null) {
    final sky = world.group(FakeData.skyGarden.id);
    world.replaceGroup(
      Group(
        id: sky.id,
        name: sky.name,
        myRole: role,
        myNickname: sky.myNickname,
        cameraCount: sky.cameraCount,
        memberCount: sky.memberCount,
        address: sky.address,
      ),
    );
  }
  final down = world.cameras.firstWhere((c) => c.id == 'cam-down');
  world.cameras[world.cameras.indexOf(down)] = down.copyWith(hasRtsp: false);
  return world;
});

void _noRtspTests() {
  testWidgets('I8 · without a link: no reconnect, "$_readd" for the owner', (
    tester,
  ) async {
    await _pumpLost(tester, failures: 0, overrides: [_noRtspDown()]);
    expect(find.text(_noLink), findsOneWidget);
    expect(find.text('Thử kết nối lại'), findsNothing);
    expect(find.text(_readd), findsOneWidget);
  });

  testWidgets('I8 · without a link: a member only reads the banner', (
    tester,
  ) async {
    await _pumpLost(
      tester,
      failures: 0,
      overrides: [_noRtspDown(role: GroupRole.member)],
    );
    expect(find.text(_noLink), findsOneWidget);
    expect(find.text('Thử kết nối lại'), findsNothing);
    expect(find.text(_readd), findsNothing);
  });

  testWidgets('I20 · without a link the sheet offers only "$_delete"', (
    tester,
  ) async {
    await _pumpLost(tester, failures: 0, overrides: [_noRtspDown()]);
    await _tap(tester, find.bySemanticsLabel(_delete));
    expect(find.text('Gỡ đường dẫn RTSP'), findsNothing);
    expect(find.text(_delete), findsOneWidget);
  });
}
