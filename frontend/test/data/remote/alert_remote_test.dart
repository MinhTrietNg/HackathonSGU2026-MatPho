import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/remote/alert_remote.dart';
import 'package:mat_pho/data/remote/core/api_client.dart';
import 'package:mat_pho/data/remote/core/json.dart';
import 'package:mat_pho/data/remote/core/ws_client.dart';

import '../../fakes/remote_doubles.dart';

Map<String, Object?> contractAlert() => {
  'alert_id': 'alt_1001',
  'cam_id': 'cam_charger',
  'cam_name': 'Hầm B1 · Khu sạc xe',
  'location_name': 'Hầm B1',
  'address': 'Hầm B1, chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7',
  'status': 'CONFIRMED',
  'sign': 'BOTH',
  'confidence': 0.93,
  'check_count': 2,
  'verification': 'VERIFIED',
  'summary': 'Lửa ở xe máy',
  'detail': 'Lửa và khói ở xe máy bên trái',
  'call_script': 'Cháy xe máy ở khu sạc hầm B1',
  'still_url': 'https://storage.googleapis.com/b/alt_1001.jpg',
  'detected_at': '2026-11-04T21:47:31.000Z',
  'called_114_at': '2026-11-04T21:48:10.000Z',
  'resolved_at': null,
  'resolved_by_name': null,
  'steps': {
    'DETECTED': '2026-11-04T21:47:31.000Z',
    'IMAGE_SENT': '2026-11-04T21:47:31.400Z',
    'AI_VERIFIED': '2026-11-04T21:47:36.100Z',
    'ALERT_TRIGGERED': '2026-11-04T21:47:37.800Z',
    'CALLED_114': '2026-11-04T21:48:10.000Z',
  },
  'timeline_snapshots': [
    {
      'url': 'https://storage.googleapis.com/b/t0.jpg',
      'bbox': [0.2, 0.3, 0.4, 0.6],
      'timestamp': '2026-11-04T21:47:31.000Z',
    },
  ],
};

Map<String, Object?> wsFireAlert({String verification = 'VERIFIED'}) => {
  'type': 'FIRE_ALERT',
  'alert_id': 'alt_1001',
  'cam_id': 'cam_charger',
  'cam_name': 'Hầm B1 · Khu sạc xe',
  'location_name': 'Hầm B1',
  'sign': 'BOTH',
  'confidence': 0.93,
  'verification': verification,
  'escalation_level': 0,
  'summary': 'Lửa ở xe máy',
  'detail': 'Lửa và khói ở xe máy bên trái',
  'still_url': 'https://storage.googleapis.com/b/alt_1001.jpg',
  'detected_at': '2026-11-04T12:00:00.000Z',
};

http.Response jsonResponse(Object? json, [int status = 200]) => http.Response(
  jsonEncode(json),
  status,
  headers: {'content-type': 'application/json'},
);

