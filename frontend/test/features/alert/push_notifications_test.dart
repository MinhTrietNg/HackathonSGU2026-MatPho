import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mat_pho/app.dart';
import 'package:mat_pho/core/router/app_router.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_alert_repository.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_notification_service.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/models/fire_event.dart';
import 'package:mat_pho/data/models/incident.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/repositories/alert_repository.dart';
import 'package:mat_pho/data/remote/core/api_client.dart';
import 'package:mat_pho/data/remote/core/remote_providers.dart';
import 'package:mat_pho/data/services/notification_service.dart';
import 'package:mat_pho/data/services/push_inbox.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/cameras/camera_screen.dart';
import 'package:mat_pho/features/groups/current_group.dart';
import 'package:mat_pho/features/groups/group_routes.dart';
import 'package:mat_pho/features/groups/invitation_screen.dart';
import 'package:mat_pho/features/groups/members_screen.dart';

import '../../fakes/push_doubles.dart';
import '../../fakes/remote_doubles.dart';

final class _App {
  _App(this.container, this.push, this.tokens, this.requests, this.fetches);

  final ProviderContainer container;
  final FakePushMessageSource push;
  final FakePushTokenSource tokens;
  final List<http.Request> requests;

  final List<String> fetches;

  FakeNotificationService get notifications =>
      container.read(notificationServiceProvider) as FakeNotificationService;

  String get path => container.read(appRouterProvider).state.uri.path;

  List<Object?> get postedTokens => [
    for (final r in requests)
      if (r.url.path.endsWith('/users/me/fcm-tokens'))
        (jsonDecode(r.body) as Map)['fcm_token'],
  ];
}

Future<_App> _launch(
  WidgetTester tester, {
  Map<String, Object?>? launchedBy,
}) async {
  tester.view
    ..physicalSize = const Size(360, 780) * 2
    ..devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  final push = FakePushMessageSource()..initial = launchedBy;
  final tokens = FakePushTokenSource('fcm-1');
  final requests = <http.Request>[];
  final fetches = <String>[];
  final api = ApiClient(
    config: testApiConfig,
    tokens: FakeAuthTokenSource(token: 'id-1'),
    httpClient: MockClient((request) async {
      requests.add(request);
      return http.Response(
        '{"status":"success"}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }),
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(const FakeScenario.test()),
        pushMessageSourceProvider.overrideWithValue(push),
        pushTokenSourceProvider.overrideWithValue(tokens),
        apiClientProvider.overrideWithValue(api),
        alertRepositoryProvider.overrideWith(
          (ref) => _CountingAlerts(
            FakeAlertRepository(ref.watch(fakeWorldProvider)),
            fetches,
          ),
        ),
      ]),
      child: const MatPhoApp(),
    ),
  );
  await tester.pump(const Duration(seconds: 2));
  await tester.pumpAndSettle();
  final container = ProviderScope.containerOf(
    tester.element(find.byType(MatPhoApp)),
  );
  return _App(container, push, tokens, requests, fetches);
}

Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(seconds: 10));
  await tester.pumpAndSettle();
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

const _lostCameraId = 'cam-down';

FireEvent _newFire(_App app) {
  final alert = FakeData.fireAlert(id: 'evt-push');
  app.container.read(fakeWorldProvider).addEvent(alert);
  return alert;
}

Map<String, Object?> _fire(String id) => {
  'type': 'FIRE_ALERT',
  'alert_id': id,
  'escalation_level': '0',
};

