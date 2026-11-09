import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/app.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_notification_service.dart';
import '../../fakes/fake_phone_dialer.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/services/notification_service.dart';
import 'package:mat_pho/features/auth/permission_controller.dart';

Future<ProviderContainer> _launch(
  WidgetTester tester, {
  FakeNotificationService? notifications,
  FakePhoneDialer? dialer,
}) async {
  tester.view
    ..physicalSize = const Size(360, 780) * 2
    ..devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    ProviderScope(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(const FakeScenario.test()),
        if (notifications != null)
          notificationServiceProvider.overrideWithValue(notifications),
        if (dialer != null) phoneDialerProvider.overrideWithValue(dialer),
      ]),
      child: const MatPhoApp(),
    ),
  );
  await tester.pump(const Duration(seconds: 2));
  await tester.pumpAndSettle();
  return ProviderScope.containerOf(tester.element(find.byType(MatPhoApp)));
}

FakeNotificationService _service(ProviderContainer c) =>
    c.read(notificationServiceProvider) as FakeNotificationService;

FireEvent _pushFire(ProviderContainer c, {String id = 'evt-push'}) {
  final alert = FakeData.fireAlert(id: id);
  c.read(fakeWorldProvider).addEvent(alert, alert: true);
  return alert;
}

void _lifecycle(WidgetTester tester, List<AppLifecycleState> states) {
  for (final s in states) {
    tester.binding.handleAppLifecycleStateChanged(s);
  }
}

const _toBackground = [
  AppLifecycleState.inactive,
  AppLifecycleState.hidden,
  AppLifecycleState.paused,
];
const _toForeground = [
  AppLifecycleState.hidden,
  AppLifecycleState.inactive,
  AppLifecycleState.resumed,
];

void main() {
  testWidgets('in the foreground the in-app alert is enough', (tester) async {
    final c = await _launch(tester);
    _pushFire(c);
    await tester.pump();
    expect(_service(c).shown, isEmpty);
    await tester.pump(const Duration(seconds: 10));
    await tester.pumpAndSettle();
  });

  testWidgets(
    'in the background a fire, or an unverified one, is a notification',
    (tester) async {
      final c = await _launch(tester);
      _lifecycle(tester, _toBackground);
      final alert = _pushFire(c);
      c
          .read(fakeWorldProvider)
          .addEvent(
            FakeData.unverifiedEvent(id: 'evt-unverified'),
            alert: true,
          );
      await tester.pump();
      expect(_service(c).shown.first, (
        title: fireAlertTitle(alert),
        body: fireAlertBody(alert),
        eventId: alert.id,
      ));
      expect(_service(c).shown.first.title, 'Có cháy · Hầm xe');
      expect(_service(c).shown.last, (
        title: 'Có thể có khói ở Hầm xe',
        body: 'Chưa kiểm tra lại được. Chạm để xem ảnh.',
        eventId: 'evt-unverified',
      ));
      _lifecycle(tester, _toForeground);
      await tester.pump(const Duration(seconds: 10));
      await tester.pumpAndSettle();
    },
  );

  testWidgets('tapping the notification opens F2', (tester) async {
    final c = await _launch(tester);
    _lifecycle(tester, _toBackground);
    final alert = _pushFire(c);
    await tester.pump();
    _lifecycle(tester, _toForeground);
    _service(c).tap(alert.id);
    await tester.pump();
    await tester.pump(const Duration(seconds: 10));
    await tester.pumpAndSettle();
    expect(find.text('Cháy ở Hầm xe'), findsOneWidget);
  });

  testWidgets(
    'back in the app while it rings: the notification goes, F2 opens and rings on',
    (tester) async {
      final c = await _launch(tester);
      _lifecycle(tester, _toBackground);
      final alert = _pushFire(c);
      await tester.pump();
      expect(_service(c).cleared, isEmpty);
      _lifecycle(tester, _toForeground);
      await tester.pump();
      await tester.pump(const Duration(seconds: 10));
      await tester.pumpAndSettle();
      expect(_service(c).cleared.toSet(), {alert.id});
      expect(_service(c).ringing, isTrue);
      expect(find.text('Cháy ở Hầm xe'), findsOneWidget);
    },
  );

  testWidgets('F1 "Gọi 114" opens F2 and the dialer with 114', (tester) async {
    final dialer = FakePhoneDialer();
    final c = await _launch(tester, dialer: dialer);
    _lifecycle(tester, _toBackground);
    final alert = _pushFire(c);
    await tester.pump();
    _service(c).tap(alert.id, call114: true);
    _lifecycle(tester, _toForeground);
    await tester.pump();
    await tester.pump(const Duration(seconds: 10));
    await tester.pumpAndSettle();
    expect(find.text('Cháy ở Hầm xe'), findsOneWidget);
    expect(dialer.dialed, ['114']);
  });

  testWidgets('a tap that launched the app opens F2 after the splash', (
    tester,
  ) async {
    await _launch(
      tester,
      notifications: FakeNotificationService(
        const FakeScenario.test(),
        launchAlertId: FakeData.fireAlert().id,
      ),
    );
    expect(find.text('Cháy ở Hầm xe'), findsOneWidget);
  });

  testWidgets('returning to the app re-reads the permission', (tester) async {
    final c = await _launch(tester);
    expect(
      await c.read(notificationPermissionProvider.future),
      NotificationPermission.granted,
    );
    _lifecycle(tester, _toBackground);
    _service(c).permission = NotificationPermission.denied;
    _lifecycle(tester, _toForeground);
    await tester.pump();
    expect(
      c.read(notificationPermissionProvider).value,
      NotificationPermission.denied,
    );
  });
}
