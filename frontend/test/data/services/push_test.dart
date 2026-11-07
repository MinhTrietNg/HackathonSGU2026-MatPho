import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mat_pho/data/errors.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_notification_service.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/models/fire_event.dart';
import 'package:mat_pho/data/remote/core/api_client.dart';
import 'package:mat_pho/data/services/notification_service.dart';
import 'package:mat_pho/data/services/push_background.dart';
import 'package:mat_pho/data/services/push_inbox.dart';
import 'package:mat_pho/data/services/push_message.dart';
import 'package:mat_pho/data/services/push_token_registrar.dart';

import '../../fakes/push_doubles.dart';
import '../../fakes/remote_doubles.dart';

const fireAlertData = {
  'type': 'FIRE_ALERT',
  'alert_id': 'alt_1001',
  'escalation_level': '1',
};
const fireAlertUpdatedData = {
  'type': 'FIRE_ALERT_UPDATED',
  'alert_id': 'alt_1001',
  'status': 'RESOLVED',
  'resolved_by_name': 'Nguyễn Minh Anh',
};
const testAlertData = {'type': 'TEST_ALERT', 'test_id': 'test_1a2b3c4d'};
const invitationData = {
  'type': 'INVITATION',
  'group_id': 'grp_riverside',
  'invitation_id': 'inv_9001',
};
const roleChangedData = {'type': 'ROLE_CHANGED', 'group_id': 'grp_riverside'};
const cameraOfflineData = {'type': 'CAMERA_OFFLINE', 'cam_id': 'cam_charger'};

