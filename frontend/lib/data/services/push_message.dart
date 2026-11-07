library;

sealed class PushMessage {
  const PushMessage();

  static const fireAlertType = 'FIRE_ALERT';
  static const fireAlertUpdatedType = 'FIRE_ALERT_UPDATED';
  static const testAlertType = 'TEST_ALERT';
  static const invitationType = 'INVITATION';
  static const roleChangedType = 'ROLE_CHANGED';
  static const cameraOfflineType = 'CAMERA_OFFLINE';

  static PushMessage? decode(Map<String, Object?> data) {
    String? field(String key) {
      final value = data[key];
      return value is String && value.isNotEmpty ? value : null;
    }

    T? need<T>(List<String> keys, T Function(List<String>) build) {
      final values = [for (final k in keys) field(k)];
      if (values.contains(null)) return null;
      return build(values.cast<String>());
    }

    return switch (field('type')) {
      fireAlertType => need(
        ['alert_id'],
        (v) => FireAlertPush(
          alertId: v[0],
          escalationLevel: int.tryParse(field('escalation_level') ?? '') ?? 0,
        ),
      ),
      fireAlertUpdatedType => need(
        ['alert_id'],
        (v) => FireAlertUpdatedPush(
          alertId: v[0],
          status: field('status'),
          resolvedByName: field('resolved_by_name'),
        ),
      ),
      testAlertType => need(['test_id'], (v) => TestAlertPush(testId: v[0])),
      invitationType => need([
        'group_id',
        'invitation_id',
      ], (v) => InvitationPush(groupId: v[0], invitationId: v[1])),
      roleChangedType => need([
        'group_id',
      ], (v) => RoleChangedPush(groupId: v[0])),
      cameraOfflineType => need([
        'cam_id',
      ], (v) => CameraOfflinePush(cameraId: v[0])),
      _ => null,
    };
  }
}

final class FireAlertPush extends PushMessage {
  const FireAlertPush({required this.alertId, this.escalationLevel = 0});

  final String alertId;
  final int escalationLevel;

  @override
  bool operator ==(Object other) =>
      other is FireAlertPush &&
      other.alertId == alertId &&
      other.escalationLevel == escalationLevel;

  @override
  int get hashCode => Object.hash(alertId, escalationLevel);

  @override
  String toString() => 'FireAlertPush($alertId, level $escalationLevel)';
}

final class FireAlertUpdatedPush extends PushMessage {
  const FireAlertUpdatedPush({
    required this.alertId,
    this.status,
    this.resolvedByName,
  });

  final String alertId;

  final String? status;

  final String? resolvedByName;

  @override
  bool operator ==(Object other) =>
      other is FireAlertUpdatedPush &&
      other.alertId == alertId &&
      other.status == status &&
      other.resolvedByName == resolvedByName;

  @override
  int get hashCode => Object.hash(alertId, status, resolvedByName);

  @override
  String toString() => 'FireAlertUpdatedPush($alertId, $status)';
}

final class TestAlertPush extends PushMessage {
  const TestAlertPush({required this.testId});

  final String testId;

  @override
  bool operator ==(Object other) =>
      other is TestAlertPush && other.testId == testId;

  @override
  int get hashCode => testId.hashCode;

  @override
  String toString() => 'TestAlertPush($testId)';
}

final class InvitationPush extends PushMessage {
  const InvitationPush({required this.groupId, required this.invitationId});

  final String groupId;
  final String invitationId;

  @override
  bool operator ==(Object other) =>
      other is InvitationPush &&
      other.groupId == groupId &&
      other.invitationId == invitationId;

  @override
  int get hashCode => Object.hash(groupId, invitationId);

  @override
  String toString() => 'InvitationPush($invitationId in $groupId)';
}

final class RoleChangedPush extends PushMessage {
  const RoleChangedPush({required this.groupId});

  final String groupId;

  @override
  bool operator ==(Object other) =>
      other is RoleChangedPush && other.groupId == groupId;

  @override
  int get hashCode => groupId.hashCode;

  @override
  String toString() => 'RoleChangedPush($groupId)';
}

final class CameraOfflinePush extends PushMessage {
  const CameraOfflinePush({required this.cameraId});

  final String cameraId;

  @override
  bool operator ==(Object other) =>
      other is CameraOfflinePush && other.cameraId == cameraId;

  @override
  int get hashCode => cameraId.hashCode;

  @override
  String toString() => 'CameraOfflinePush($cameraId)';
}
