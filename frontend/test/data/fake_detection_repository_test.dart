import 'package:flutter_test/flutter_test.dart';
import '../fakes/fake_alert_repository.dart';
import '../fakes/fake_data.dart';
import '../fakes/fake_detection_repository.dart';
import '../fakes/fake_history_repository.dart';
import '../fakes/fake_scenario.dart';
import '../fakes/fake_world.dart';
import 'package:mat_pho/data/models/models.dart';

FakeWorld world([Set<FakeCase> cases = const {}]) =>
    FakeWorld(FakeScenario.test(cases: cases));

Camera fixture(String id) => FakeData.cameras.firstWhere((c) => c.id == id);

final fireCamera = fixture(FakeData.fireCameraId);

final otherCamera = fixture('cam-ramp');

const newCamera = Camera(
  id: 'cam-new',
  groupId: 'g-sky',
  areaId: 'a-b1',
  name: 'Cửa hầm',
  rtspUrl: FakeData.rtspExample,
);

List<TimelineStepKind> kinds(DetectionState s) =>
    (s as DetectionVerifying).steps.map((step) => step.kind).toList();

void main() {
  test('fire camera: E2 → E2a → E2b → E2c → E2d → F2', () async {
    final w = world();
    final states = await FakeDetectionRepository(w).start(fireCamera).toList();

    expect(states.map((s) => s.runtimeType), [
      DetectionWatching,
      DetectionVerifying,
      DetectionVerifying,
      DetectionVerifying,
      DetectionNotified,
      DetectionNotified,
    ]);
    expect((states[0] as DetectionWatching).fps, 5);

    final e2a = states[1] as DetectionVerifying;
    expect(e2a.suspect.sign, DetectedSign.smoke);
    expect(e2a.suspect.confidence, 0.61);
    expect(kinds(e2a), [TimelineStepKind.detected]);
    expect(e2a.steps.single.offset, Duration.zero);
    expect(e2a.awaitingVerdict, isTrue);

    final e2b = states[2] as DetectionVerifying;
    expect(kinds(e2b), [TimelineStepKind.detected, TimelineStepKind.imageSent]);
    expect(e2b.steps.last.offset, const Duration(milliseconds: 400));
    expect(e2b.awaitingVerdict, isTrue);

    final e2c = states[3] as DetectionVerifying;
    expect(kinds(e2c).last, TimelineStepKind.confirmedFire);
    expect(e2c.steps.last.offset, const Duration(milliseconds: 5100));
    expect(e2c.verdict!.sign, DetectedSign.fire);
    expect(e2c.verdict!.confidence, 0.93);
    expect(e2c.awaitingVerdict, isFalse);

    final e2d = states[4] as DetectionNotified;
    expect(e2d.openAlert, isFalse);
    final alert = e2d.alert;
    expect(alert.status, EventStatus.fire);
    expect(alert.confidence, 0.93);
    expect(alert.cameraId, 'cam-charger');
    expect(alert.locationName, 'Hầm xe');
    expect(alert.summary, 'Lửa ở xe máy');
    expect(alert.notifyLatency, const Duration(milliseconds: 6800));
    expect(alert.notifyLatency! < alertLatencyGoal, isTrue);
    final open = states[5] as DetectionNotified;
    expect(open.openAlert, isTrue);
    expect(open.alert.id, alert.id);
  });

  test('confirmation lands within the 3–8 s verification window', () {
    final confirmed = FakeData.fireConfirmedAfter;
    expect(confirmed >= verifyTypicalMin, isTrue);
    expect(confirmed <= verifyTypicalMax, isTrue);
    expect(
      FakeData.notFireConfirmedAfter >= verifyTypicalMin &&
          FakeData.notFireConfirmedAfter <= verifyTypicalMax,
      isTrue,
    );
  });

  test('F2 opens 1,5 s after E2d (scaled)', () async {
    final repo = FakeDetectionRepository(
      FakeWorld(const FakeScenario(timeScale: 0.01, freezeClock: true)),
    );
    final at = <String, DateTime>{};
    await repo.start(fireCamera).forEach((s) {
      if (s is DetectionNotified) {
        at[s.openAlert ? 'open' : 'notified'] = DateTime.now();
      }
    });
    final gap = at['open']!.difference(at['notified']!);
    expect(gap, greaterThanOrEqualTo(const Duration(milliseconds: 14)));
  });

  test('a camera added during the session plays the fire script', () async {
    final states = await FakeDetectionRepository(
      world(),
    ).start(newCamera).toList();
    final alert = (states.last as DetectionNotified).alert;
    expect(alert.cameraId, 'cam-new');
    expect(alert.status, EventStatus.fire);
  });

  test('confirmed alert is pushed and saved in history', () async {
    final w = world();
    final pushed = FakeAlertRepository(w).incomingAlerts().first;
    final states = await FakeDetectionRepository(w).start(fireCamera).toList();
    final alert = (states.last as DetectionNotified).alert;
    expect((await pushed).id, alert.id);
    final history = await FakeHistoryRepository(w).list();
    expect(history.first.id, alert.id);
  });

  test(
    'the fire plays once per app run, then the camera just watches',
    () async {
      final w = world();
      final repo = FakeDetectionRepository(w);
      await repo.start(fireCamera).toList();
      expect(w.firedCameraIds, {FakeData.fireCameraId});

      final events = w.events.length;
      final states = <DetectionState>[];
      repo.start(fireCamera).listen(states.add);
      await pumpEventQueue();
      expect(states, [const DetectionWatching()]);
      expect(w.events.length, events);
      await repo.stop();
    },
  );

  test('other camera: dismissed (E4), then watching until stop', () async {
    final w = world();
    final repo = FakeDetectionRepository(w);
    final states = <DetectionState>[];
    final done = repo.start(otherCamera).listen(states.add).asFuture();
    await pumpEventQueue();

    expect(states.map((s) => s.runtimeType), [
      DetectionWatching,
      DetectionVerifying,
      DetectionVerifying,
      DetectionDismissed,
      DetectionWatching,
    ]);
    final dismissed = states[3] as DetectionDismissed;
    expect(dismissed.reason.explanation, 'Chỉ là đèn xe chiếu lên tường.');
    expect(dismissed.event.status, EventStatus.dismissed);
    expect(dismissed.event.cameraId, 'cam-ramp');
    expect(states.last, const DetectionWatching());

    final history = await FakeHistoryRepository(w).list();
    expect(history.first.id, dismissed.event.id);

    await repo.stop();
    await done;
    expect(states.last, const DetectionWatching());
  });

  test('"Bỏ qua" during E2a goes back to watching, no alert', () async {
    final w = world();
    final repo = FakeDetectionRepository(w);
    final events = w.events.length;
    final states = <DetectionState>[];
    final done = repo.start(fireCamera).listen((s) {
      states.add(s);
      if (s is DetectionVerifying) repo.dismissSuspect();
    }).asFuture();
    await pumpEventQueue(times: 50);

    expect(states.map((s) => s.runtimeType), [
      DetectionWatching,
      DetectionVerifying,
      DetectionWatching,
    ]);
    expect(w.events.length, events);
    expect(w.firedCameraIds, isEmpty);

    await repo.stop();
    await done;
  });

  test('"Bỏ qua" is ignored once the server answered', () async {
    final repo = FakeDetectionRepository(world());
    final states = <DetectionState>[];
    await repo.start(fireCamera).forEach((s) {
      states.add(s);
      if (s is DetectionNotified) repo.dismissSuspect();
    });
    expect(states.last, isA<DetectionNotified>());
    expect(states.whereType<DetectionWatching>(), hasLength(1));
  });

  test('server error → unverified (F4)', () async {
    final states = await FakeDetectionRepository(
      world({FakeCase.verificationServerError}),
    ).start(fireCamera).toList();
    expect(states.last, isA<DetectionUnverified>());
    final alert = (states.last as DetectionUnverified).alert;
    expect(alert.status, EventStatus.unverified);
    expect(alert.sign, DetectedSign.smoke);
  });

  test('offline → suspect frame queued (E5), stream stays open', () async {
    final repo = FakeDetectionRepository(world({FakeCase.offline}));
    final states = <DetectionState>[];
    final done = repo.start(fireCamera).listen(states.add).asFuture();
    await pumpEventQueue();
    expect(states.last, const DetectionOffline());

    await repo.stop();
    await done;
    expect(states.last, isA<DetectionOffline>());
  });

  test('slow device → degraded 5→2 fps (E6), then continues', () async {
    final states = await FakeDetectionRepository(
      world({FakeCase.slowDevice}),
    ).start(fireCamera).toList();
    expect(
      states[1],
      const DetectionDegraded(fromFps: normalFps, fps: degradedFps),
    );
    expect((states[2] as DetectionVerifying).fps, 2);
    expect((states.last as DetectionNotified).fps, 2);
  });

  test('starting again ends the previous session', () async {
    final repo = FakeDetectionRepository(world());
    final first = repo.start(otherCamera).toList();
    final second = repo.start(fireCamera).toList();
    expect(await first, [const DetectionWatching()]);
    expect((await second).last, isA<DetectionNotified>());
  });

  test('stop while verifying closes the stream, the fire not played', () async {
    final w = FakeWorld(
      const FakeScenario(timeScale: 0.001, freezeClock: true),
    );
    final repo = FakeDetectionRepository(w);
    final states = <DetectionState>[];
    final done = repo.start(fireCamera).listen((s) {
      states.add(s);
      if (s is DetectionVerifying) repo.stop();
    }).asFuture();
    await done;
    expect(states.last, isA<DetectionVerifying>());
    expect(states.whereType<DetectionNotified>(), isEmpty);
    expect(w.firedCameraIds, isEmpty);
  });
}