void main() {
  testWidgets('the push token is posted on sign-in and refresh, not when '
      'signed out', (tester) async {
    final app = await _launch(tester);
    expect(app.postedTokens, ['fcm-1']);
    app.tokens.refresh('fcm-2');
    await tester.pump();
    expect(app.postedTokens, ['fcm-1', 'fcm-2']);

    app.container.read(authSessionProvider.notifier).signOut();
    await tester.pumpAndSettle();
    app.tokens.refresh('fcm-3');
    await tester.pump();
    expect(app.postedTokens, ['fcm-1', 'fcm-2']);

    app.container
        .read(authSessionProvider.notifier)
        .signIn(FakeData.user, newAccount: false);
    await tester.pump();
    expect(app.postedTokens, ['fcm-1', 'fcm-2', 'fcm-3']);
    await _settle(tester);
  });

  testWidgets('FIRE_ALERT in the foreground: the in-app alert is enough', (
    tester,
  ) async {
    final app = await _launch(tester);
    app.push.receive(_fire(FakeData.fireAlert().id));
    await _settle(tester);
    expect(app.notifications.shown, isEmpty);
  });

  testWidgets('FIRE_ALERT in the background: F1 with the fetched text, '
      '"Cảnh báo cháy" when the fetch fails', (tester) async {
    final app = await _launch(tester);
    _lifecycle(tester, _toBackground);
    final fire = _newFire(app);
    app.push
      ..receive(_fire(fire.id))
      ..receive(_fire('alt_unknown'));
    await tester.pump(const Duration(seconds: 1));
    expect(app.notifications.shown, [
      (title: 'Có cháy · Hầm xe', body: fireAlertBody(fire), eventId: fire.id),
      (
        title: 'Cảnh báo cháy',
        body: 'Chạm để xem ảnh.',
        eventId: 'alt_unknown',
      ),
    ]);
    _lifecycle(tester, _toForeground);
    await _settle(tester);
    expect(app.notifications.cleared, ['alt_unknown']);
    expect(app.path, AppRoutes.alert('alt_unknown'));
  });

  testWidgets('rung by the background handler: back in the app opens F2', (
    tester,
  ) async {
    final app = await _launch(tester);
    _lifecycle(tester, _toBackground);
    final fire = _newFire(app);
    app.push.handleInBackground(_fire(fire.id));
    await tester.pump();
    expect(app.notifications.shown, isEmpty);
    _lifecycle(tester, _toForeground);
    await _settle(tester);
    expect(app.notifications.cleared, [fire.id]);
    expect(find.text('Cháy ở Hầm xe'), findsOneWidget);
  });

  testWidgets('FIRE_ALERT_UPDATED stops the ringing and refetches its F2, '
      'which stays open', (tester) async {
    final app = await _launch(tester);
    final fire = _newFire(app);
    app.notifications.tap(fire.id);
    await _settle(tester);
    expect(find.text('Cháy ở Hầm xe'), findsOneWidget);
    app.notifications.cleared.clear();
    final loads = app.fetches.where((id) => id == fire.id).length;

    final world = app.container.read(fakeWorldProvider);
    world.replaceEvent(world.event(fire.id).copyWith(resolved: true));
    app.push.receive({
      'type': 'FIRE_ALERT_UPDATED',
      'alert_id': fire.id,
      'status': 'RESOLVED',
      'resolved_by_name': 'Chị Hoa',
    });
    await _settle(tester);
    expect(app.notifications.cleared, [fire.id]);
    expect(app.path, AppRoutes.alert(fire.id));
    expect(app.fetches.where((id) => id == fire.id).length, loads + 1);
  });

  testWidgets('FIRE_ALERT_UPDATED from the background handler: F2 turns into '
      '"Đã báo nhầm"', (tester) async {
    final app = await _launch(tester);
    final fire = _newFire(app);
    app.notifications.tap(fire.id);
    await _settle(tester);
    expect(find.text('Đã báo nhầm'), findsNothing);

    final world = app.container.read(fakeWorldProvider);
    world.replaceEvent(
      world.event(fire.id).copyWith(status: EventStatus.falseAlarm),
    );
    app.push.handleInBackground({
      'type': 'FIRE_ALERT_UPDATED',
      'alert_id': fire.id,
      'status': 'FALSE_ALARM',
    });
    await _settle(tester);
    expect(app.notifications.cleared, contains(fire.id));
    expect(app.path, AppRoutes.alert(fire.id));
    expect(find.text('Đã báo nhầm'), findsOneWidget);
  });

  testWidgets('a tap on a FIRE_ALERT push opens F2', (tester) async {
    final app = await _launch(tester);
    final fire = _newFire(app);
    app.push.open(_fire(fire.id));
    await _settle(tester);
    expect(app.path, AppRoutes.alert(fire.id));
    expect(find.text('Cháy ở Hầm xe'), findsOneWidget);
  });

  testWidgets('a tap on INVITATION opens J3', (tester) async {
    final app = await _launch(tester);
    const invitation = FakeData.invitation;
    app.push.open({
      'type': 'INVITATION',
      'group_id': invitation.groupId,
      'invitation_id': invitation.id,
    });
    await _settle(tester);
    expect(app.path, GroupRoutes.invitation(invitation.id));
    expect(find.byType(InvitationScreen), findsOneWidget);
  });

  testWidgets('a tap on ROLE_CHANGED opens J1 of that group', (tester) async {
    final app = await _launch(tester);
    final groups = await app.container.read(groupsProvider.future);
    final other = groups.lastWhere(
      (g) => g.id != app.container.read(currentGroupProvider).value?.id,
    );
    app.push.open({'type': 'ROLE_CHANGED', 'group_id': other.id});
    await _settle(tester);
    expect(app.path, GroupRoutes.members);
    expect(find.byType(MembersScreen), findsOneWidget);
    expect(app.container.read(currentGroupIdProvider), other.id);
  });

  testWidgets('a tap on CAMERA_OFFLINE opens I8', (tester) async {
    final app = await _launch(tester);
    app.push.open({'type': 'CAMERA_OFFLINE', 'cam_id': _lostCameraId});
    await _settle(tester);
    expect(app.path, AppRoutes.signalLost(_lostCameraId));
    expect(find.byType(CameraScreen), findsOneWidget);
  });

  testWidgets('a push whose notification launched the app opens its screen', (
    tester,
  ) async {
    final app = await _launch(
      tester,
      launchedBy: {'type': 'CAMERA_OFFLINE', 'cam_id': _lostCameraId},
    );
    await _settle(tester);
    expect(app.path, AppRoutes.signalLost(_lostCameraId));
  });
}

final class _CountingAlerts implements AlertRepository {
  _CountingAlerts(this._inner, this._fetches);

  final AlertRepository _inner;
  final List<String> _fetches;

  @override
  Future<FireEvent> getAlert(String eventId) {
    _fetches.add(eventId);
    return _inner.getAlert(eventId);
  }

  @override
  Stream<FireEvent> incomingAlerts() => _inner.incomingAlerts();

  @override
  Stream<AlertUpdate> alertUpdates() => _inner.alertUpdates();

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
