library;

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../errors.dart';
import '../models/models.dart';
import '../repositories/detection_repository.dart';
import 'alert_remote.dart' show parseFireEvent, parseSign, stepKindOf;

import 'core/api_client.dart';
import 'core/json.dart';
import 'core/remote_providers.dart';
import 'core/ws_client.dart';

final class RemoteDetectionRepository implements DetectionRepository {
  RemoteDetectionRepository(
    this._api,
    this._ws, {
    this.openAlertAfter = const Duration(milliseconds: 1500),
    this.dismissToast = const Duration(seconds: 4),
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now;

  final ApiClient _api;
  final WsClient _ws;
  final DateTime Function() _now;

  final Duration openAlertAfter;

  final Duration dismissToast;

  _Session? _session;

  @override
  Stream<DetectionState> start(Camera camera) {
    _end();
    final session = _Session(camera.id);
    _session = session;
    session
      ..messages = _ws.messages.listen((message) {
        if (message.json['cam_id'] != session.cameraId) return;
        try {
          _onMessage(session, message);
        } on MpException {
          // A malformed message is dropped; the next one corrects the state.
        }
      })
      ..connection = _ws.states.listen((state) => _onConnection(session, state))
      ..emit(
        _ws.state == WsConnectionState.connected
            ? DetectionWatching(fps: session.fps)
            : DetectionOffline(fps: session.fps),
      );
    return session.states.stream;
  }

  @override
  Future<void> dismissSuspect() async {
    final session = _session;
    if (session == null) return;
    final now = session.state;
    if (now is! DetectionVerifying || !now.awaitingVerdict) return;
    session
      ..skippedAt = now.suspect.detectedAt
      ..resetVerification()
      ..emit(DetectionWatching(fps: session.fps));
    try {
      await _api.post(
        '/cameras/${Uri.encodeComponent(session.cameraId)}/suspect/dismiss',
      );
    } on MpException {
      // The server's next message corrects the state if this did not land.
    }
  }

  @override
  Future<void> stop() async => _end();

  void _end() {
    _session?.close();
    _session = null;
  }

  void _onConnection(_Session s, WsConnectionState state) {
    if (s.closed || s.alerted) return;
    switch (state) {
      case WsConnectionState.disconnected:
        s
          ..resetVerification()
          ..emit(DetectionOffline(fps: s.fps));
      case WsConnectionState.connected:
        if (s.state is DetectionOffline) s.emit(DetectionWatching(fps: s.fps));
    }
  }

  void _onMessage(_Session s, WsMessage message) {
    final json = message.json;
    switch (message.type) {
      case 'CAMERA_HEARTBEAT':
        _onHeartbeat(s, readIntOrNull(json, 'fps'));
      case 'AI_VERIFYING':
        _onVerifying(s, json);
      case 'FIRE_ALERT':
        unawaited(_onAlert(s, parseFireEvent(json)));
      case 'FIRE_ALERT_SUPPRESSED':
        _onSuppressed(s, json);
    }
  }

  void _onHeartbeat(_Session s, int? fps) {
    if (fps != null && fps > 0) s.fps = fps;
    switch (s.state) {
      case DetectionIdle() || DetectionWatching() || DetectionOffline():
        s.emit(DetectionWatching(fps: s.fps));
      case DetectionVerifying(:final suspect, :final steps, :final verdict):
        s.emit(
          DetectionVerifying(
            suspect: suspect,
            steps: steps,
            verdict: verdict,
            fps: s.fps,
          ),
        );
      case _:
    }
  }

  void _onVerifying(_Session s, Map<String, Object?> json) {
    final times = <String, DateTime>{};
    for (final step in readObjectList(json, 'steps', (item) => item)) {
      final kind =
          readStringOrNull(step, 'step') ?? readStringOrNull(step, 'kind');
      if (kind != null) times[kind] = readDateTime(step, 'at');
    }
    final detectedAt = times['DETECTED'] ?? s.detectedAt ?? _now();
    if (detectedAt == s.skippedAt) return;
    final sign = parseSign(readStringOrNull(json, 'sign')) ?? DetectedSign.fire;
    final confidence = readDoubleOrNull(json, 'confidence') ?? 0;
    final frame = SuspectFrame(
      sign: sign,
      confidence: confidence,
      detectedAt: detectedAt,
    );
    if (s.detectedAt != detectedAt) s.suspect = frame;
    s
      ..detectedAt = detectedAt
      ..steps = [
        for (final kind in const ['DETECTED', 'IMAGE_SENT', 'AI_VERIFIED'])
          if (times[kind] case final at?)
            TimelineStep(
              stepKindOf(kind, dismissed: false)!,
              at.difference(detectedAt),
            ),
      ]
      ..cancelToast();
    s.emit(
      DetectionVerifying(
        suspect: s.suspect ?? frame,
        steps: s.steps,
        verdict: times.containsKey('AI_VERIFIED') ? frame : null,
        fps: s.fps,
      ),
    );
  }

  Future<void> _onAlert(_Session s, FireEvent wsEvent) async {
    s.cancelToast();
    if (wsEvent.status == EventStatus.unverified) {
      s
        ..emit(DetectionUnverified(wsEvent, fps: s.fps))
        ..close();
      return;
    }
    if (wsEvent.status != EventStatus.fire || s.alerted) return;
    s.alerted = true;
    FireEvent event;
    try {
      event = parseFireEvent(
        asJsonMap(await _api.get('/alerts/${Uri.encodeComponent(wsEvent.id)}')),
      );
    } on MpException {
      event = wsEvent.copyWith(timeline: s.steps);
    }
    if (!s.emit(DetectionNotified(event, fps: s.fps))) return;
    s.timer = Timer(openAlertAfter, () {
      s
        ..emit(DetectionNotified(event, openAlert: true, fps: s.fps))
        ..close();
    });
  }

  void _onSuppressed(_Session s, Map<String, Object?> json) {
    final detail = readStringOrNull(json, 'detail') ?? '';
    final event = FireEvent(
      id: readString(json, 'alert_id'),
      cameraId: s.cameraId,
      locationName: '',
      status: EventStatus.dismissed,
      detectedAt: s.detectedAt ?? _now(),
      summary: readStringOrNull(json, 'summary') ?? 'Không phải cháy',
      detail: detail,
    );
    s
      ..resetVerification()
      ..emit(
        DetectionDismissed(
          reason: DismissalReason(explanation: detail),
          event: event,
          fps: s.fps,
        ),
      )
      ..timer = Timer(dismissToast, () {
        if (s.state is DetectionDismissed) {
          s.emit(DetectionWatching(fps: s.fps));
        }
      });
  }
}

final remoteDetectionRepositoryProvider = Provider<DetectionRepository>((ref) {
  final repository = RemoteDetectionRepository(
    ref.watch(apiClientProvider),
    ref.watch(wsClientProvider),
  );
  ref.onDispose(repository.stop);
  return repository;
});

final class _Session {
  _Session(this.cameraId);

  final String cameraId;
  final states = StreamController<DetectionState>();
  StreamSubscription<WsMessage>? messages;
  StreamSubscription<WsConnectionState>? connection;

  Timer? timer;

  DetectionState state = const DetectionIdle();
  int fps = normalFps;

  SuspectFrame? suspect;
  DateTime? detectedAt;
  List<TimelineStep> steps = const [];

  DateTime? skippedAt;

  bool alerted = false;

  bool get closed => states.isClosed;

  bool emit(DetectionState next) {
    if (closed) return false;
    state = next;
    states.add(next);
    return true;
  }

  void resetVerification() {
    cancelToast();
    suspect = null;
    detectedAt = null;
    steps = const [];
  }

  void cancelToast() {
    timer?.cancel();
    timer = null;
  }

  void close() {
    cancelToast();
    unawaited(messages?.cancel());
    unawaited(connection?.cancel());
    messages = null;
    connection = null;
    if (!closed) unawaited(states.close());
  }
}