void main() {
  group('parseFireEvent', () {
    test('reads every field of the contract detail', () {
      final e = parseFireEvent(contractAlert());
      expect(e.id, 'alt_1001');
      expect(e.cameraId, 'cam_charger');
      expect(e.locationName, 'Hầm B1');
      expect(e.status, EventStatus.fire);
      expect(e.resolved, isFalse);
      expect(e.called114, isTrue);
      expect(e.detectedAt, DateTime.utc(2026, 11, 4, 21, 47, 31).toLocal());
      expect(e.detectedAt.isUtc, isFalse);
      expect(e.summary, 'Lửa ở xe máy');
      expect(e.detail, 'Lửa và khói ở xe máy bên trái');
      expect(e.sign, DetectedSign.fire);
      expect(e.confidence, 0.93);
      expect(e.checkCount, 2);
      expect(e.address, 'Hầm B1, chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7');
      expect(e.callScript, 'Cháy xe máy ở khu sạc hầm B1');
      expect(e.stillUrl, 'https://storage.googleapis.com/b/alt_1001.jpg');
      expect(e.resolvedByName, isNull);
    });

    test('steps: offsets from DETECTED, CALLED_114 dropped', () {
      final e = parseFireEvent(contractAlert());
      expect(e.timeline, const [
        TimelineStep(TimelineStepKind.detected, Duration.zero),
        TimelineStep(TimelineStepKind.imageSent, Duration(milliseconds: 400)),
        TimelineStep(
          TimelineStepKind.confirmedFire,
          Duration(milliseconds: 5100),
        ),
        TimelineStep(TimelineStepKind.notified, Duration(milliseconds: 6800)),
      ]);
      expect(e.notifyLatency, const Duration(milliseconds: 6800));
    });

    test('steps as a list of {step, at} read the same', () {
      final json = contractAlert()
        ..['steps'] = [
          {'step': 'DETECTED', 'at': '2026-11-04T21:47:31.000Z'},
          {'kind': 'IMAGE_SENT', 'at': '2026-11-04T21:47:31.400Z'},
          {'step': 'CALLED_114', 'at': '2026-11-04T21:48:10.000Z'},
        ];
      expect(parseFireEvent(json).timeline, const [
        TimelineStep(TimelineStepKind.detected, Duration.zero),
        TimelineStep(TimelineStepKind.imageSent, Duration(milliseconds: 400)),
      ]);
    });

    test('snapshots with their bbox [x1, y1, x2, y2]', () {
      final snap = parseFireEvent(contractAlert()).snapshots.single;
      expect(snap.url, 'https://storage.googleapis.com/b/t0.jpg');
      expect(snap.box, (left: 0.2, top: 0.3, right: 0.4, bottom: 0.6));
      expect(snap.takenAt, DateTime.utc(2026, 11, 4, 21, 47, 31).toLocal());
    });

    test('a bbox that is empty or in pixels draws no box', () {
      final json = contractAlert()
        ..['timeline_snapshots'] = [
          {'url': 'https://x/a.jpg', 'bbox': <Object?>[], 'timestamp': 'x'},
          {
            'url': 'https://x/b.jpg',
            'bbox': [120, 80, 300, 260],
          },
        ];
      final snaps = parseFireEvent(json).snapshots;
      expect(snaps.map((s) => s.box), [null, null]);
      expect(snaps.first.takenAt, isNull);
    });

    test('statuses and signs follow the translation table', () {
      FireEvent with_(Map<String, Object?> fields) =>
          parseFireEvent(contractAlert()..addAll(fields));

      final dismissed = with_({'verification': 'SUPPRESSED', 'steps': null});
      expect(dismissed.status, EventStatus.dismissed);
      expect(with_({'status': 'SUPPRESSED'}).status, EventStatus.dismissed);
      expect(
        with_({'verification': 'UNVERIFIED'}).status,
        EventStatus.unverified,
      );
      expect(with_({'status': 'FALSE_ALARM'}).status, EventStatus.falseAlarm);
      expect(
        with_({'status': 'FALSE_ALARM', 'verification': 'UNVERIFIED'}).status,
        EventStatus.falseAlarm,
      );
      final resolved = with_({
        'status': 'RESOLVED',
        'resolved_by_name': 'Nguyễn Minh Anh',
      });
      expect(resolved.status, EventStatus.fire);
      expect(resolved.resolved, isTrue);
      expect(resolved.resolvedByName, 'Nguyễn Minh Anh');
      expect(with_({'status': 'NEW'}).status, EventStatus.fire);
      expect(with_({'called_114_at': null}).called114, isFalse);

      expect(with_({'sign': 'FIRE'}).sign, DetectedSign.fire);
      expect(with_({'sign': 'SMOKE'}).sign, DetectedSign.smoke);
      expect(with_({'sign': 'BOTH'}).sign, DetectedSign.fire);
    });

    test('a dismissed event: "Xác nhận không cháy", then "Không báo"', () {
      final e = parseFireEvent(
        contractAlert()
          ..['verification'] = 'SUPPRESSED'
          ..['steps'] = {
            'DETECTED': '2026-11-04T21:47:31.000Z',
            'IMAGE_SENT': '2026-11-04T21:47:31.400Z',
            'AI_VERIFIED': '2026-11-04T21:47:35.600Z',
          },
      );
      expect(e.timeline, const [
        TimelineStep(TimelineStepKind.detected, Duration.zero),
        TimelineStep(TimelineStepKind.imageSent, Duration(milliseconds: 400)),
        TimelineStep(
          TimelineStepKind.confirmedNotFire,
          Duration(milliseconds: 4600),
        ),
        TimelineStep(TimelineStepKind.notNotified, null),
      ]);
    });

    test('a wrong shape is a ServerException naming the field', () {
      expect(
        () => parseFireEvent(contractAlert()..remove('alert_id')),
        throwsA(
          isA<ServerException>()
              .having((e) => e.code, 'code', badResponse)
              .having((e) => e.message, 'message', contains('alert_id')),
        ),
      );
      expect(
        () => parseFireEvent(contractAlert()..['detected_at'] = 'yesterday'),
        throwsA(isA<ServerException>()),
      );
    });
  });

  group('REST', () {
    late List<http.Request> requests;
    late Map<String, http.Response Function(http.Request)> routes;
    late RemoteAlertRepository repository;

    setUp(() {
      requests = [];
      routes = {
        'GET /api/v1/alerts/alt_1001': (_) => jsonResponse(contractAlert()),
      };
      final api = ApiClient(
        config: testApiConfig,
        tokens: FakeAuthTokenSource(token: 'tok-1'),
        httpClient: MockClient((request) async {
          requests.add(request);
          final route = routes['${request.method} ${request.url.path}'];
          return route?.call(request) ??
              jsonResponse({
                'error': {'code': 'NOT_FOUND'},
              }, 404);
        }),
      );
      repository = RemoteAlertRepository(
        api,
        WsClient(config: testApiConfig, tokens: FakeAuthTokenSource()),
      );
    });

    List<String> calls() => [
      for (final r in requests) '${r.method} ${r.url.path}',
    ];

    test('getAlert reads GET /alerts/{id}', () async {
      final e = await repository.getAlert('alt_1001');
      expect(e.id, 'alt_1001');
      expect(calls(), ['GET /api/v1/alerts/alt_1001']);
      expect(requests.single.headers['Authorization'], 'Bearer tok-1');
    });

    test('getAlert of an unknown alert is a ServerException', () async {
      await expectLater(
        repository.getAlert('alt_x'),
        throwsA(
          isA<ServerException>().having((e) => e.code, 'code', 'NOT_FOUND'),
        ),
      );
    });

    for (final (name, action, path) in [
      (
        'recordCall114',
        (RemoteAlertRepository r) => r.recordCall114('alt_1001'),
        'call-114',
      ),
      (
        'resolve',
        (RemoteAlertRepository r) => r.resolve('alt_1001'),
        'resolve',
      ),
      (
        'markFalseAlarm',
        (RemoteAlertRepository r) => r.markFalseAlarm('alt_1001'),
        'mark-false-alarm',
      ),
      (
        'reportRealFire',
        (RemoteAlertRepository r) => r.reportRealFire('alt_1001'),
        'report-real-fire',
      ),
    ]) {
      test('$name posts …/$path, then reads the alert', () async {
        routes['POST /api/v1/alerts/alt_1001/$path'] = (_) =>
            jsonResponse({'alert_id': 'alt_1001', 'status': 'CONFIRMED'});
        final e = await action(repository);
        expect(e.id, 'alt_1001');
        expect(calls(), [
          'POST /api/v1/alerts/alt_1001/$path',
          'GET /api/v1/alerts/alt_1001',
        ]);
      });
    }

    test('resolve sends a JSON body the router accepts', () async {
      routes['POST /api/v1/alerts/alt_1001/resolve'] = (_) =>
          jsonResponse({'alert_id': 'alt_1001', 'status': 'RESOLVED'});
      await repository.resolve('alt_1001');
      expect(jsonDecode(requests.first.body), <String, Object?>{});
    });

    for (final (name, path) in [
      ('resolve', 'resolve'),
      ('markFalseAlarm', 'mark-false-alarm'),
    ]) {
      test('$name by "Chỉ báo cháy": 403 → PermissionDenied', () async {
        routes['POST /api/v1/alerts/alt_1001/$path'] = (_) => jsonResponse({
          'error': {
            'code': 'PERMISSION_DENIED',
            'message': 'Người nhận tin (Notifier) không có quyền đóng sự cố.',
          },
        }, 403);
        final future = name == 'resolve'
            ? repository.resolve('alt_1001')
            : repository.markFalseAlarm('alt_1001');
        await expectLater(future, throwsA(isA<PermissionDeniedException>()));
        expect(calls(), ['POST /api/v1/alerts/alt_1001/$path']);
      });
    }
  });

  group('WebSocket', () {
    late WsClient ws;
    late FakeWsChannel channel;
    late RemoteAlertRepository repository;

    setUp(() async {
      final channels = <FakeWsChannel>[];
      ws = WsClient(
        config: testApiConfig,
        tokens: FakeAuthTokenSource(token: 'tok-1'),
        channelFactory: (uri, headers) {
          final c = FakeWsChannel(uri, headers);
          channels.add(c);
          return c;
        },
      )..connect();
      await pumpEventQueue();
      channel = channels.single..accept();
      await pumpEventQueue();
      repository = RemoteAlertRepository(
        ApiClient(
          config: testApiConfig,
          tokens: FakeAuthTokenSource(token: 'tok-1'),
          httpClient: MockClient((_) async => http.Response('', 500)),
        ),
        ws,
      );
    });

    tearDown(() => ws.dispose());

    void send(Map<String, Object?> json) =>
        channel.serverSends(jsonEncode(json));

    test('FIRE_ALERT: fire / unverified, each once per level', () async {
      final alerts = <FireEvent>[];
      final sub = repository.incomingAlerts().listen(alerts.add);
      send(wsFireAlert());
      send(wsFireAlert()..['escalation_level'] = 1);
      send({'type': 'FIRE_ALERT', 'alert_id': 'broken'});
      send(wsFireAlert(verification: 'UNVERIFIED')..['alert_id'] = 'alt_2');
      send({'type': 'CAMERA_HEARTBEAT', 'cam_id': 'cam_charger', 'fps': 5});
      await pumpEventQueue();
      await sub.cancel();

      expect(alerts.map((e) => (e.id, e.status)), [
        ('alt_1001', EventStatus.fire),
        ('alt_2', EventStatus.unverified),
      ]);
      final fire = alerts.first;
      expect(fire.cameraId, 'cam_charger');
      expect(fire.locationName, 'Hầm B1');
      expect(fire.summary, 'Lửa ở xe máy');
      expect(fire.stillUrl, 'https://storage.googleapis.com/b/alt_1001.jpg');
      expect(fire.detectedAt, DateTime.utc(2026, 11, 4, 12).toLocal());
    });

    test('each listener gets every alert', () async {
      final first = repository.incomingAlerts().first;
      final second = repository.incomingAlerts().first;
      send(wsFireAlert());
      expect((await first).id, 'alt_1001');
      expect((await second).id, 'alt_1001');
    });

    test(
      'FIRE_ALERT_UPDATED: RESOLVED / FALSE_ALARM; CONFIRMED left out',
      () async {
        final updates = <AlertUpdate>[];
        final sub = repository.alertUpdates().listen(updates.add);
        send({
          'type': 'FIRE_ALERT_UPDATED',
          'alert_id': 'alt_1001',
          'status': 'CONFIRMED',
          'escalation_level': 1,
          'resolved_by_name': null,
          'resolved_at': null,
        });
        send({
          'type': 'FIRE_ALERT_UPDATED',
          'alert_id': 'alt_1001',
          'status': 'RESOLVED',
          'escalation_level': 1,
          'resolved_by_name': 'Nguyễn Minh Anh',
          'resolved_at': '2026-11-04T12:05:00.000Z',
        });
        send({
          'type': 'FIRE_ALERT_UPDATED',
          'alert_id': 'alt_2',
          'status': 'FALSE_ALARM',
        });
        send({'type': 'FIRE_ALERT_UPDATED', 'status': 'RESOLVED'});
        await pumpEventQueue();
        await sub.cancel();

        expect(updates, const [
          AlertUpdate(
            eventId: 'alt_1001',
            outcome: AlertUpdateOutcome.resolved,
            resolvedByName: 'Nguyễn Minh Anh',
          ),
          AlertUpdate(eventId: 'alt_2', outcome: AlertUpdateOutcome.falseAlarm),
        ]);
      },
    );
  });

  group('escalation, dispatch, audit', () {
    late List<http.Request> requests;
    late Map<String, http.Response Function(http.Request)> routes;
    late RemoteAlertRepository repository;

    setUp(() {
      requests = [];
      routes = {};
      repository = RemoteAlertRepository(
        ApiClient(
          config: testApiConfig,
          tokens: FakeAuthTokenSource(token: 'tok-1'),
          httpClient: MockClient((request) async {
            requests.add(request);
            final route = routes['${request.method} ${request.url.path}'];
            return route?.call(request) ??
                jsonResponse({
                  'error': {'code': 'NOT_FOUND'},
                }, 404);
          }),
        ),
        WsClient(config: testApiConfig, tokens: FakeAuthTokenSource()),
      );
    });

    test('escalation-status: the 60 s timer still running', () async {
      routes['GET /api/v1/alerts/alt_1001/escalation-status'] = (_) =>
          jsonResponse({
            'alert_id': 'alt_1001',
            'group_id': 'grp_sky_garden_01',
            'status': 'NEW',
            'timer_active': true,
            'remaining_seconds': 42,
            'escalation_level': 0,
          });
      final s = await repository.escalationStatus('alt_1001');
      expect(
        s,
        const EscalationStatus(
          eventId: 'alt_1001',
          timerActive: true,
          remaining: Duration(seconds: 42),
          level: 0,
        ),
      );
    });

    test('escalation-status: stopped or escalated', () async {
      routes['GET /api/v1/alerts/alt_1001/escalation-status'] = (_) =>
          jsonResponse({
            'alert_id': 'alt_1001',
            'status': 'CONFIRMED',
            'timer_active': false,
            'remaining_seconds': 0,
            'escalation_level': 1,
          });
      final s = await repository.escalationStatus('alt_1001');
      expect(s.timerActive, isFalse);
      expect(s.remaining, Duration.zero);
      expect(s.level, 1);
    });

    test('dispatch-info: address, script and owner / managers', () async {
      routes['GET /api/v1/alerts/alt_1001/dispatch-info'] = (_) =>
          jsonResponse({
            'alert_id': 'alt_1001',
            'facility_name': 'Chung cư Sky Garden',
            'address': '12 Nguyễn Văn Linh, Q.7, TP.HCM',
            'location_name': 'Hầm B1',
            'cam_name': 'Hầm B1 · Khu sạc xe',
            'status': 'NEW',
            'call_script':
                'Báo cháy khẩn cấp tại: 12 Nguyễn Văn Linh, Q.7, TP.HCM, '
                'khu vực Hầm B1.',
            'emergency_contacts': [
              {
                'user_id': 'usr_lan',
                'full_name': 'Trần Thị Lan',
                'phone_number': '+84903112233',
                'role': 'LEADER',
              },
              {
                'user_id': 'usr_x',
                'full_name': 'Ai đó',
                'phone_number': '+84900000000',
                'role': 'SUPERVISOR',
              },
            ],
            'still_url': 'https://storage.googleapis.com/b/alt_1001.jpg',
            'detected_at': '2026-11-04T21:47:31.000Z',
            'called_114_at': 'None',
          });
      final d = await repository.dispatchInfo('alt_1001');
      expect(d.facilityName, 'Chung cư Sky Garden');
      expect(d.address, '12 Nguyễn Văn Linh, Q.7, TP.HCM');
      expect(d.locationName, 'Hầm B1');
      expect(d.cameraName, 'Hầm B1 · Khu sạc xe');
      expect(d.callScript, startsWith('Báo cháy khẩn cấp tại'));
      expect(d.contacts, const [
        EmergencyContact(
          userId: 'usr_lan',
          name: 'Trần Thị Lan',
          phone: '0903112233',
          role: GroupRole.owner,
        ),
      ]);
      expect(d.detectedAt, DateTime.utc(2026, 11, 4, 21, 47, 31).toLocal());
      expect(d.called114At, isNull);
    });

    test('audit-logs: items of the alert', () async {
      routes['GET /api/v1/alerts/alt_1001/audit-logs'] = (_) => jsonResponse({
        'alert_id': 'alt_1001',
        'items': [
          {
            'log_id': 'log_9',
            'action': 'ALERT_RESOLVED',
            'actor_id': 'usr_lan',
            'target_entity': 'alert:alt_1001',
            'details': {'note': 'Đã dập'},
            'created_at': '2026-11-04T21:50:00.000Z',
          },
        ],
        'total': 1,
      });
      final log = await repository.auditLog('alt_1001');
      expect(log.single.action, 'ALERT_RESOLVED');
      expect(log.single.target, 'alert:alt_1001');
      expect(log.single.createdAt, DateTime.utc(2026, 11, 4, 21, 50).toLocal());
    });

    test('an unknown alert is a ServerException', () async {
      await expectLater(
        repository.dispatchInfo('alt_x'),
        throwsA(
          isA<ServerException>().having((e) => e.code, 'code', 'NOT_FOUND'),
        ),
      );
    });
  });
}
