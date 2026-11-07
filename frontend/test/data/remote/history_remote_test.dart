import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/fire_event.dart';
import 'package:mat_pho/data/remote/core/api_client.dart';
import 'package:mat_pho/data/remote/history_remote.dart';

import '../../fakes/remote_doubles.dart';

Map<String, Object?> item(
  String id, {
  required String detectedAt,
  String status = 'CONFIRMED',
  String verification = 'VERIFIED',
  String? called114At,
}) => {
  'alert_id': id,
  'cam_id': 'cam_charger',
  'cam_name': 'Hầm B1 · Khu sạc xe',
  'location_name': 'Hầm B1',
  'status': status,
  'sign': 'BOTH',
  'confidence': 0.93,
  'verification': verification,
  'summary': 'Lửa ở xe máy',
  'detail': 'Lửa và khói ở xe máy bên trái',
  'still_url': 'https://storage.googleapis.com/b/$id.jpg',
  'detected_at': detectedAt,
  'called_114_at': called114At,
  'resolved_at': null,
  'resolved_by_name': null,
};

http.Response jsonResponse(Object? json, [int status = 200]) => http.Response(
  jsonEncode(json),
  status,
  headers: {'content-type': 'application/json'},
);

void main() {
  late List<http.Request> requests;
  late http.Response Function(http.Request) reply;

  RemoteHistoryRepository repository({int maxPages = 10}) =>
      RemoteHistoryRepository(
        ApiClient(
          config: testApiConfig,
          tokens: FakeAuthTokenSource(token: 'tok-1'),
          httpClient: MockClient((request) async {
            requests.add(request);
            return reply(request);
          }),
        ),
        maxPages: maxPages,
        now: () => DateTime.utc(2026, 11, 4, 22),
      );

  setUp(() => requests = []);

  test('G1 asks GET /alerts with filter and limit 20', () async {
    reply = (_) => jsonResponse({'items': <Object?>[], 'next_cursor': null});
    for (final (filter, wire) in [
      (HistoryFilter.all, 'all'),
      (HistoryFilter.fire, 'fire'),
      (HistoryFilter.dismissed, 'dismissed'),
      (HistoryFilter.falseAlarm, 'false_alarm'),
    ]) {
      requests.clear();
      expect(await repository().list(filter: filter), isEmpty);
      final url = requests.single.url;
      expect(url.path, '/api/v1/alerts');
      expect(url.queryParameters, {'filter': wire, 'limit': '20'});
    }
  });

  test('pages are followed by next_cursor until there is none', () async {
    reply = (request) => switch (request.url.queryParameters['cursor']) {
      null => jsonResponse({
        'items': [
          item('alt_3', detectedAt: '2026-11-04T21:00:00.000Z'),
          item('alt_2', detectedAt: '2026-11-04T20:00:00.000Z'),
        ],
        'next_cursor': '2026-11-04T20:00:00+00:00',
      }),
      _ => jsonResponse({
        'items': [item('alt_1', detectedAt: '2026-11-03T08:00:00.000Z')],
        'next_cursor': null,
      }),
    };
    final rows = await repository().list();
    expect(rows.map((e) => e.id), ['alt_3', 'alt_2', 'alt_1']);
    expect(requests.map((r) => r.url.queryParameters['cursor']), [
      null,
      '2026-11-04T20:00:00+00:00',
    ]);
  });

  test('a server that ignores cursor stops after its first page', () async {
    reply = (_) => jsonResponse({
      'items': [item('alt_1', detectedAt: '2026-11-04T21:00:00.000Z')],
      'next_cursor': 'again',
    });
    expect((await repository().list()).map((e) => e.id), ['alt_1']);
    expect(requests, hasLength(2));
  });

  test('at most maxPages pages', () async {
    var n = 0;
    reply = (_) {
      n++;
      return jsonResponse({
        'items': [item('alt_$n', detectedAt: '2026-11-04T21:00:00.000Z')],
        'next_cursor': 'c$n',
      });
    };
    expect(await repository(maxPages: 3).list(), hasLength(3));
    expect(requests, hasLength(3));
  });

  test('rows: newest first, 30 days, chip statuses, translated', () async {
    reply = (_) => jsonResponse({
      'items': [
        item('old', detectedAt: '2026-09-01T10:00:00.000Z'),
        item(
          'unverified',
          detectedAt: '2026-11-04T19:00:00.000Z',
          status: 'NEW',
          verification: 'UNVERIFIED',
        ),
        item(
          'called',
          detectedAt: '2026-11-04T21:00:00.000Z',
          status: 'RESOLVED',
          called114At: '2026-11-04T21:01:00.000Z',
        ),
      ],
      'next_cursor': null,
    });
    final all = await repository().list();
    expect(all.map((e) => e.id), ['called', 'unverified']);
    expect(all.first.status, EventStatus.fire);
    expect(all.first.resolved, isTrue);
    expect(all.first.called114, isTrue);
    expect(all.first.stillUrl, 'https://storage.googleapis.com/b/called.jpg');
    expect(all.last.status, EventStatus.unverified);

    final fire = await repository().list(filter: HistoryFilter.fire);
    expect(fire.map((e) => e.id), ['called']);
  });

  test('detail reads GET /alerts/{id} with steps and snapshots', () async {
    reply = (_) => jsonResponse({
      ...item('alt_1001', detectedAt: '2026-11-04T21:47:31.000Z'),
      'check_count': 2,
      'steps': {
        'DETECTED': '2026-11-04T21:47:31.000Z',
        'ALERT_TRIGGERED': '2026-11-04T21:47:37.800Z',
      },
      'timeline_snapshots': [
        {
          'url': 'https://storage.googleapis.com/b/t0.jpg',
          'bbox': [0.2, 0.3, 0.4, 0.6],
          'timestamp': '2026-11-04T21:47:31.000Z',
        },
      ],
    });
    final e = await repository().detail('alt_1001');
    expect(requests.single.url.path, '/api/v1/alerts/alt_1001');
    expect(
      e.timeline.last,
      const TimelineStep(
        TimelineStepKind.notified,
        Duration(milliseconds: 6800),
      ),
    );
    expect(e.snapshots.single.box, (
      left: 0.2,
      top: 0.3,
      right: 0.4,
      bottom: 0.6,
    ));
  });

  test('5xx → ServerException (G8), wrong shape too', () async {
    reply = (_) => http.Response('oops', 503);
    await expectLater(repository().list(), throwsA(isA<ServerException>()));
    reply = (_) => jsonResponse({'items': 'nope'});
    await expectLater(repository().list(), throwsA(isA<ServerException>()));
  });
}
