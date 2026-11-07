import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_banner.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import 'package:mat_pho/data/errors.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_alert_repository.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_notification_service.dart';
import '../../fakes/fake_phone_dialer.dart';
import '../../fakes/fake_scenario.dart';
import '../../fakes/fake_world.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/repositories/alert_repository.dart';
import 'package:mat_pho/features/alert/alert_actions.dart';
import 'package:mat_pho/features/alert/alert_controller.dart';
import 'package:mat_pho/features/alert/alert_listener.dart';
import 'package:mat_pho/features/alert/alert_routes.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/groups/current_group.dart';
import 'package:mat_pho/features/alert/call_screen.dart';

final _fire = FakeData.fireAlert(id: 'evt-live');

class _SpyToasts extends AlertToasts {
  final calls = <(AlertOutcome, String, VoidCallback?)>[];

  @override
  void resolved(
    BuildContext context, {
    required String locationName,
    VoidCallback? onUndo,
  }) => calls.add((AlertOutcome.resolved, locationName, onUndo));

  @override
  void falseAlarm(
    BuildContext context, {
    required String locationName,
    required VoidCallback onUndo,
  }) => calls.add((AlertOutcome.falseAlarm, locationName, onUndo));
}

class _Harness {
  _Harness(this.router, this.world, this.toasts, this.dialer, this.container);

  final GoRouter router;
  final FakeWorld world;
  final _SpyToasts toasts;
  final FakePhoneDialer dialer;
  final ProviderContainer container;

  String get location => router.state.uri.path;
  FireEvent event(String id) => world.event(id);
  FakeNotificationService get notifications =>
      container.read(notificationServiceProvider) as FakeNotificationService;
}

