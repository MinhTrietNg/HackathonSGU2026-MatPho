import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/remote/core/api_client.dart';
import 'package:mat_pho/data/remote/core/ws_client.dart';
import 'package:mat_pho/data/remote/detection_remote.dart';

import '../../fakes/remote_doubles.dart';
import 'alert_remote_test.dart' show contractAlert, wsFireAlert;

const _camera = Camera(
  id: 'cam_charger',
  groupId: 'grp_1',
  name: 'Khu sạc xe',
  rtspUrl: 'rtsp://cam.test/stream',
);

Map<String, Object?> verifying(
  List<(String, String)> steps, {
  String sign = 'SMOKE',
  double confidence = 0.61,
  String cam = 'cam_charger',
}) => {
  'type': 'AI_VERIFYING',
  'cam_id': cam,
  'sign': sign,
  'confidence': confidence,
  'message': 'Đang xác minh dấu hiệu ngọn lửa...',
  'steps': [
    for (final (kind, at) in steps) {'step': kind, 'name': kind, 'at': at},
  ],
};

const _t0 = '2026-11-04T12:00:00.000Z';
const _t04 = '2026-11-04T12:00:00.400Z';
const _t51 = '2026-11-04T12:00:05.100Z';

void main() {
  late List<FakeWsChannel> channels;
  late WsClient ws;
  late List<http.Request> requests;
  late RemoteDetectionRepository repository;
  late List<DetectionState> states;
  late bool done;

  Future<FakeWsChannel> channel(int index) async {
    for (var i = 0; channels.length <= index; i++) {
      if (i > 500) fail('channel $index never opened');
      await Future<void>.delayed(const Duration(milliseconds: 1));
    }
    return channels[index];
  }

  setUp(() async {
    channels = [];
    requests = [];
    states = [];
    done = false;
    final tokens = FakeAuthTokenSource(token: 'tok-1');
    ws = WsClient(
      config: testApiConfig,
      tokens: tokens,
      minBackoff: const Duration(milliseconds: 1),
      maxBackoff: const Duration(milliseconds: 2),
      channelFactory: (uri, headers) {
        final c = FakeWsChannel(uri, headers);
        channels.add(c);
        return c;
      },
    );
    repository = RemoteDetectionRepository(
      ApiClient(
        config: testApiConfig,
        tokens: tokens,
        httpClient: MockClient((request) async {
          requests.add(request);
          if (request.url.path == '/api/v1/alerts/alt_1001') {
            return http.Response(
              jsonEncode(contractAlert()),
              200,
              headers: {'content-type': 'application/json'},
            );
          }
          return http.Response('', 204);
        }),
      ),
      ws,
      openAlertAfter: Duration.zero,
      dismissToast: const Duration(milliseconds: 20),
    );
  });

  tearDown(() async {
    await repository.stop();
    await ws.dispose();
  });

  Future<FakeWsChannel> connect() async {
    ws.connect();
    final c = await channel(channels.length);
    c.accept();
    await pumpEventQueue();
    return c;
  }

  void watch() =>
      repository.start(_camera).listen(states.add, onDone: () => done = true);

  void send(FakeWsChannel c, Map<String, Object?> json) =>
      c.serverSends(jsonEncode(json));

  test('connected: Watching, heartbeat sets the fps', () async {
    final c = await connect();
    watch();
    send(c, {
      'type': 'CAMERA_HEARTBEAT',
      'cam_id': 'cam_charger',
      'status': 'ONLINE',
      'ai_status': 'SCANNING',
      'fps': 3,
    });
    await pumpEventQueue();
    expect(states, const [DetectionWatching(), DetectionWatching(fps: 3)]);
  });

  test('messages of another camera are ignored', () async {
    final c = await connect();
    watch();
    send(c, {'type': 'CAMERA_HEARTBEAT', 'cam_id': 'cam_other', 'fps': 2});
    send(c, verifying([('DETECTED', _t0)], cam: 'cam_other'));
    send(c, wsFireAlert()..['cam_id'] = 'cam_other');
    await pumpEventQueue();
    expect(states, const [DetectionWatching()]);
  });

  test('AI_VERIFYING: steps grow, AI_VERIFIED brings the verdict', () async {
    final c = await connect();
    watch();
    send(c, verifying([('DETECTED', _t0)]));
    send(c, verifying([('DETECTED', _t0), ('IMAGE_SENT', _t04)]));
    send(
      c,
      verifying(
        [('DETECTED', _t0), ('IMAGE_SENT', _t04), ('AI_VERIFIED', _t51)],
        sign: 'FIRE',
        confidence: 0.93,
      ),
    );
    await pumpEventQueue();

    final [_, a, b, c2] = states;
    final detectedAt = DateTime.utc(2026, 11, 4, 12).toLocal();
    final suspect = SuspectFrame(
      sign: DetectedSign.smoke,
      confidence: 0.61,
      detectedAt: detectedAt,
    );
    expect(
      a,
      DetectionVerifying(
        suspect: suspect,
        steps: const [TimelineStep(TimelineStepKind.detected, Duration.zero)],
      ),
    );
    expect((a as DetectionVerifying).awaitingVerdict, isTrue);
    expect(
      (b as DetectionVerifying).steps.last,
      const TimelineStep(
        TimelineStepKind.imageSent,
        Duration(milliseconds: 400),
      ),
    );
    expect(
      c2,
      DetectionVerifying(
        suspect: suspect,
        steps: const [
          TimelineStep(TimelineStepKind.detected, Duration.zero),
          TimelineStep(TimelineStepKind.imageSent, Duration(milliseconds: 400)),
          TimelineStep(
            TimelineStepKind.confirmedFire,
            Duration(milliseconds: 5100),
          ),
        ],
        verdict: SuspectFrame(
          sign: DetectedSign.fire,
          confidence: 0.93,
          detectedAt: detectedAt,
        ),
      ),
    );
  });

  test('FIRE_ALERT VERIFIED: E2d with the full alert, then F2', () async {
    final c = await connect();
    watch();
    send(c, verifying([('DETECTED', _t0)]));
    send(c, wsFireAlert());
    await pumpEventQueue(times: 50);

    final notified = states.whereType<DetectionNotified>().toList();
    expect(notified.map((s) => s.openAlert), [false, true]);
    final alert = notified.first.alert;
    expect(alert.id, 'alt_1001');
    expect(alert.notifyLatency, const Duration(milliseconds: 6800));
    expect(requests.single.url.path, '/api/v1/alerts/alt_1001');
    expect(done, isTrue);
  });

  test('FIRE_ALERT UNVERIFIED: F4 at once, the session ends', () async {
    final c = await connect();
    watch();
    send(c, wsFireAlert(verification: 'UNVERIFIED'));
    await pumpEventQueue();
    expect(states.last, isA<DetectionUnverified>());
    expect(
      (states.last as DetectionUnverified).alert.status,
      EventStatus.unverified,
    );
    expect(done, isTrue);
    expect(requests, isEmpty);
  });

  test('FIRE_ALERT_SUPPRESSED: E4 with the detail, then Watching', () async {
    final c = await connect();
    watch();
    send(c, verifying([('DETECTED', _t0)]));
    send(c, {
      'type': 'FIRE_ALERT_SUPPRESSED',
      'alert_id': 'alt_1001',
      'cam_id': 'cam_charger',
      'summary': 'Không phải cháy',
      'detail': 'Chỉ là đèn xe chiếu lên tường.',
    });
    await pumpEventQueue();
    final dismissed = states.last as DetectionDismissed;
    expect(dismissed.reason.explanation, 'Chỉ là đèn xe chiếu lên tường.');
    expect(dismissed.event.id, 'alt_1001');
    expect(dismissed.event.status, EventStatus.dismissed);

    send(c, {'type': 'CAMERA_HEARTBEAT', 'cam_id': 'cam_charger', 'fps': 5});
    await pumpEventQueue();
    expect(states.last, isA<DetectionDismissed>());

    await Future<void>.delayed(const Duration(milliseconds: 40));
    expect(states.last, const DetectionWatching());
    expect(done, isFalse);
  });

  test('socket down → Offline (E5); back → Watching', () async {
    final c = await connect();
    watch();
    send(c, verifying([('DETECTED', _t0)]));
    await pumpEventQueue();
    c.serverCloses();
    await pumpEventQueue();
    expect(states.last, const DetectionOffline());

    (await channel(1)).accept();
    await pumpEventQueue();
    expect(states.last, const DetectionWatching());
  });

  test('not connected yet: starts in Offline', () async {
    watch();
    await pumpEventQueue();
    expect(states, const [DetectionOffline()]);
  });

  test('"Bỏ qua" posts the dismissal and goes back to Watching', () async {
    final c = await connect();
    watch();
    send(c, verifying([('DETECTED', _t0)]));
    await pumpEventQueue();
    await repository.dismissSuspect();
    expect(states.last, const DetectionWatching());
    expect(requests.single.method, 'POST');
    expect(
      requests.single.url.path,
      '/api/v1/cameras/cam_charger/suspect/dismiss',
    );

    send(c, verifying([('DETECTED', _t0), ('IMAGE_SENT', _t04)]));
    await pumpEventQueue();
    expect(states.last, const DetectionWatching());
  });

  test('"Bỏ qua" without a suspect does nothing', () async {
    await connect();
    watch();
    await pumpEventQueue();
    await repository.dismissSuspect();
    expect(requests, isEmpty);
  });

  test('stop closes the stream; start again ends the last session', () async {
    final c = await connect();
    watch();
    await pumpEventQueue();
    final second = <DetectionState>[];
    repository.start(_camera).listen(second.add);
    await pumpEventQueue();
    expect(done, isTrue);
    send(c, {'type': 'CAMERA_HEARTBEAT', 'cam_id': 'cam_charger', 'fps': 2});
    await pumpEventQueue();
    expect(second.last, const DetectionWatching(fps: 2));
  });
}
