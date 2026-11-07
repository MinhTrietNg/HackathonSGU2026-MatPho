import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_notification_service.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/features/alert/pending_alert_actions.dart';
import 'package:mat_pho/features/auth/auth_routes.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/cameras/camera_state.dart';
import 'package:mat_pho/features/groups/current_group.dart';
import 'package:mat_pho/features/settings/settings_state.dart';

void main() {
  ProviderContainer container([Set<FakeCase> cases = const {}]) =>
      ProviderContainer.test(
        overrides: fakeOverrides([
          fakeScenarioProvider.overrideWithValue(
            FakeScenario.test(cases: cases),
          ),
        ]),
      );

  test("signing in as someone else drops the last account's state", () {
    final c = container();
    final auth = c.read(authSessionProvider.notifier)..signIn(FakeData.user);
    c
      ..listen(currentGroupIdProvider, (_, _) {})
      ..listen(addCameraProvider, (_, _) {});
    c.read(currentGroupIdProvider.notifier).select('g-office');
    c.read(addCameraProvider.notifier).setName('Cổng sau');

    auth.signIn(
      const User(id: 'u-other', fullName: 'Trần Văn Bình', phone: '0933222111'),
    );
    expect(c.read(currentGroupIdProvider), isNull);
    expect(c.read(addCameraProvider).name, isEmpty);
  });

  test('logout signs this phone out at once and stops fire alerts', () async {
    final c = container();
    final notifications =
        c.read(notificationServiceProvider) as FakeNotificationService;
    final auth = c.read(authSessionProvider.notifier)..signIn(FakeData.user);
    final done = auth.logout();
    expect(c.read(authSessionProvider), isA<SignedOut>());
    await done;
    expect(notifications.clears, 1);
  });

  test(
    'logout sends the alert actions still inside their undo window',
    () async {
      final c = container();
      final world = c.read(fakeWorldProvider)
        ..addEvent(FakeData.fireAlert(id: 'evt-a'))
        ..addEvent(FakeData.fireAlert(id: 'evt-b'));
      final auth = c.read(authSessionProvider.notifier)..signIn(FakeData.user);
      c.read(pendingAlertActionsProvider.notifier)
        ..schedule('evt-a', AlertOutcome.resolved)
        ..schedule('evt-b', AlertOutcome.falseAlarm);

      await auth.logout();
      expect(world.event('evt-a').resolved, isTrue);
      expect(world.event('evt-b').status, EventStatus.falseAlarm);
    },
  );

  test('H4 does not report "Ổn rồi" while notifications are off', () async {
    final c = container({FakeCase.notificationsDenied});
    c.listen(testAlertProvider, (_, _) {});
    await c.read(testAlertProvider.notifier).send();
    expect(c.read(testAlertProvider).error, isA<TestAlertBlocked>());
  });

  test('A1 opens only paths inside the app', () {
    expect(appPathOrNull('/history/evt-1'), '/history/evt-1');
    expect(appPathOrNull(null), isNull);
    expect(appPathOrNull('//evil.example/x'), isNull);
    expect(appPathOrNull('https://evil.example'), isNull);
    expect(appPathOrNull('history'), isNull);
  });
}
