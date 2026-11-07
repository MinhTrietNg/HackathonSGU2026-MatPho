import 'dart:async';

import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/repositories/detection_repository.dart';
import 'fake_data.dart';
import 'fake_scenario.dart';
import 'fake_world.dart';

abstract final class FakeDetectionTimings {
  static const untilSuspect = Duration(seconds: 19);

  static const untilDegraded = Duration(seconds: 3);

  static const dismissToast = Duration(seconds: 4);

  static const openAlertAfter = Duration(milliseconds: 1500);
}

final class FakeDetectionRepository implements DetectionRepository {
  FakeDetectionRepository(this._world);

  final FakeWorld _world;
  _Session? _session;

  @override
  Stream<DetectionState> start(Camera camera) {
    _endSession();
    final session = _Session();
    _session = session;
    unawaited(_run(camera, session));
    return session.states.stream;
  }

  @override
  Future<void> dismissSuspect() async {
    final session = _session;
    if (session == null || !session.awaitingVerdict) return;
    session
      ..awaitingVerdict = false
      ..skipped = true;
    session.emit(DetectionWatching(fps: session.fps));
  }

  @override
  Future<void> stop() async => _endSession();

  void _endSession() {
    final session = _session;
    _session = null;
    if (session != null && !session.states.isClosed) session.states.close();
  }

  Future<void> _run(Camera camera, _Session s) async {
    final scenario = _world.scenario;

    Future<bool> wait(Duration base) async {
      await _world.delay(base);
      return s.running;
    }

    void finish(DetectionState state) {
      if (s.emit(state)) s.states.close();
    }

    if (!s.emit(const DetectionWatching())) return;

    if (scenario.has(FakeCase.slowDevice)) {
      if (!await wait(FakeDetectionTimings.untilDegraded)) return;
      s.fps = degradedFps;
      s.emit(const DetectionDegraded(fromFps: normalFps, fps: degradedFps));
    }

    if (_world.firedCameraIds.contains(camera.id)) return;

    if (!await wait(FakeDetectionTimings.untilSuspect)) return;
    final detectedAt = _world.now();
    final suspect = SuspectFrame(
      sign: FakeData.suspectSign,
      confidence: FakeData.suspectConfidence,
      detectedAt: detectedAt,
    );

    if (scenario.has(FakeCase.offline)) {
      s.emit(DetectionOffline(fps: s.fps));
      return;
    }

    const detected = TimelineStep(TimelineStepKind.detected, Duration.zero);
    const imageSent = TimelineStep(
      TimelineStepKind.imageSent,
      FakeData.imageSentAfter,
    );
    s.awaitingVerdict = true;
    if (!s.emit(
      DetectionVerifying(suspect: suspect, steps: const [detected], fps: s.fps),
    )) {
      return;
    }
    if (!await wait(FakeData.imageSentAfter)) return;
    if (!s.emit(
      DetectionVerifying(
        suspect: suspect,
        steps: const [detected, imageSent],
        fps: s.fps,
      ),
    )) {
      return;
    }

    final isFire = _playsFire(camera);
    final verifiedAt = isFire
        ? FakeData.fireConfirmedAfter
        : FakeData.notFireConfirmedAfter;
    if (!await wait(verifiedAt - FakeData.imageSentAfter)) return;
    s.awaitingVerdict = false;

    if (scenario.has(FakeCase.verificationServerError)) {
      final event = FakeData.unverifiedEvent(
        id: _world.newId('evt'),
        cameraId: camera.id,
        detectedAt: detectedAt,
      );
      _world
        ..firedCameraIds.add(camera.id)
        ..addEvent(event, alert: true);
      finish(DetectionUnverified(event, fps: s.fps));
      return;
    }

    if (!isFire) {
      final event = FakeData.dismissedEvent(
        id: _world.newId('evt'),
        cameraId: camera.id,
        detectedAt: detectedAt,
      );
      _world.addEvent(event);
      if (!s.emit(
        DetectionDismissed(
          reason: FakeData.dismissalReason,
          event: event,
          fps: s.fps,
        ),
      )) {
        return;
      }
      if (!await wait(FakeDetectionTimings.dismissToast)) return;
      s.emit(DetectionWatching(fps: s.fps));
      return;
    }

    if (!s.emit(
      DetectionVerifying(
        suspect: suspect,
        steps: const [
          detected,
          imageSent,
          TimelineStep(
            TimelineStepKind.confirmedFire,
            FakeData.fireConfirmedAfter,
          ),
        ],
        verdict: SuspectFrame(
          sign: DetectedSign.fire,
          confidence: FakeData.fireConfidence,
          detectedAt: detectedAt,
        ),
        fps: s.fps,
      ),
    )) {
      return;
    }
    if (!await wait(FakeData.fireNotifiedAfter - FakeData.fireConfirmedAfter)) {
      return;
    }
    final alert = FakeData.fireAlert(
      id: _world.newId('evt'),
      cameraId: camera.id,
      detectedAt: detectedAt,
    );
    _world
      ..firedCameraIds.add(camera.id)
      ..addEvent(alert, alert: true);
    if (!s.emit(DetectionNotified(alert, fps: s.fps))) return;
    if (!await wait(FakeDetectionTimings.openAlertAfter)) return;
    finish(DetectionNotified(alert, openAlert: true, fps: s.fps));
  }

  bool _playsFire(Camera camera) =>
      camera.id == FakeData.fireCameraId ||
      !FakeData.cameras.any((c) => c.id == camera.id);
}

final class _Session {
  final states = StreamController<DetectionState>();

  int fps = normalFps;

  bool awaitingVerdict = false;

  bool skipped = false;

  bool get running => !states.isClosed && !skipped;

  bool emit(DetectionState state) {
    if (states.isClosed) return false;
    states.add(state);
    return true;
  }
}
