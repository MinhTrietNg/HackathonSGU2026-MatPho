import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/repositories/alert_repository.dart';
import 'fake_world.dart';

final class FakeAlertRepository implements AlertRepository {
  FakeAlertRepository(this._world);

  final FakeWorld _world;

  @override
  Stream<FireEvent> incomingAlerts() => _world.incoming;

  @override
  Stream<AlertUpdate> alertUpdates() => const Stream.empty();

  @override
  Future<FireEvent> getAlert(String eventId) async {
    await _world.delay();
    return _world.event(eventId);
  }

  @override
  Future<FireEvent> recordCall114(String eventId) =>
      _update(eventId, (e) => e.copyWith(called114: true));

  @override
  Future<FireEvent> resolve(String eventId) =>
      _update(eventId, (e) => e.copyWith(resolved: true), closes: true);

  @override
  Future<FireEvent> markFalseAlarm(String eventId) => _update(
    eventId,
    (e) => e.copyWith(status: EventStatus.falseAlarm),
    closes: true,
  );

  @override
  Future<FireEvent> reportRealFire(String eventId) =>
      _update(eventId, (e) => e.copyWith(status: EventStatus.fire));

  @override
  Future<EscalationStatus> escalationStatus(String eventId) async {
    await _world.delay();
    final e = _world.event(eventId);
    final stopped =
        e.resolved ||
        e.called114 ||
        e.status == EventStatus.falseAlarm ||
        e.status == EventStatus.dismissed;
    final left = e.detectedAt
        .add(escalationSteps.first)
        .difference(_world.now());
    final active = !stopped && left > Duration.zero;
    return EscalationStatus(
      eventId: eventId,
      timerActive: active,
      remaining: active ? Duration(seconds: left.inSeconds) : Duration.zero,
      level: active ? 0 : 1,
    );
  }

  @override
  Future<DispatchInfo> dispatchInfo(String eventId) async {
    await _world.delay();
    final e = _world.event(eventId);
    final camera = _world.cameras.where((c) => c.id == e.cameraId).firstOrNull;
    final group = camera == null
        ? null
        : _world.groups.where((g) => g.id == camera.groupId).firstOrNull;
    final address = group?.address ?? e.address ?? '';
    return DispatchInfo(
      eventId: eventId,
      facilityName: group?.name ?? '',
      address: address,
      callScript:
          e.callScript ??
          'Báo cháy khẩn cấp tại: $address, khu vực ${e.locationName}.',
      locationName: e.locationName,
      cameraName: camera?.name,
      contacts: [
        for (final m in _world.members[group?.id] ?? const <Member>[])
          if (m.role.canManage && !m.pending)
            EmergencyContact(
              userId: m.id,
              name: m.realName ?? m.nickname ?? '',
              phone: m.phone,
              role: m.role,
            ),
      ],
      stillUrl: e.stillUrl,
      detectedAt: e.detectedAt,
    );
  }

  @override
  Future<List<AuditEntry>> auditLog(String eventId) async {
    await _world.delay();
    _world.event(eventId);
    return const [];
  }

  Future<FireEvent> _update(
    String eventId,
    FireEvent Function(FireEvent) change, {
    bool closes = false,
  }) async {
    await _world.delay();
    final before = _world.event(eventId);
    if (closes && _alertsOnly(before.cameraId)) {
      throw const PermissionDeniedException();
    }
    final after = change(before);
    _world.replaceEvent(after);
    return after;
  }

  bool _alertsOnly(String cameraId) {
    final camera = _world.cameras.where((c) => c.id == cameraId).firstOrNull;
    if (camera == null) return false;
    final group = _world.groups
        .where((g) => g.id == camera.groupId)
        .firstOrNull;
    return group?.myRole == GroupRole.alertsOnly;
  }
}
