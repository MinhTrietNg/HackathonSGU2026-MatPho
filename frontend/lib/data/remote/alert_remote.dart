library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../errors.dart';
import '../models/fire_event.dart';
import '../models/group.dart';
import '../models/incident.dart';
import '../repositories/alert_repository.dart';
import '../session/emergency_token_store.dart';
import 'core/api_client.dart';
import 'core/json.dart';
import 'core/remote_providers.dart';
import 'core/ws_client.dart';
import 'group_remote.dart' show parseAuditEntry, parseGroupRole;

final class RemoteAlertRepository implements AlertRepository {
  RemoteAlertRepository(this._api, this._ws);

  final ApiClient _api;
  final WsClient _ws;

  @override
  Stream<FireEvent> incomingAlerts() {
    final seen = <String>{};
    return _ws
        .ofType('FIRE_ALERT')
        .map((message) => _tryParse(message.json))
        .where(
          (event) =>
              event != null &&
              (event.status == EventStatus.fire ||
                  event.status == EventStatus.unverified) &&
              seen.add('${event.id}/${event.status.name}'),
        )
        .cast<FireEvent>();
  }

  @override
  Stream<AlertUpdate> alertUpdates() => _ws
      .ofType('FIRE_ALERT_UPDATED')
      .map((message) {
        try {
          return parseAlertUpdate(message.json);
        } on MpException {
          return null;
        }
      })
      .where((update) => update != null)
      .cast<AlertUpdate>();

  @override
  Future<FireEvent> getAlert(String eventId) async {
    final token = EmergencyTokenStore.instance.get(eventId);
    final response = await _api.get(
      _path(eventId),
      query: token != null ? {'emergency_token': token} : null,
      authenticated: token == null,
    );
    return parseFireEvent(asJsonMap(response));
  }

  @override
  Future<FireEvent> recordCall114(String eventId) =>
      _actThenGet(eventId, 'call-114');

  @override
  Future<FireEvent> resolve(String eventId) =>
      _actThenGet(eventId, 'resolve', body: const <String, Object?>{});

  @override
  Future<FireEvent> markFalseAlarm(String eventId) =>
      _actThenGet(eventId, 'mark-false-alarm');

  @override
  Future<FireEvent> reportRealFire(String eventId) =>
      _actThenGet(eventId, 'report-real-fire');

  @override
  Future<EscalationStatus> escalationStatus(String eventId) async {
    final token = EmergencyTokenStore.instance.get(eventId);
    final json = asJsonMap(
      await _api.get(
        '${_path(eventId)}/escalation-status',
        query: token != null ? {'emergency_token': token} : null,
        authenticated: token == null,
      ),
    );
    final remaining = readIntOrNull(json, 'remaining_seconds') ?? 0;
    return EscalationStatus(
      eventId: readStringOrNull(json, 'alert_id') ?? eventId,
      timerActive: readBoolOrNull(json, 'timer_active') ?? false,
      remaining: Duration(seconds: remaining < 0 ? 0 : remaining),
      level: readIntOrNull(json, 'escalation_level') ?? 0,
    );
  }

  @override
  Future<DispatchInfo> dispatchInfo(String eventId) async {
    final token = EmergencyTokenStore.instance.get(eventId);
    final json = asJsonMap(
      await _api.get(
        '${_path(eventId)}/dispatch-info',
        query: token != null ? {'emergency_token': token} : null,
        authenticated: token == null,
      ),
    );
    return DispatchInfo(
      eventId: readStringOrNull(json, 'alert_id') ?? eventId,
      facilityName: readStringOrNull(json, 'facility_name') ?? '',
      address: readStringOrNull(json, 'address') ?? '',
      callScript: readStringOrNull(json, 'call_script') ?? '',
      locationName: readStringOrNull(json, 'location_name'),
      cameraName: readStringOrNull(json, 'cam_name'),
      contacts: [
        if (json['emergency_contacts'] != null)
          for (final contact in readObjectList(
            json,
            'emergency_contacts',
            _contact,
          ))
            ?contact,
      ],
      stillUrl: readStringOrNull(json, 'still_url'),
      detectedAt: _time(json, 'detected_at'),
      called114At: _time(json, 'called_114_at'),
    );
  }

  @override
  Future<List<AuditEntry>> auditLog(String eventId) async {
    final token = EmergencyTokenStore.instance.get(eventId);
    return readObjectList(
      asJsonMap(
        await _api.get(
          '${_path(eventId)}/audit-logs',
          query: token != null ? {'emergency_token': token} : null,
          authenticated: token == null,
        ),
      ),
      'items',
      parseAuditEntry,
    );
  }

  static EmergencyContact? _contact(Map<String, Object?> json) {
    final GroupRole role;
    try {
      role = parseGroupRole(readString(json, 'role'));
    } on ServerException {
      return null;
    }
    return EmergencyContact(
      userId: readString(json, 'user_id'),
      name: readStringOrNull(json, 'full_name') ?? '',
      phone: displayPhone(readString(json, 'phone_number')),
      role: role,
    );
  }

  static DateTime? _time(Map<String, Object?> json, String key) {
    final value = json[key];
    return value is String ? tryParseServerTime(value) : null;
  }

  Future<FireEvent> _actThenGet(
    String eventId,
    String action, {
    Object? body,
  }) async {
    final token = EmergencyTokenStore.instance.get(eventId);
    await _api.post(
      '${_path(eventId)}/$action',
      query: token != null ? {'emergency_token': token} : null,
      body: body,
      authenticated: token == null,
    );
    return getAlert(eventId);
  }

  static String _path(String eventId) =>
      '/alerts/${Uri.encodeComponent(eventId)}';