void main() {
  group('PushMessage.decode', () {
    test('reads the six data messages', () {
      expect(
        PushMessage.decode(fireAlertData),
        const FireAlertPush(alertId: 'alt_1001', escalationLevel: 1),
      );
      expect(
        PushMessage.decode(fireAlertUpdatedData),
        const FireAlertUpdatedPush(
          alertId: 'alt_1001',
          status: 'RESOLVED',
          resolvedByName: 'Nguyễn Minh Anh',
        ),
      );
      expect(
        PushMessage.decode(testAlertData),
        const TestAlertPush(testId: 'test_1a2b3c4d'),
      );
      expect(
        PushMessage.decode(invitationData),
        const InvitationPush(
          groupId: 'grp_riverside',
          invitationId: 'inv_9001',
        ),
      );
      expect(
        PushMessage.decode(roleChangedData),
        const RoleChangedPush(groupId: 'grp_riverside'),
      );
      expect(
        PushMessage.decode(cameraOfflineData),
        const CameraOfflinePush(cameraId: 'cam_charger'),
      );
    });

    test('optional fields: level 0 by default, empty name is none', () {
      expect(
        PushMessage.decode({'type': 'FIRE_ALERT', 'alert_id': 'a'}),
        const FireAlertPush(alertId: 'a'),
      );
      expect(
        PushMessage.decode({
          'type': 'FIRE_ALERT_UPDATED',
          'alert_id': 'a',
          'status': 'FALSE_ALARM',
          'resolved_by_name': '',
        }),
        const FireAlertUpdatedPush(alertId: 'a', status: 'FALSE_ALARM'),
      );
    });

    test('unknown types and missing fields are no message', () {
      expect(PushMessage.decode({}), isNull);
      expect(PushMessage.decode({'type': 'AI_DISMISSED'}), isNull);
      expect(PushMessage.decode({'type': 'FIRE_ALERT'}), isNull);
      expect(
        PushMessage.decode({'type': 'FIRE_ALERT', 'alert_id': ''}),
        isNull,
      );
      expect(
        PushMessage.decode({'type': 'INVITATION', 'group_id': 'g'}),
        isNull,
      );
      expect(PushMessage.decode({'type': 'CAMERA_OFFLINE'}), isNull);
    });
  });

  group('PushInbox', () {
    test('decodes each stream and drops what does not decode', () async {
      final source = FakePushMessageSource();
      final inbox = PushInbox(source);
      addTearDown(inbox.dispose);
      final received = <PushMessage>[];
      final background = <PushMessage>[];
      final opened = <PushMessage>[];
      inbox.received.listen(received.add);
      inbox.handledInBackground.listen(background.add);
      inbox.opened.listen(opened.add);
      source
        ..receive(fireAlertData)
        ..receive({'type': 'UNKNOWN'})
        ..handleInBackground(fireAlertUpdatedData)
        ..open(invitationData);
      await pumpEventQueue();
      expect(received, [PushMessage.decode(fireAlertData)]);
      expect(background, [PushMessage.decode(fireAlertUpdatedData)]);
      expect(opened, [PushMessage.decode(invitationData)]);
    });

    test('TEST_ALERT emits on testAlertPushes (H4)', () async {
      final source = FakePushMessageSource();
      final inbox = PushInbox(source);
      addTearDown(inbox.dispose);
      var count = 0;
      final sub = inbox.testAlertPushes.listen((_) => count++);
      addTearDown(sub.cancel);
      source
        ..receive(fireAlertData)
        ..receive(testAlertData)
        ..handleInBackground(testAlertData)
        ..open(testAlertData);
      await pumpEventQueue();
      expect(count, 2);
    });

    test('the push that launched the app', () async {
      final source = FakePushMessageSource()..initial = cameraOfflineData;
      final inbox = PushInbox(source);
      addTearDown(inbox.dispose);
      expect(
        await inbox.initialOpened(),
        const CameraOfflinePush(cameraId: 'cam_charger'),
      );
    });
  });

  group('PushTokenRegistrar', () {
    late List<http.Request> requests;
    late int status;
    late FakePushTokenSource tokens;
    late PushTokenRegistrar registrar;

    setUp(() {
      requests = [];
      status = 200;
      tokens = FakePushTokenSource('fcm-1');
      final api = ApiClient(
        config: testApiConfig,
        tokens: FakeAuthTokenSource(token: 'id-1'),
        httpClient: MockClient((request) async {
          requests.add(request);
          return http.Response(
            jsonEncode({
              'status': 'success',
              'message': 'FCM token đã được cập nhật',
            }),
            status,
            headers: {'content-type': 'application/json'},
          );
        }),
      );
      registrar = PushTokenRegistrar(api: api, tokens: tokens);
      addTearDown(registrar.stop);
    });

    List<Object?> sent() => [
      for (final r in requests)
        (r.method, r.url.path, (jsonDecode(r.body) as Map)['fcm_token']),
    ];

    test('posts the token on sign-in and on every refresh', () async {
      await registrar.start();
      tokens.refresh('fcm-2');
      await pumpEventQueue();
      expect(sent(), [
        ('POST', '/api/v1/users/me/fcm-tokens', 'fcm-1'),
        ('POST', '/api/v1/users/me/fcm-tokens', 'fcm-2'),
      ]);
      expect(requests.first.headers['authorization'], 'Bearer id-1');
    });

    test('nothing once signed out, nothing without a token', () async {
      await registrar.start();
      registrar.stop();
      tokens.refresh('fcm-2');
      await pumpEventQueue();
      expect(sent(), [('POST', '/api/v1/users/me/fcm-tokens', 'fcm-1')]);

      requests.clear();
      tokens.current = null;
      await registrar.start();
      expect(requests, isEmpty);
    });

    test('a failed post does not throw and the next refresh retries', () async {
      status = 503;
      await registrar.start();
      status = 200;
      tokens.refresh('fcm-2');
      await pumpEventQueue();
      expect(sent().length, 2);
    });
  });

  group('background push', () {
    late FakeNotificationService notifications;
    late List<Map<String, String>> relayed;

    setUp(() {
      notifications = FakeNotificationService(const FakeScenario.test());
      relayed = [];
    });

    Future<void> handle(
      Map<String, Object?> data, {
      GetAlertRepository? alerts,
      bool signedIn = true,
    }) => handleBackgroundPush(
      data,
      notifications: notifications,
      alerts: alerts,
      signedIn: () async => signedIn,
      relay: relayed.add,
    );

    test('FIRE_ALERT: F1 with the text of GET /alerts/{id}', () async {
      final fire = FakeData.fireAlert(id: 'alt_1001');
      final smoke = FakeData.unverifiedEvent(id: 'alt_1002');
      final alerts = GetAlertRepository(
        events: {fire.id: fire, smoke.id: smoke},
      );
      await handle(fireAlertData, alerts: alerts);
      await handle({...fireAlertData, 'alert_id': 'alt_1002'}, alerts: alerts);
      expect(alerts.fetched, ['alt_1001', 'alt_1002']);
      expect(notifications.shown, [
        (
          title: 'Có cháy · Hầm xe',
          body: fireAlertBody(fire),
          eventId: 'alt_1001',
        ),
        (
          title: 'Có thể có khói ở Hầm xe',
          body: 'Chưa kiểm tra lại được. Chạm để xem ảnh.',
          eventId: 'alt_1002',
        ),
      ]);
      expect(relayed, [
        fireAlertData,
        {...fireAlertData, 'alert_id': 'alt_1002'},
      ]);
    });

    test('FIRE_ALERT: fetch fails → "Cảnh báo cháy" (#75)', () async {
      await handle(
        fireAlertData,
        alerts: GetAlertRepository(error: const NetworkException()),
      );
      await handle({...fireAlertData, 'alert_id': 'alt_2'});
      expect(notifications.shown, [
        (title: 'Cảnh báo cháy', body: 'Chạm để xem ảnh.', eventId: 'alt_1001'),
        (title: 'Cảnh báo cháy', body: 'Chạm để xem ảnh.', eventId: 'alt_2'),
      ]);
    });

    test('FIRE_ALERT: a slow fetch times out to the generic alert', () async {
      final never = _NeverAlerts();
      await showPushedFireAlert(
        'alt_1001',
        notifications: notifications,
        alerts: never,
        timeout: const Duration(milliseconds: 10),
      );
      expect(notifications.shown.single.title, genericFireAlertTitle);
    });

    test('FIRE_ALERT: no ring when signed out or already closed', () async {
      final fire = FakeData.fireAlert(id: 'alt_1001');
      await handle(
        fireAlertData,
        alerts: GetAlertRepository(events: {fire.id: fire}),
        signedIn: false,
      );
      await handle(
        fireAlertData,
        alerts: GetAlertRepository(
          events: {fire.id: fire.copyWith(resolved: true)},
        ),
      );
      await handle(
        fireAlertData,
        alerts: GetAlertRepository(
          events: {fire.id: fire.copyWith(status: EventStatus.falseAlarm)},
        ),
      );
      expect(notifications.shown, isEmpty);
    });

    test('FIRE_ALERT_UPDATED stops that alert only', () async {
      await handle(fireAlertUpdatedData);
      expect(notifications.cleared, ['alt_1001']);
      expect(notifications.clears, 0);
      expect(relayed, [fireAlertUpdatedData]);
    });

    test('the other pushes show nothing and are relayed', () async {
      for (final data in [
        testAlertData,
        invitationData,
        roleChangedData,
        cameraOfflineData,
      ]) {
        await handle(data);
      }
      await handle({'type': 'UNKNOWN'});
      expect(notifications.shown, isEmpty);
      expect(relayed, [
        testAlertData,
        invitationData,
        roleChangedData,
        cameraOfflineData,
      ]);
    });
  });
}

final class _NeverAlerts extends GetAlertRepository {
  @override
  Future<FireEvent> getAlert(String eventId) => Completer<FireEvent>().future;
}
