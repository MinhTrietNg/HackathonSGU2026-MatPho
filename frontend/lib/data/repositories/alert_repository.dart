import '../models/fire_event.dart';
import '../models/incident.dart';

abstract interface class AlertRepository {
  Stream<FireEvent> incomingAlerts();

  Stream<AlertUpdate> alertUpdates();

  Future<FireEvent> getAlert(String eventId);

  Future<FireEvent> recordCall114(String eventId);

  Future<FireEvent> resolve(String eventId);

  Future<FireEvent> markFalseAlarm(String eventId);

  Future<FireEvent> reportRealFire(String eventId);

  Future<EscalationStatus> escalationStatus(String eventId);

  Future<DispatchInfo> dispatchInfo(String eventId);

  Future<List<AuditEntry>> auditLog(String eventId);
}