  static FireEvent? _tryParse(Map<String, Object?> json) {
    try {
      return parseFireEvent(json);
    } on MpException {
      return null;
    }
  }
}

final remoteAlertRepositoryProvider = Provider<AlertRepository>(
  (ref) => RemoteAlertRepository(
    ref.watch(apiClientProvider),
    ref.watch(wsClientProvider),
  ),
);

FireEvent parseFireEvent(Map<String, Object?> json) {
  final status = readStringOrNull(json, 'status');
  final verification = readStringOrNull(json, 'verification');
  final eventStatus = verification == 'SUPPRESSED' || status == 'SUPPRESSED'
      ? EventStatus.dismissed
      : status == 'FALSE_ALARM'
      ? EventStatus.falseAlarm
      : verification == 'UNVERIFIED'
      ? EventStatus.unverified
      : EventStatus.fire;
  final detectedAt = readDateTimeOrNull(json, 'detected_at') ?? DateTime.now();
  return FireEvent(
    id: readString(json, 'alert_id'),
    cameraId: readString(json, 'cam_id'),
    locationName:
        readStringOrNull(json, 'location_name') ??
        readStringOrNull(json, 'cam_name') ??
        '',
    status: eventStatus,
    detectedAt: detectedAt,
    summary: readStringOrNull(json, 'summary') ?? '',
    detail: readStringOrNull(json, 'detail'),
    sign: parseSign(readStringOrNull(json, 'sign')),
    confidence: readDoubleOrNull(json, 'confidence'),
    checkCount: readIntOrNull(json, 'check_count'),
    address: readStringOrNull(json, 'address'),
    callScript: readStringOrNull(json, 'call_script'),
    timeline: _timeline(json, eventStatus, detectedAt),
    resolved: status == 'RESOLVED',
    called114: json['called_114_at'] != null,
    stillUrl: readStringOrNull(json, 'still_url'),
    snapshots: json['timeline_snapshots'] == null
        ? const []
        : readObjectList(json, 'timeline_snapshots', _snapshot),
    resolvedByName: readStringOrNull(json, 'resolved_by_name'),
  );
}

AlertUpdate? parseAlertUpdate(Map<String, Object?> json) {
  final outcome = switch (readString(json, 'status')) {
    'RESOLVED' => AlertUpdateOutcome.resolved,
    'FALSE_ALARM' => AlertUpdateOutcome.falseAlarm,
    _ => null,
  };
  if (outcome == null) return null;
  return AlertUpdate(
    eventId: readString(json, 'alert_id'),
    outcome: outcome,
    resolvedByName: readStringOrNull(json, 'resolved_by_name'),
  );
}

DetectedSign? parseSign(String? sign) => switch (sign) {
  'FIRE' || 'BOTH' => DetectedSign.fire,
  'SMOKE' => DetectedSign.smoke,
  _ => null,
};

const _stepKinds = ['DETECTED', 'IMAGE_SENT', 'AI_VERIFIED', 'ALERT_TRIGGERED'];

TimelineStepKind? stepKindOf(String kind, {required bool dismissed}) =>
    switch (kind) {
      'DETECTED' => TimelineStepKind.detected,
      'IMAGE_SENT' => TimelineStepKind.imageSent,
      'AI_VERIFIED' =>
        dismissed
            ? TimelineStepKind.confirmedNotFire
            : TimelineStepKind.confirmedFire,
      'ALERT_TRIGGERED' => TimelineStepKind.notified,
      _ => null,
    };

List<TimelineStep> _timeline(
  Map<String, Object?> json,
  EventStatus status,
  DateTime detectedAt,
) {
  final raw = json['steps'];
  if (raw == null) return const [];
  final times = <String, DateTime>{};
  if (raw is Map<String, Object?>) {
    for (final kind in _stepKinds) {
      if (raw[kind] != null) times[kind] = readDateTime(raw, kind);
    }
  } else {
    for (final step in readObjectList(json, 'steps', (item) => item)) {
      final kind =
          readStringOrNull(step, 'step') ?? readStringOrNull(step, 'kind');
      if (kind != null && _stepKinds.contains(kind)) {
        times[kind] = readDateTime(step, 'at');
      }
    }
  }
  final origin = times['DETECTED'] ?? detectedAt;
  final dismissed = status == EventStatus.dismissed;
  final steps = [
    for (final kind in _stepKinds)
      if (times[kind] case final at?)
        TimelineStep(
          stepKindOf(kind, dismissed: dismissed)!,
          at.difference(origin),
        ),
  ];
  if (dismissed && steps.isNotEmpty && !times.containsKey('ALERT_TRIGGERED')) {
    steps.add(const TimelineStep(TimelineStepKind.notNotified, null));
  }
  return steps;
}

EvidenceSnapshot _snapshot(Map<String, Object?> json) => EvidenceSnapshot(
  url: readStringOrNull(json, 'url') ?? readString(json, 'image_url'),
  box: _box(json),
  takenAt: tryParseServerTime(readStringOrNull(json, 'timestamp')),
);

EvidenceBox? _box(Map<String, Object?> json) {
  final raw = json['bbox'];
  if (raw == null) return null;
  final values = readList(json, 'bbox');
  if (values.length != 4 || values.any((v) => v is! num)) return null;
  final [x1, y1, x2, y2] = [for (final v in values) (v! as num).toDouble()];
  if ([x1, y1, x2, y2].any((v) => v < 0 || v > 1)) return null;
  return (
    left: x1 < x2 ? x1 : x2,
    top: y1 < y2 ? y1 : y2,
    right: x1 < x2 ? x2 : x1,
    bottom: y1 < y2 ? y2 : y1,
  );
}
