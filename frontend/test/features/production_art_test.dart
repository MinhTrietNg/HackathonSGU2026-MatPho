import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_feed_placeholder.dart';
import 'package:mat_pho/core/widgets/mp_illustration.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/repositories/repositories.dart';
import 'package:mat_pho/features/alert/alert_routes.dart';
import 'package:mat_pho/features/cameras/camera_monitor_screen.dart';
import 'package:mat_pho/features/cameras/camera_routes.dart';
import 'package:mat_pho/features/detection/detection_routes.dart';

import '../fakes/fake_data.dart';
import '../fakes/fake_overrides.dart';
import '../fakes/fake_scenario.dart';
import '../fakes/fake_world.dart';

class _SilentDetection implements DetectionRepository {
  final _session = StreamController<DetectionState>();

  @override
  Stream<DetectionState> start(Camera camera) => _session.stream;

  @override
  Future<void> dismissSuspect() async {}

  @override
  Future<void> stop() => _session.close();
}

const _sceneArt = {
  MpIllustrations.feed,
  MpIllustrations.feedFire,
  MpIllustrations.feedSmoke,
};

final _drawnScene = find.byWidgetPredicate(
  (w) => w is MpIllustration && _sceneArt.contains(w.asset),
);

Future<void> _pump(
  WidgetTester tester, {
  required String initialLocation,
  List<Override> overrides = const [],
}) async {
  tester.view
    ..physicalSize = const Size(360, 780)
    ..devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final router = GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: initialLocation,
    routes: [
      ...alertRoutes,
      GoRoute(
        path: AppRoutes.monitor,
        builder: (_, _) => const CameraMonitorScreen(),
        routes: [...cameraSubRoutes, ...detectionRoutes],
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: fakeOverrides([
        demoSceneArtProvider.overrideWithValue(false),
        fakeScenarioProvider.overrideWithValue(const FakeScenario.test()),
        clockProvider.overrideWithValue(() => FakeData.demoNow),
        ...overrides,
      ]),
      child: MaterialApp.router(
        theme: AppTheme.dark(),
        locale: const Locale('vi'),
        supportedLocales: const [Locale('vi')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        routerConfig: router,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(disableAnimations: true),
          child: child!,
        ),
      ),
    ),
  );
  for (var i = 0; i < 3; i++) {
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
  }
}

void main() {
  testWidgets('watch without a stream: a placeholder, no drawn scene', (
    tester,
  ) async {
    await _pump(
      tester,
      initialLocation: AppRoutes.watch(FakeData.fireCameraId),
      overrides: [
        detectionRepositoryProvider.overrideWithValue(_SilentDetection()),
      ],
    );
    expect(find.byType(MpFeedPlaceholder), findsOneWidget);
    expect(find.text('Không có hình trực tiếp'), findsOneWidget);
    expect(_drawnScene, findsNothing);
  });

  testWidgets('alert without a still: "Chưa có ảnh", no drawn fire', (
    tester,
  ) async {
    final fire = FakeData.fireAlert(id: 'evt-live');
    final world = FakeWorld(const FakeScenario.test())..addEvent(fire);
    addTearDown(world.dispose);
    await _pump(
      tester,
      initialLocation: AppRoutes.alert(fire.id),
      overrides: [fakeWorldProvider.overrideWithValue(world)],
    );
    expect(find.text('Đã xác nhận cháy'), findsOneWidget);
    expect(find.text('Chưa có ảnh'), findsOneWidget);
    expect(_drawnScene, findsNothing);
  });

  testWidgets('monitor rows without a thumbnail: the placeholder', (
    tester,
  ) async {
    await _pump(tester, initialLocation: AppRoutes.monitor);
    expect(find.byType(MpFeedPlaceholder), findsWidgets);
    expect(_drawnScene, findsNothing);
  });
}
