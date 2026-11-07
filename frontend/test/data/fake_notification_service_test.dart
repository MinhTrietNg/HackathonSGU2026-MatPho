import 'package:flutter_test/flutter_test.dart';
import '../fakes/fake_data.dart';
import '../fakes/fake_notification_service.dart';
import '../fakes/fake_scenario.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/services/notification_service.dart';

FakeNotificationService service([
  Set<FakeCase> cases = const {},
  bool grantOnRequest = true,
]) => FakeNotificationService(
  FakeScenario.test(cases: cases),
  grantOnRequest: grantOnRequest,
);

void main() {
  test('permission: granted by default, C1 and C3 cases', () async {
    expect(await service().status(), NotificationPermission.granted);
    expect(
      await service({FakeCase.notificationsNotDetermined}).status(),
      NotificationPermission.notDetermined,
    );
    expect(
      await service({FakeCase.notificationsDenied}).status(),
      NotificationPermission.denied,
    );
  });

  test('request grants, or plays "Don\'t allow"', () async {
    final c1 = service({FakeCase.notificationsNotDetermined});
    expect(await c1.request(), NotificationPermission.granted);
    expect(await c1.status(), NotificationPermission.granted);

    final refusing = service({FakeCase.notificationsNotDetermined}, false);
    expect(await refusing.request(), NotificationPermission.denied);
  });

  test('system settings: the user turns notifications on', () async {
    final c3 = service({FakeCase.notificationsDenied});
    await c3.openSystemSettings();
    expect(await c3.status(), NotificationPermission.granted);
  });

  test('records fire and test alerts, plays taps', () async {
    final s = service();
    final alert = FakeData.fireAlert(
      id: 'evt-9',
      cameraId: FakeData.fireCameraId,
      detectedAt: FakeData.demoNow,
    );
    await s.showFireAlert(alert);
    await s.showTestAlert();
    expect(s.shown, [
      (
        title: fireAlertTitle(alert),
        body: fireAlertBody(alert),
        eventId: 'evt-9',
      ),
      (title: testAlertTitle, body: testAlertBody, eventId: null),
    ]);

    final taps = s.taps.take(2).toList();
    s
      ..tap('evt-9')
      ..tap('evt-9', call114: true);
    expect(await taps, [
      (eventId: 'evt-9', call114: false),
      (eventId: 'evt-9', call114: true),
    ]);
  });

  test('F1 copy: "Có cháy · Hầm xe", "Phát hiện lửa lúc 21:47…"', () {
    final alert = FakeData.fireAlert(
      detectedAt: DateTime(2025, 10, 23, 21, 47),
    );
    expect(fireAlertTitle(alert), 'Có cháy · Hầm xe');
    expect(fireAlertBody(alert), 'Phát hiện lửa lúc 21:47. Chạm để xem ảnh.');
  });
}
