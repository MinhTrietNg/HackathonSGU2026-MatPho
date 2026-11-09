enum EventStatus { fire, dismissed, unverified, falseAlarm }

enum HistoryFilter {
  all,
  fire,
  dismissed,
  falseAlarm;

  bool matches(EventStatus status) => switch (this) {
    all => true,
    fire => status == EventStatus.fire,
    dismissed => status == EventStatus.dismissed,
    falseAlarm => status == EventStatus.falseAlarm,
  };
}

enum DetectedSign { fire, smoke }

enum TimelineStepKind {
  detected,

  imageSent,

  confirmedFire,

  confirmedNotFire,

  notified,

  notNotified,
}

final class TimelineStep {
  const TimelineStep(this.kind, this.offset);

  final TimelineStepKind kind;

  final Duration? offset;

  @override
  bool operator ==(Object other) =>
      other is TimelineStep && other.kind == kind && other.offset == offset;

  @override
  int get hashCode => Object.hash(kind, offset);

  @override
  String toString() => 'TimelineStep($kind, $offset)';
}

final class EvidenceSnapshot {
  const EvidenceSnapshot({required this.url, this.box, this.takenAt});

  final String url;

  final EvidenceBox? box;

  final DateTime? takenAt;

  @override
  bool operator ==(Object other) =>
      other is EvidenceSnapshot &&
      other.url == url &&
      other.box == box &&
      other.takenAt == takenAt;

  @override
  int get hashCode => Object.hash(url, box, takenAt);

  @override
  String toString() => 'EvidenceSnapshot($url, $box)';
}

typedef EvidenceBox = ({double left, double top, double right, double bottom});

final class AlertUpdate {
  const AlertUpdate({
    required this.eventId,
    required this.outcome,
    this.resolvedByName,
  });

  final String eventId;
  final AlertUpdateOutcome outcome;

  final String? resolvedByName;

  @override
  bool operator ==(Object other) =>
      other is AlertUpdate &&
      other.eventId == eventId &&
      other.outcome == outcome &&
      other.resolvedByName == resolvedByName;

  @override
  int get hashCode => Object.hash(eventId, outcome, resolvedByName);

  @override
  String toString() => 'AlertUpdate($eventId, $outcome, $resolvedByName)';
}

enum AlertUpdateOutcome { resolved, falseAlarm }

final class FireEvent {
  const FireEvent({
    required this.id,
    required this.cameraId,
    required this.locationName,
    required this.status,
    required this.detectedAt,
    required this.summary,
    this.detail,
    this.sign,
    this.confidence,
    this.checkCount,
    this.address,
    this.callScript,
    this.timeline = const [],
    this.resolved = false,
    this.called114 = false,
    this.stillUrl,
    this.snapshots = const [],
    this.resolvedByName,
  });

  final String id;

  final String cameraId;

  final String locationName;
  final EventStatus status;

  final DateTime detectedAt;

  final String summary;

  final String? detail;

  final DetectedSign? sign;

  final double? confidence;

  final int? checkCount;

  final String? address;

  final String? callScript;

  final List<TimelineStep> timeline;

  final bool resolved;

  final bool called114;

  final String? stillUrl;

  final List<EvidenceSnapshot> snapshots;

  final String? resolvedByName;

  Duration? get notifyLatency {
    for (final step in timeline) {
      if (step.kind == TimelineStepKind.notified) return step.offset;
    }
    return null;
  }

  FireEvent copyWith({
    EventStatus? status,
    bool? resolved,
    bool? called114,
    List<TimelineStep>? timeline,
    String? resolvedByName,
  }) => FireEvent(
    id: id,
    cameraId: cameraId,
    locationName: locationName,
    status: status ?? this.status,
    detectedAt: detectedAt,
    summary: summary,
    detail: detail,
    sign: sign,
    confidence: confidence,
    checkCount: checkCount,
    address: address,
    callScript: callScript,
    timeline: timeline ?? this.timeline,
    resolved: resolved ?? this.resolved,
    called114: called114 ?? this.called114,
    stillUrl: stillUrl,
    snapshots: snapshots,
    resolvedByName: resolvedByName ?? this.resolvedByName,
  );

  @override
  bool operator ==(Object other) =>
      other is FireEvent &&
      other.id == id &&
      other.cameraId == cameraId &&
      other.locationName == locationName &&
      other.status == status &&
      other.detectedAt == detectedAt &&
      other.summary == summary &&
      other.detail == detail &&
      other.sign == sign &&
      other.confidence == confidence &&
      other.checkCount == checkCount &&
      other.address == address &&
      other.callScript == callScript &&
      _listEquals(other.timeline, timeline) &&
      other.resolved == resolved &&
      other.called114 == called114 &&
      other.stillUrl == stillUrl &&
      _listEquals(other.snapshots, snapshots) &&
      other.resolvedByName == resolvedByName;

  @override
  int get hashCode => Object.hash(
    id,
    status,
    detectedAt,
    summary,
    Object.hashAll(timeline),
    resolved,
    called114,
  );

  @override
  String toString() => 'FireEvent($id, $status, resolved: $resolved)';
}

bool _listEquals<T>(List<T> a, List<T> b) {
  if (a.length != b.length) return false;
  for (var i = 0; i < a.length; i++) {
    if (a[i] != b[i]) return false;
  }
  return true;
}

const alertLatencyGoal = Duration(seconds: 10);

const undoWindow = Duration(seconds: 5);

const escalationSteps = [Duration(seconds: 60)];

const historyRetention = Duration(days: 30);

const historyLoadTimeout = Duration(seconds: 20);
