import 'package:flutter/foundation.dart';

import '../../core/time_format.dart';
import '../models/fire_event.dart';
import '../models/settings.dart';

abstract interface class NotificationService {
  Future<NotificationPermission> status();

  Future<NotificationPermission> request();

  Future<void> openSystemSettings();

  Future<void> showFireAlert(FireEvent alert, {Uint8List? picture});

  Future<void> showGenericFireAlert(String eventId);

  Future<void> clearFireAlerts();

  Future<void> clearFireAlert(String eventId);

  Future<void> stopSiren();

  Future<void> showTestAlert();

  Stream<AlertTap> get taps;

  String? get launchAlertId;

  bool get launchCall114;
}

const fireAlertChannelId = 'fire_alarms_v2';
const legacyFireAlertChannelId = 'fire_alerts';
const fireAlertChannelName = 'Cảnh báo cháy';

String fireAlertTitle(FireEvent alert) => alert.status == EventStatus.unverified
    ? 'Có thể có khói ở ${alert.locationName}'
    : 'Có cháy · ${alert.locationName}';

String fireAlertBody(FireEvent alert) => alert.status == EventStatus.unverified
    ? 'Chưa kiểm tra lại được. Chạm để xem ảnh.'
    : 'Phát hiện lửa lúc ${formatClock(alert.detectedAt, seconds: false)}. '
          'Chạm để xem ảnh.';

const genericFireAlertTitle = 'Cảnh báo cháy';
const genericFireAlertBody = 'Chạm để xem ảnh.';

typedef AlertTap = ({String eventId, bool call114});

const testAlertTitle = 'THỬ · Cảnh báo cháy';
const testAlertBody = 'Thông báo thử, không có cháy.';