Future<_Harness> _pump(
  WidgetTester tester,
  String initialLocation, {
  bool dialerAvailable = true,
  Set<FakeCase> cases = const {},
  List<Override> overrides = const [],
}) async {
  tester.view
    ..physicalSize = const Size(360, 780)
    ..devicePixelRatio = 1;
  addTearDown(tester.view.reset);

  final world = FakeWorld(FakeScenario.test(cases: cases))..addEvent(_fire);
  final toasts = _SpyToasts();
  final dialer = FakePhoneDialer(available: dialerAvailable);
  Widget tab(String name) => Scaffold(
    body: AlertListener(child: Center(child: Text(name))),
  );
  final router = GoRouter(
    initialLocation: initialLocation,
    routes: [
      ...alertRoutes,
      GoRoute(
        path: AppRoutes.monitor,
        builder: (_, _) => tab('monitor-tab'),
        routes: [
          GoRoute(
            path: 'watch/:cameraId',
            builder: (_, state) => Scaffold(
              body: Text('watch ${state.pathParameters['cameraId']}'),
            ),
            routes: [
              GoRoute(
                path: 'full',
                builder: (_, _) => const Scaffold(body: Text('full')),
              ),
            ],
          ),
        ],
      ),
      GoRoute(path: AppRoutes.history, builder: (_, _) => tab('history-tab')),
    ],
  );
  addTearDown(router.dispose);

  await tester.pumpWidget(
    ProviderScope(
      overrides: fakeOverrides([
        fakeWorldProvider.overrideWithValue(world),
        alertToastsProvider.overrideWithValue(toasts),
        phoneDialerProvider.overrideWithValue(dialer),
        authSessionProvider.overrideWith(_SignedIn.new),
        ...overrides,
      ]),
      child: MaterialApp.router(theme: AppTheme.dark(), routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
  final container = ProviderScope.containerOf(
    tester.element(find.byType(MaterialApp)),
  );
  return _Harness(router, world, toasts, dialer, container);
}

Finder _semantics(Type screen, String label) => find.descendant(
  of: find.byType(screen),
  matching: find.byWidgetPredicate(
    (w) => w is Semantics && w.properties.label == label,
  ),
);

void main() {
  testWidgets('F2 shows the confirmed alert, 114 first', (tester) async {
    await _pump(tester, AppRoutes.alert(_fire.id));

    expect(find.text('Đã xác nhận cháy'), findsOneWidget);
    expect(find.text('Cháy ở Hầm xe'), findsOneWidget);
    expect(find.text('HẦM XE · 23/10/2025 21:47:31'), findsOneWidget);
    expect(find.text('21:47:31 · 12 giây trước'), findsOneWidget);
    expect(find.text('93% · đã kiểm tra 2 lần'), findsOneWidget);
    expect(find.text('Lửa và khói ở xe máy bên trái'), findsOneWidget);

    final call = tester.getTopLeft(find.text('Gọi 114')).dy;
    expect(tester.getTopLeft(find.text('Báo nhầm')).dy, greaterThan(call));
    expect(tester.getTopLeft(find.text('Đã xử lý')).dy, greaterThan(call));
    expect(find.text('Xem camera'), findsNothing);
  });

  testWidgets('Gọi 114 opens the phone dialer with 114, call recorded', (
    tester,
  ) async {
    final h = await _pump(tester, AppRoutes.alert(_fire.id));

    await tester.tap(find.text('Gọi 114'));
    await tester.pumpAndSettle();
    expect(h.dialer.dialed, ['114']);
    expect(h.location, AppRoutes.alert(_fire.id));
    expect(h.event(_fire.id).called114, isTrue);
    expect(h.event(_fire.id).timeline, _fire.timeline);
  });

  testWidgets('no dialer on the device: a toast, no call recorded', (
    tester,
  ) async {
    final h = await _pump(
      tester,
      AppRoutes.alert(_fire.id),
      dialerAvailable: false,
    );

    await tester.tap(find.text('Gọi 114'));
    await tester.pumpAndSettle();
    expect(h.dialer.dialed, isEmpty);
    expect(
      find.text('Máy này không gọi được. Hãy gọi 114 bằng máy khác.'),
      findsOneWidget,
    );
    expect(h.event(_fire.id).called114, isFalse);
    hideMpToast();
    await tester.pumpAndSettle();
  });

  testWidgets('F7 (gallery) reads the address; Kết thúc → F5; undo', (
    tester,
  ) async {
    final h = await _pump(tester, AlertPaths.call(_fire.id));
    expect(
      find.text('Hầm B1, chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7'),
      findsOneWidget,
    );
    expect(find.text('Cháy xe máy ở khu sạc · từ 21:47'), findsOneWidget);
    expect(find.text('Đã kết nối · 00:00'), findsOneWidget);
    await tester.pump(const Duration(seconds: 2));
    expect(find.text('Đã kết nối · 00:02'), findsOneWidget);

    await tester.tap(_semantics(CallScreen, 'Kết thúc'));
    await tester.pumpAndSettle();
    expect(h.location, AppRoutes.alert(_fire.id));
    expect(find.text('Bạn đang xử lý'), findsOneWidget);
    expect(find.text('Đã ngừng báo cho người khác.'), findsOneWidget);
    expect(find.text('Gọi 114'), findsOneWidget);
    expect(find.text('Về Theo dõi'), findsOneWidget);
    expect(find.text('Đã xử lý'), findsNothing);
    expect(h.event(_fire.id).resolved, isFalse);

    await tester.tap(find.text('Hoàn tác'));
    await tester.pumpAndSettle();
    expect(find.text('Đã xử lý'), findsOneWidget);
    await tester.pump(undoWindow * 2);
    expect(h.event(_fire.id).resolved, isFalse);
    expect(find.text('Đã xử lý'), findsOneWidget);
  });

  testWidgets('F5 drops "Hoàn tác" after the undo window, then sends', (
    tester,
  ) async {
    final h = await _pump(tester, AlertPaths.call(_fire.id));
    await tester.tap(_semantics(CallScreen, 'Kết thúc'));
    await tester.pumpAndSettle();
    expect(find.text('Hoàn tác'), findsOneWidget);
    expect(h.event(_fire.id).resolved, isFalse);

    await tester.pump(undoWindow);
    await tester.pump();
    expect(find.text('Hoàn tác'), findsNothing);
    expect(find.text('Bạn đang xử lý'), findsOneWidget);
    expect(h.event(_fire.id).resolved, isTrue);
  });

  testWidgets('leaving F5 within the undo window sends the resolve at once', (
    tester,
  ) async {
    final h = await _pump(tester, AlertPaths.call(_fire.id));
    await tester.tap(_semantics(CallScreen, 'Kết thúc'));
    await tester.pumpAndSettle();
    expect(h.event(_fire.id).resolved, isFalse);

    await tester.tap(find.text('Về Theo dõi'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(h.location, AppRoutes.monitor);
    expect(h.container.exists(alertProvider(_fire.id)), isFalse);
    await tester.pump(const Duration(milliseconds: 100));
    expect(h.event(_fire.id).resolved, isTrue);
  });

  testWidgets('F8 (gallery) "Mắt Phố" goes back to the alert', (tester) async {
    final h = await _pump(tester, AlertPaths.dialer(_fire.id));

    await tester.tap(find.text('Mắt Phố'));
    await tester.pumpAndSettle();
    expect(h.location, AppRoutes.alert(_fire.id));
    expect(find.text('Cháy ở Hầm xe'), findsOneWidget);
  });

  testWidgets('Báo nhầm → F9 → Theo dõi + K5 toast with undo', (tester) async {
    final h = await _pump(tester, AppRoutes.alert(_fire.id));

    await tester.tap(find.text('Báo nhầm'));
    await tester.pumpAndSettle();
    expect(find.text('Báo nhầm?'), findsOneWidget);
    expect(
      find.text('AI sẽ ghi nhận đây không phải cháy và tắt cảnh báo này.'),
      findsOneWidget,
    );

    await tester.tap(find.text('Không'));
    await tester.pumpAndSettle();
    expect(h.location, AppRoutes.alert(_fire.id));
    expect(h.toasts.calls, isEmpty);

    await tester.tap(find.text('Báo nhầm'));
    await tester.pumpAndSettle();
    showMpAlertBanner(
      tester.element(find.text('Xác nhận')),
      const MpAlertBanner(title: 'Cháy · Kho'),
    );
    await tester.pumpAndSettle();
    expect(find.byType(MpAlertBanner), findsOneWidget);
    await tester.tap(find.text('Xác nhận'));
    await tester.pumpAndSettle();

    expect(h.location, AppRoutes.monitor);
    expect(find.text('monitor-tab'), findsOneWidget);
    expect(h.toasts.calls, hasLength(1));
    final (outcome, where, undo) = h.toasts.calls.single;
    expect(outcome, AlertOutcome.falseAlarm);
    expect(where, 'Hầm xe');
    expect(h.notifications.cleared, [_fire.id]);
    expect(find.byType(MpAlertBanner), findsNothing);
    expect(h.event(_fire.id).status, EventStatus.fire);

    undo!();
    await tester.pumpAndSettle();
    expect(h.location, AppRoutes.alert(_fire.id));
    expect(find.text('Báo nhầm'), findsOneWidget);
    await tester.pump(undoWindow * 2);
    expect(h.event(_fire.id).status, EventStatus.fire);
  });

  testWidgets('Báo nhầm without "Hoàn tác" reaches the server after 5 s', (
    tester,
  ) async {
    final h = await _pump(tester, AppRoutes.alert(_fire.id));
    await tester.tap(find.text('Báo nhầm'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Xác nhận'));
    await tester.pumpAndSettle();
    expect(h.event(_fire.id).status, EventStatus.fire);

    await tester.pump(undoWindow);
    await tester.pump();
    expect(h.event(_fire.id).status, EventStatus.falseAlarm);
  });

  testWidgets('an alert closed as a false alarm cannot be closed again', (
    tester,
  ) async {
    final h = await _pump(tester, AppRoutes.monitor);
    h.world.addEvent(
      FakeData.fireAlert(
        id: 'evt-closed',
      ).copyWith(status: EventStatus.falseAlarm),
    );
    h.router.push(AppRoutes.alert('evt-closed'));
    await tester.pumpAndSettle();
    expect(find.text('Đã báo nhầm'), findsOneWidget);
    expect(find.text('Báo nhầm'), findsNothing);
    expect(find.text('Đã xử lý'), findsNothing);
    expect(find.text('Gọi 114'), findsOneWidget);
  });

  testWidgets('an alert that cannot load still offers "Gọi 114"', (
    tester,
  ) async {
    final h = await _pump(tester, AppRoutes.alert('evt-unknown'));
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Không tải được cảnh báo'), findsOneWidget);
    await tester.tap(find.text('Gọi 114'));
    await tester.pumpAndSettle();
    expect(h.dialer.dialed, ['114']);
  });

  testWidgets('Đã xử lý → F10 → Theo dõi + K4 toast with undo', (tester) async {
    final h = await _pump(tester, AppRoutes.alert(_fire.id));

    await tester.tap(find.text('Đã xử lý'));
    await tester.pumpAndSettle();
    expect(find.text('Đã xử lý xong?'), findsOneWidget);
    expect(
      find.text('Cảnh báo sẽ đóng lại và được lưu vào Lịch sử.'),
      findsOneWidget,
    );
    await tester.tap(find.text('Xác nhận'));
    await tester.pumpAndSettle();

    expect(h.location, AppRoutes.monitor);
    expect(h.notifications.cleared, [_fire.id]);
    expect(h.event(_fire.id).resolved, isFalse);
    final (outcome, where, undo) = h.toasts.calls.single;
    expect(outcome, AlertOutcome.resolved);
    expect(where, 'Hầm xe');

    undo!();
    await tester.pumpAndSettle();
    expect(h.location, AppRoutes.alert(_fire.id));
    expect(find.text('Đã xử lý'), findsOneWidget);
    await tester.pump(undoWindow * 2);
    expect(h.event(_fire.id).resolved, isFalse);
  });

  testWidgets('Đã xử lý without "Hoàn tác" reaches the server after 5 s', (
    tester,
  ) async {
    final h = await _pump(tester, AppRoutes.alert(_fire.id));
    await tester.tap(find.text('Đã xử lý'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Xác nhận'));
    await tester.pumpAndSettle();
    expect(h.event(_fire.id).resolved, isFalse);

    await tester.pump(undoWindow);
    await tester.pump();
    expect(h.event(_fire.id).resolved, isTrue);
  });

  testWidgets('F2 shows "Gọi 114" at once; closing waits for the role', (
    tester,
  ) async {
    final groups = Completer<List<Group>>();
    await _pump(
      tester,
      AppRoutes.alert(_fire.id),
      overrides: [groupsProvider.overrideWith((ref) => groups.future)],
    );
    expect(find.text('Cháy ở Hầm xe'), findsOneWidget);
    expect(find.text('Gọi 114'), findsOneWidget);
    expect(find.text('Về Theo dõi'), findsNothing);
    expect(find.text('Báo nhầm'), findsNothing);
    expect(find.text('Đã xử lý'), findsNothing);

    groups.complete(FakeData.groups);
    await tester.pumpAndSettle();
    expect(find.text('Gọi 114'), findsOneWidget);
    expect(find.text('Báo nhầm'), findsOneWidget);
    expect(find.text('Đã xử lý'), findsOneWidget);
    expect(find.text('Về Theo dõi'), findsNothing);
  });

  testWidgets('"Chỉ báo cháy": "Về Theo dõi" is added once the role is known', (
    tester,
  ) async {
    final groups = Completer<List<Group>>();
    final h = await _pump(
      tester,
      AppRoutes.alert(_fire.id),
      cases: {FakeCase.alertsOnlyRole},
      overrides: [groupsProvider.overrideWith((ref) => groups.future)],
    );
    expect(find.text('Gọi 114'), findsOneWidget);
    expect(find.text('Về Theo dõi'), findsNothing);
    expect(find.text('Báo nhầm'), findsNothing);

    groups.complete(h.world.groups);
    await tester.pumpAndSettle();
    expect(find.text('Gọi 114'), findsOneWidget);
    expect(find.text('Về Theo dõi'), findsOneWidget);
    expect(find.text('Báo nhầm'), findsNothing);
    expect(find.text('Đã xử lý'), findsNothing);
  });

  testWidgets('a failed role lookup still lets the alert be closed', (
    tester,
  ) async {
    await _pump(
      tester,
      AppRoutes.alert(_fire.id),
      overrides: [
        groupsProvider.overrideWith(
          (ref) => Future<List<Group>>.error(const NetworkException()),
        ),
      ],
    );
    expect(find.text('Báo nhầm'), findsOneWidget);
    expect(find.text('Đã xử lý'), findsOneWidget);
  });

  for (final (code, id) in [('F2', 'evt-live'), ('F4', 'evt-unverified')]) {
    testWidgets('$code for "Chỉ báo cháy": only Gọi 114 and Về Theo dõi', (
      tester,
    ) async {
      final h = await _pump(
        tester,
        AppRoutes.alert(id),
        cases: {FakeCase.alertsOnlyRole},
      );
      expect(find.text('Gọi 114'), findsOneWidget);
      expect(find.text('Về Theo dõi'), findsOneWidget);
      expect(find.text('Báo nhầm'), findsNothing);
      expect(find.text('Đã xử lý'), findsNothing);
      expect(find.text('Xem camera'), findsNothing);

      await tester.tap(find.text('Về Theo dõi'));
      await tester.pumpAndSettle();
      expect(h.location, AppRoutes.monitor);
    });
  }

  testWidgets('F4 for an alert the server could not verify', (tester) async {
    final h = await _pump(tester, AppRoutes.alert('evt-unverified'));

    expect(find.text('Chưa chắc chắn'), findsOneWidget);
    expect(find.text('Có thể có khói ở Hầm xe'), findsOneWidget);
    expect(find.text('Chưa kiểm tra lại được'), findsOneWidget);
    expect(find.text('Xem camera hoặc tới tận nơi kiểm tra.'), findsOneWidget);
    expect(find.text('Gọi 114'), findsOneWidget);
    expect(find.text('Báo nhầm'), findsOneWidget);
    expect(find.text('Xem camera'), findsOneWidget);
    expect(find.text('Đã xử lý'), findsNothing);
    expect(find.text('Lúc'), findsNothing);

    await tester.tap(find.text('Báo nhầm'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Xác nhận'));
    await tester.pumpAndSettle();
    expect(h.location, AppRoutes.monitor);
    await tester.pump(undoWindow);
    await tester.pump();
    expect(h.event('evt-unverified').status, EventStatus.falseAlarm);
  });

  testWidgets('F6 banner on another tab opens the alert when tapped', (
    tester,
  ) async {
    final h = await _pump(tester, AppRoutes.history);

    h.world.addEvent(FakeData.fireAlert(id: 'evt-new'), alert: true);
    await tester.pumpAndSettle();
    expect(find.byType(MpAlertBanner), findsOneWidget);
    expect(find.text('Cháy · Hầm xe'), findsOneWidget);
    expect(find.text('Lửa ở xe máy · chạm để xem'), findsOneWidget);
    expect(find.text('history-tab'), findsOneWidget);

    await tester.tap(find.byType(MpAlertBanner));
    await tester.pumpAndSettle();
    expect(h.location, AppRoutes.alert('evt-new'));
    expect(find.text('Cháy ở Hầm xe'), findsOneWidget);
    expect(find.byType(MpAlertBanner), findsNothing);
  });

  testWidgets('no F6 banner while an alert screen is open', (tester) async {
    final h = await _pump(tester, AppRoutes.monitor);
    h.router.push(AppRoutes.alert(_fire.id));
    await tester.pumpAndSettle();

    h.world.addEvent(FakeData.fireAlert(id: 'evt-new'), alert: true);
    await tester.pumpAndSettle();
    expect(find.byType(MpAlertBanner), findsNothing);
  });

  testWidgets('F4 "Xem camera" opens the watch screen of its camera', (
    tester,
  ) async {
    final h = await _pump(tester, AppRoutes.alert('evt-unverified'));
    await tester.tap(find.text('Xem camera'));
    await tester.pumpAndSettle();
    expect(h.location, AppRoutes.watch(FakeData.fireCameraId));
    expect(find.text('watch ${FakeData.fireCameraId}'), findsOneWidget);
  });

  testWidgets('no F6 banner on the watch screen of the alert camera', (
    tester,
  ) async {
    final h = await _pump(tester, AppRoutes.monitor);
    h.router.go(AppRoutes.watch(_fire.cameraId));
    await tester.pumpAndSettle();

    h.world.addEvent(FakeData.fireAlert(id: 'evt-new'), alert: true);
    await tester.pumpAndSettle();
    expect(find.byType(MpAlertBanner), findsNothing);

    h.world.addEvent(
      FakeData.fireAlert(id: 'evt-other', cameraId: 'cam-ramp'),
      alert: true,
    );
    await tester.pumpAndSettle();
    expect(find.byType(MpAlertBanner), findsOneWidget);
    hideMpAlertBanner();
    await tester.pumpAndSettle();
  });

  testWidgets('no F6 banner on the full-screen view (E8) of that camera', (
    tester,
  ) async {
    final h = await _pump(tester, AppRoutes.monitor);
    h.router.go('${AppRoutes.watch(_fire.cameraId)}/full');
    await tester.pumpAndSettle();
    expect(find.text('full'), findsOneWidget);

    h.world.addEvent(FakeData.fireAlert(id: 'evt-new'), alert: true);
    await tester.pumpAndSettle();
    expect(find.byType(MpAlertBanner), findsNothing);
  });

  group('closed by someone else (FIRE_ALERT_UPDATED)', () {
    late StreamController<AlertUpdate> updates;

    setUp(() => updates = StreamController<AlertUpdate>.broadcast());
    tearDown(() => updates.close());

    Override closableAlerts() => alertRepositoryProvider.overrideWith(
      (ref) => _UpdatingAlerts(
        FakeAlertRepository(ref.watch(fakeWorldProvider)),
        updates,
      ),
    );

    testWidgets('stops F1 ringing and takes the F6 banner away', (
      tester,
    ) async {
      final h = await _pump(
        tester,
        AppRoutes.history,
        overrides: [closableAlerts()],
      );
      h.world.addEvent(FakeData.fireAlert(id: 'evt-new'), alert: true);
      await tester.pumpAndSettle();
      expect(find.byType(MpAlertBanner), findsOneWidget);

      updates.add(
        const AlertUpdate(
          eventId: 'evt-other',
          outcome: AlertUpdateOutcome.resolved,
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(MpAlertBanner), findsOneWidget);

      updates.add(
        const AlertUpdate(
          eventId: 'evt-new',
          outcome: AlertUpdateOutcome.resolved,
          resolvedByName: 'Trần Văn Bình',
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(MpAlertBanner), findsNothing);
      expect(h.notifications.cleared, ['evt-other', 'evt-new']);
    });

    testWidgets('F2 turns into F5 with the name of who took it', (
      tester,
    ) async {
      await _pump(
        tester,
        AppRoutes.alert(_fire.id),
        overrides: [closableAlerts()],
      );
      expect(find.text('Đã xử lý'), findsOneWidget);

      updates.add(
        AlertUpdate(
          eventId: _fire.id,
          outcome: AlertUpdateOutcome.resolved,
          resolvedByName: 'Trần Văn Bình',
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Trần Văn Bình đang xử lý'), findsOneWidget);
      expect(find.text('Hoàn tác'), findsNothing);
      expect(find.text('Về Theo dõi'), findsOneWidget);
    });

    testWidgets('the user\'s own name still reads "Bạn đang xử lý"', (
      tester,
    ) async {
      await _pump(
        tester,
        AppRoutes.alert(_fire.id),
        overrides: [closableAlerts()],
      );
      updates.add(
        AlertUpdate(
          eventId: _fire.id,
          outcome: AlertUpdateOutcome.resolved,
          resolvedByName: FakeData.user.fullName,
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Bạn đang xử lý'), findsOneWidget);
    });

    testWidgets('a false alarm from another phone shows "Đã báo nhầm"', (
      tester,
    ) async {
      await _pump(
        tester,
        AppRoutes.alert(_fire.id),
        overrides: [closableAlerts()],
      );
      updates.add(
        AlertUpdate(eventId: _fire.id, outcome: AlertUpdateOutcome.falseAlarm),
      );
      await tester.pumpAndSettle();
      expect(find.text('Đã báo nhầm'), findsOneWidget);
      expect(find.text('Báo nhầm'), findsNothing);
    });
  });
}

final class _UpdatingAlerts implements AlertRepository {
  _UpdatingAlerts(this._inner, this._updates);

  final AlertRepository _inner;
  final StreamController<AlertUpdate> _updates;

  @override
  Stream<AlertUpdate> alertUpdates() => _updates.stream;

  @override
  Stream<FireEvent> incomingAlerts() => _inner.incomingAlerts();

  @override
  Future<FireEvent> getAlert(String eventId) => _inner.getAlert(eventId);

  @override
  Future<FireEvent> recordCall114(String eventId) =>
      _inner.recordCall114(eventId);

  @override
  Future<FireEvent> resolve(String eventId) => _inner.resolve(eventId);

  @override
  Future<FireEvent> markFalseAlarm(String eventId) =>
      _inner.markFalseAlarm(eventId);

  @override
  Future<FireEvent> reportRealFire(String eventId) =>
      _inner.reportRealFire(eventId);

  @override
  Future<EscalationStatus> escalationStatus(String eventId) =>
      _inner.escalationStatus(eventId);

  @override
  Future<DispatchInfo> dispatchInfo(String eventId) =>
      _inner.dispatchInfo(eventId);

  @override
  Future<List<AuditEntry>> auditLog(String eventId) => _inner.auditLog(eventId);
}

class _SignedIn extends AuthSessionNotifier {
  @override
  AuthSession build() => const SignedIn(FakeData.user);
}
