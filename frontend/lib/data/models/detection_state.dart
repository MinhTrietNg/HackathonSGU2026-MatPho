import 'fire_event.dart';

const normalFps = 5;

const degradedFps = 2;

const verifyTypicalMin = Duration(seconds: 3);
const verifyTypicalMax = Duration(seconds: 8);

final class SuspectFrame {
  const SuspectFrame({
    required this.sign,
    required this.confidence,
    required this.detectedAt,
  });

  final DetectedSign sign;
  final double confidence;
  final DateTime detectedAt;

  @override
  bool operator ==(Object other) =>
      other is SuspectFrame &&
      other.sign == sign &&
      other.confidence == confidence &&
      other.detectedAt == detectedAt;

  @override
  int get hashCode => Object.hash(sign, confidence, detectedAt);
}

final class DismissalReason {
  const DismissalReason({required this.explanation});

  final String explanation;

  @override
  bool operator ==(Object other) =>
      other is DismissalReason && other.explanation == explanation;

  @override
  int get hashCode => explanation.hashCode;
}

sealed class DetectionState {
  const DetectionState();
}

final class DetectionIdle extends DetectionState {
  const DetectionIdle();

  @override
  bool operator ==(Object other) => other is DetectionIdle;

  @override
  int get hashCode => (DetectionIdle).hashCode;

  @override
  String toString() => 'DetectionIdle()';
}

final class DetectionWatching extends DetectionState {
  const DetectionWatching({this.fps = normalFps});

  final int fps;

  @override
  bool operator ==(Object other) =>
      other is DetectionWatching && other.fps == fps;

  @override
  int get hashCode => fps.hashCode;

  @override
  String toString() => 'DetectionWatching($fps fps)';
}

final class DetectionVerifying extends DetectionState {
  const DetectionVerifying({
    required this.suspect,
    required this.steps,
    this.verdict,
    this.fps = normalFps,
  });

  final SuspectFrame suspect;
  final List<TimelineStep> steps;

  final SuspectFrame? verdict;
  final int fps;

  bool get awaitingVerdict => verdict == null;

  @override
  bool operator ==(Object other) =>
      other is DetectionVerifying &&
      other.suspect == suspect &&
      _listEquals(other.steps, steps) &&
      other.verdict == verdict &&
      other.fps == fps;

  @override
  int get hashCode => Object.hash(suspect, Object.hashAll(steps), verdict, fps);

  @override
  String toString() =>
      'DetectionVerifying(${steps.map((s) => s.kind.name).join(' ▸ ')})';
}

final class DetectionNotified extends DetectionState {
  const DetectionNotified(
    this.alert, {
    this.openAlert = false,
    this.fps = normalFps,
  });

  final FireEvent alert;
  final bool openAlert;
  final int fps;

  @override
  String toString() => 'DetectionNotified(${alert.id}, open: $openAlert)';
}

final class DetectionDismissed extends DetectionState {
  const DetectionDismissed({
    required this.reason,
    required this.event,
    this.fps = normalFps,
  });

  final DismissalReason reason;
  final FireEvent event;
  final int fps;

  @override
  String toString() => 'DetectionDismissed(${event.id})';
}

final class DetectionUnverified extends DetectionState {
  const DetectionUnverified(this.alert, {this.fps = normalFps});

  final FireEvent alert;
  final int fps;

  @override
  String toString() => 'DetectionUnverified(${alert.id})';
}

final class DetectionOffline extends DetectionState {
  const DetectionOffline({this.fps = normalFps});

  final int fps;

  @override
  bool operator ==(Object other) =>
      other is DetectionOffline && other.fps == fps;

  @override
  int get hashCode => fps.hashCode;

  @override
  String toString() => 'DetectionOffline($fps fps)';
}

final class DetectionDegraded extends DetectionState {
  const DetectionDegraded({required this.fromFps, required this.fps});

  final int fromFps;
  final int fps;

  @override
  bool operator ==(Object other) =>
      other is DetectionDegraded &&
      other.fromFps == fromFps &&
      other.fps == fps;

  @override
  int get hashCode => Object.hash(fromFps, fps);

  @override
  String toString() => 'DetectionDegraded($fromFps→$fps)';
}

bool _listEquals<T>(List<T> a, List<T> b) {
  if (a.length != b.length) return false;
  for (var i = 0; i < a.length; i++) {
    if (a[i] != b[i]) return false;
  }
  return true;
}
