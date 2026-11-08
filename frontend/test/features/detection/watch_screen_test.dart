import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_phone_dialer.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/repositories/repositories.dart';
import 'package:mat_pho/features/cameras/camera_state.dart';
import 'package:mat_pho/features/detection/detection_routes.dart';
import 'package:mat_pho/features/detection/watch_full_screen.dart';
import 'package:mat_pho/features/groups/current_group.dart';

class ScriptedDetectionRepository implements DetectionRepository {
  StreamController<DetectionState>? _session;
  final started = <Camera>[];
  int stops = 0;
  int skips = 0;

  @override
  Stream<DetectionState> start(Camera camera) {
    _session?.close();
    started.add(camera);
    final session = StreamController<DetectionState>();
    _session = session;
    return session.stream;
  }

  @override
  Future<void> dismissSuspect() async {
    skips++;
    emit(const DetectionWatching());
  }

  @override
  Future<void> stop() async {
    stops++;
    final session = _session;
    _session = null;
    await session?.close();
  }

  void emit(DetectionState state) => _session!.add(state);
}

final _suspect = SuspectFrame(
  sign: DetectedSign.smoke,
  confidence: 0.61,
  detectedAt: DateTime(2025, 10, 23, 21, 47, 31),
);

const _detected = TimelineStep(TimelineStepKind.detected, Duration.zero);
const _imageSent = TimelineStep(
  TimelineStepKind.imageSent,
  FakeData.imageSentAfter,
);
const _confirmed = TimelineStep(
  TimelineStepKind.confirmedFire,
  FakeData.fireConfirmedAfter,
);

const _fire = FakeData.fireCameraId;
const _skip = 'Không phải cháy? Bỏ qua';

