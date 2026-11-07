import 'group.dart';

final class EscalationStatus {
  const EscalationStatus({
    required this.eventId,
    required this.timerActive,
    required this.remaining,
    required this.level,
  });

  final String eventId;

  final bool timerActive;

  final Duration remaining;

  final int level;

  @override
  bool operator ==(Object other) =>
      other is EscalationStatus &&
      other.eventId == eventId &&
      other.timerActive == timerActive &&
      other.remaining == remaining &&
      other.level == level;

  @override
  int get hashCode => Object.hash(eventId, timerActive, remaining, level);

  @override
  String toString() =>
      'EscalationStatus($eventId, active: $timerActive, '
      'remaining: $remaining, level: $level)';
}

final class DispatchInfo {
  const DispatchInfo({
    required this.eventId,
    required this.facilityName,
    required this.address,
    required this.callScript,
    this.locationName,
    this.cameraName,
    this.contacts = const [],
    this.stillUrl,
    this.detectedAt,
    this.called114At,
  });

  final String eventId;

  final String facilityName;

  final String address;

  final String callScript;

  final String? locationName;
  final String? cameraName;

  final List<EmergencyContact> contacts;
  final String? stillUrl;
  final DateTime? detectedAt;

  final DateTime? called114At;
}

final class EmergencyContact {
  const EmergencyContact({
    required this.userId,
    required this.name,
    required this.phone,
    required this.role,
  });

  final String userId;
  final String name;

  final String phone;
  final GroupRole role;

  @override
  bool operator ==(Object other) =>
      other is EmergencyContact &&
      other.userId == userId &&
      other.name == name &&
      other.phone == phone &&
      other.role == role;

  @override
  int get hashCode => Object.hash(userId, name, phone, role);
}

final class AuditEntry {
  const AuditEntry({
    required this.id,
    required this.action,
    this.actorId,
    this.target,
    this.details = const {},
    this.createdAt,
  });

  final String id;
  final String action;

  final String? actorId;

  final String? target;
  final Map<String, Object?> details;
  final DateTime? createdAt;
}
