import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_icon_button.dart';
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
        fakeScenarioProvider.overrideWithValue(FakeScenario.test(cases: cases)),
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
  });
}