void main() {
  late GoRouter router;

  Future<void> open(
    WidgetTester tester,
    String cameraId, {
    DetectionRepository? repository,
    DateTime Function()? clock,
    List<Override> overrides = const [],
    FakeScenario scenario = const FakeScenario.test(),
  }) async {
    tester.view
      ..physicalSize = const Size(360, 780)
      ..devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    router = GoRouter(
      navigatorKey: rootNavigatorKey,
      initialLocation: AppRoutes.monitor,
      routes: [
        GoRoute(
          path: AppRoutes.monitor,
          builder: (_, _) => const Scaffold(body: Text('I7')),
          routes: [
            ...detectionRoutes,
            GoRoute(
              path: 'cameras/:id',
              builder: (_, state) =>
                  Scaffold(body: Text('I8 ${state.pathParameters['id']}')),
            ),
          ],
        ),
        GoRoute(
          path: '/alert/:id',
          builder: (_, state) =>
              Scaffold(body: Text('alert ${state.pathParameters['id']}')),
        ),
        GoRoute(
          path: '/history/:id',
          builder: (_, state) =>
              Scaffold(body: Text('history ${state.pathParameters['id']}')),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: fakeOverrides([
          fakeScenarioProvider.overrideWithValue(scenario),
          if (repository != null)
            detectionRepositoryProvider.overrideWithValue(repository),
          clockProvider.overrideWithValue(clock ?? () => FakeData.demoNow),
          ...overrides,
        ]),
        child: MaterialApp.router(
          theme: AppTheme.dark(),
          routerConfig: router,
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context).copyWith(disableAnimations: true),
            child: child!,
          ),
        ),
      ),
    );
    unawaited(router.push(AppRoutes.watch(cameraId)));
    await tester.pumpAndSettle();
  }

  String location() => router.state.uri.path;

  testWidgets('opening a camera starts watching it right away (E2)', (
    tester,
  ) async {
    final repo = ScriptedDetectionRepository();
    await open(tester, _fire, repository: repo);
    expect(repo.started.single.id, _fire);
    expect(find.text('Hầm B1 · Khu sạc xe'), findsOneWidget);

    repo.emit(const DetectionWatching());
    await tester.pumpAndSettle();
    expect(find.text('AI đang quét'), findsOneWidget);
    expect(find.textContaining('khung/giây'), findsNothing);
    expect(find.text('HẦM B1 · 23/10/2025 21:47:43'), findsOneWidget);
    expect(find.text('Toàn màn hình'), findsOneWidget);
    expect(find.text('Dừng theo dõi'), findsNothing);
  });

  testWidgets('inside its pause window the camera says AI is resting, until '
      'the window ends', (tester) async {
    var now = DateTime(2025, 10, 23, 18);
    final repo = ScriptedDetectionRepository();
    await open(tester, 'cam-kitchen', repository: repo, clock: () => now);
    repo.emit(const DetectionWatching());
    await tester.pumpAndSettle();
    expect(find.text('Nghỉ AI theo lịch'), findsOneWidget);
    expect(find.text('AI đang quét'), findsNothing);
    expect(find.textContaining('khung/giây'), findsNothing);

    now = DateTime(2025, 10, 23, 19, 30);
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Nghỉ AI theo lịch'), findsNothing);
    expect(find.text('AI đang quét'), findsOneWidget);
    expect(find.textContaining('khung/giây'), findsNothing);
  });

  testWidgets('the timeline grows E2a → E2d, then F2 opens', (tester) async {
    final repo = ScriptedDetectionRepository();
    await open(tester, _fire, repository: repo);

    repo.emit(DetectionVerifying(suspect: _suspect, steps: const [_detected]));
    await tester.pumpAndSettle();
    expect(find.text('Máy phát hiện khói'), findsOneWidget);
    expect(find.text('0,0 s'), findsOneWidget);
    expect(
      find.text('Vùng mờ xám bốc lên qua 3 khung liên tiếp.'),
      findsOneWidget,
    );
    expect(find.text(_skip), findsOneWidget);

    repo.emit(
      DetectionVerifying(
        suspect: _suspect,
        steps: const [_detected, _imageSent],
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Gửi ảnh'), findsOneWidget);
    expect(find.text('+0,4 s'), findsOneWidget);
    expect(find.text('Gửi khung hình cho AI soi kỹ hơn.'), findsOneWidget);
    expect(find.text(_skip), findsOneWidget);

    repo.emit(
      DetectionVerifying(
        suspect: _suspect,
        steps: const [_detected, _imageSent, _confirmed],
        verdict: SuspectFrame(
          sign: DetectedSign.fire,
          confidence: 0.93,
          detectedAt: _suspect.detectedAt,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Xác nhận cháy'), findsOneWidget);
    expect(find.text('+5,1 s'), findsOneWidget);
    expect(
      find.text('Thấy lửa cam dưới xe máy, độ tin cậy 93%.'),
      findsOneWidget,
    );
    expect(find.text(_skip), findsNothing);

    final alert = FakeData.fireAlert(id: 'evt-9');
    repo.emit(DetectionNotified(alert));
    await tester.pumpAndSettle();
    expect(find.text('Báo tới điện thoại'), findsOneWidget);
    expect(find.text('+6,8 s'), findsOneWidget);
    expect(find.text('Đã báo cho bạn và đội trực ca.'), findsOneWidget);
    expect(find.text('Báo sau 6,8 giây'), findsOneWidget);
    expect(find.text('alert evt-9'), findsNothing);

    repo.emit(DetectionNotified(alert, openAlert: true));
    await tester.pumpAndSettle();
    expect(find.text('alert evt-9'), findsOneWidget);

    router.pop();
    await tester.pumpAndSettle();
    expect(find.text('Báo sau 6,8 giây'), findsOneWidget);
  });

  testWidgets('"Bỏ qua" dismisses the suspect and watching resumes', (
    tester,
  ) async {
    final repo = ScriptedDetectionRepository();
    await open(tester, _fire, repository: repo);
    repo.emit(
      DetectionVerifying(
        suspect: _suspect,
        steps: const [_detected, _imageSent],
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text(_skip));
    await tester.pumpAndSettle();
    expect(repo.skips, 1);
    expect(find.text('Máy phát hiện khói'), findsNothing);
    expect(find.text('AI đang quét'), findsOneWidget);
  });

  testWidgets('server failure (unverified) opens the alert route at once', (
    tester,
  ) async {
    final repo = ScriptedDetectionRepository();
    await open(tester, _fire, repository: repo);

    repo.emit(DetectionUnverified(FakeData.unverifiedEvent(id: 'evt-4')));
    await tester.pumpAndSettle();
    expect(find.text('alert evt-4'), findsOneWidget);
  });

  testWidgets('dismissed shows the toast, then scanning resumes', (
    tester,
  ) async {
    final repo = ScriptedDetectionRepository();
    await open(tester, 'cam-ramp', repository: repo);

    repo.emit(
      DetectionDismissed(
        reason: FakeData.dismissalReason,
        event: FakeData.dismissedEvent(id: 'evt-2'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Không phải cháy'), findsOneWidget);
    expect(find.text('Chỉ là đèn xe chiếu lên tường.'), findsOneWidget);
    expect(find.text('Hình ảnh chỉ nằm trên máy này.'), findsOneWidget);
    expect(find.text('AI đang quét'), findsOneWidget);

    repo.emit(const DetectionWatching());
    await tester.pumpAndSettle();
    expect(find.text('Không phải cháy'), findsNothing);
    expect(find.text('AI đang quét'), findsOneWidget);
  });

  testWidgets('the dismissal toast links to the history entry', (tester) async {
    final repo = ScriptedDetectionRepository();
    await open(tester, 'cam-ramp', repository: repo);
    repo.emit(
      DetectionDismissed(
        reason: FakeData.dismissalReason,
        event: FakeData.dismissedEvent(id: 'evt-2'),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Xem'));
    await tester.pumpAndSettle();
    expect(find.text('history evt-2'), findsOneWidget);
  });

  testWidgets('offline and slow-device banners', (tester) async {
    final repo = ScriptedDetectionRepository();
    await open(tester, _fire, repository: repo);

    repo.emit(const DetectionOffline());
    await tester.pumpAndSettle();
    expect(find.text('Mất mạng'), findsOneWidget);
    expect(find.text('Mất kết nối. Có mạng sẽ tự nối lại.'), findsOneWidget);
    expect(find.text('Mất kết nối · Có mạng sẽ tự nối lại'), findsOneWidget);
    expect(find.text('Gọi 114 nếu thấy khói thật'), findsOneWidget);
    await tester.tap(find.text('Gọi 114 nếu thấy khói thật'));
    await tester.pumpAndSettle();
    final container = ProviderScope.containerOf(
      tester.element(find.text('Gọi 114 nếu thấy khói thật')),
    );
    expect((container.read(phoneDialerProvider) as FakePhoneDialer).dialed, [
      '114',
    ]);

    repo.emit(const DetectionDegraded(fromFps: 5, fps: degradedFps));
    await tester.pumpAndSettle();
    expect(find.text('Mất mạng'), findsNothing);
    expect(find.text('Máy nóng, đã quét chậm lại'), findsOneWidget);
    expect(find.textContaining('khung/giây'), findsNothing);
    expect(find.text('Cắm sạc'), findsOneWidget);
    expect(find.text('Tắt các app khác'), findsOneWidget);
  });

  testWidgets('"Toàn màn hình" opens E8; × closes it', (tester) async {
    final repo = ScriptedDetectionRepository();
    await open(tester, _fire, repository: repo);
    repo.emit(const DetectionWatching());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Toàn màn hình'));
    await tester.pumpAndSettle();
    expect(location(), DetectionPaths.fullScreen(_fire));
    expect(find.byType(WatchFullScreen), findsOneWidget);
    expect(find.text('Chạm × để thoát'), findsOneWidget);
    expect(find.text('HẦM B1 · 23/10/2025 21:47:43'), findsOneWidget);
    expect(repo.stops, 0);

    await tester.tap(find.bySemanticsLabel('Thoát toàn màn hình'));
    await tester.pumpAndSettle();
    expect(location(), AppRoutes.watch(_fire));
    expect(find.byType(WatchFullScreen), findsNothing);
    expect(find.text('AI đang quét'), findsOneWidget);
  });

  testWidgets('back leaves the screen and ends the session', (tester) async {
    final repo = ScriptedDetectionRepository();
    await open(tester, _fire, repository: repo);
    repo.emit(const DetectionWatching());
    await tester.pumpAndSettle();

    await tester.tap(find.bySemanticsLabel('Quay lại'));
    await tester.pumpAndSettle();
    expect(find.text('I7'), findsOneWidget);
    expect(repo.stops, 1);
  });

  testWidgets('a camera opened from the list draws E2 on its first frame', (
    tester,
  ) async {
    tester.view
      ..physicalSize = const Size(360, 780)
      ..devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final repo = ScriptedDetectionRepository();
    final list = GoRouter(
      navigatorKey: rootNavigatorKey,
      initialLocation: AppRoutes.monitor,
      routes: [
        GoRoute(
          path: AppRoutes.monitor,
          builder: (_, _) => Consumer(
            builder: (_, ref, _) {
              ref.watch(placeCamerasProvider);
              return const Scaffold(body: Text('I7'));
            },
          ),
          routes: detectionRoutes,
        ),
      ],
    );
    addTearDown(list.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: fakeOverrides([
          fakeScenarioProvider.overrideWithValue(const FakeScenario()),
          detectionRepositoryProvider.overrideWithValue(repo),
          clockProvider.overrideWithValue(() => FakeData.demoNow),
        ]),
        child: MaterialApp.router(theme: AppTheme.dark(), routerConfig: list),
      ),
    );
    await tester.pump(const Duration(seconds: 5));

    unawaited(list.push(AppRoutes.watch(_fire)));
    await tester.pump();
    expect(find.text('Hầm B1 · Khu sạc xe'), findsOneWidget);
    expect(find.text('HẦM B1 · 23/10/2025 21:47:43'), findsOneWidget);
    expect(find.text('Toàn màn hình'), findsOneWidget);
    expect(find.text('AI đang quét'), findsOneWidget);
    await tester.pump();
    expect(repo.started.single.id, _fire);

    await tester.pump(const Duration(seconds: 5));
    expect(find.text('Hầm B1 · Khu sạc xe'), findsOneWidget);
    expect(repo.started, hasLength(1));
  });

  testWidgets('a reload under the session keeps E2 on screen', (tester) async {
    final repo = ScriptedDetectionRepository();
    await open(
      tester,
      _fire,
      repository: repo,
      scenario: const FakeScenario(freezeClock: true),
    );
    await tester.pump(const Duration(seconds: 2));
    repo.emit(const DetectionWatching());
    await tester.pumpAndSettle();
    expect(find.text('Toàn màn hình'), findsOneWidget);

    final container = ProviderScope.containerOf(
      tester.element(find.text('Toàn màn hình')),
    )..invalidate(groupsProvider);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(container.read(cameraDetailProvider(_fire)).isLoading, isTrue);
    expect(find.text('Toàn màn hình'), findsOneWidget);
    expect(find.text('AI đang quét'), findsOneWidget);

    await tester.pump(const Duration(seconds: 2));
    expect(find.text('Toàn màn hình'), findsOneWidget);
    expect(repo.started, hasLength(1));
  });

  testWidgets('an unknown camera says so', (tester) async {
    final repo = ScriptedDetectionRepository();
    await open(tester, 'cam-gone', repository: repo);
    expect(find.text('Không tìm thấy camera.'), findsOneWidget);
    expect(repo.started, isEmpty);
  });

  testWidgets('fake: the fire camera ends on the alert screen over E2d', (
    tester,
  ) async {
    await open(tester, _fire);
    expect(find.textContaining('alert evt-'), findsOneWidget);
    router.pop();
    await tester.pumpAndSettle();
    expect(find.text('Báo sau 6,8 giây'), findsOneWidget);
  });

  testWidgets('fake: the fire camera fires once; reopening just watches', (
    tester,
  ) async {
    await open(tester, _fire);
    expect(find.textContaining('alert evt-'), findsOneWidget);

    router.go(AppRoutes.monitor);
    await tester.pumpAndSettle();
    unawaited(router.push(AppRoutes.watch(_fire)));
    await tester.pumpAndSettle();
    expect(find.textContaining('alert evt-'), findsNothing);
    expect(find.text('AI đang quét'), findsOneWidget);
    expect(find.text('Máy phát hiện khói'), findsNothing);
  });
}
