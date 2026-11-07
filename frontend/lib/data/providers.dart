library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'models/models.dart';
import 'remote/alert_remote.dart';
import 'remote/auth_remote.dart';
import 'remote/camera_remote.dart';
import 'remote/detection_remote.dart';
import 'remote/group_remote.dart';
import 'remote/history_remote.dart';
import 'remote/settings_remote.dart';
import 'repositories/repositories.dart';
import 'services/local_notification_service.dart';
import 'services/notification_service.dart';
import 'services/phone_dialer.dart';

final clockProvider = Provider<DateTime Function()>((ref) => DateTime.now);

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => ref.watch(remoteAuthRepositoryProvider),
);

final detectionRepositoryProvider = Provider<DetectionRepository>(
  (ref) => ref.watch(remoteDetectionRepositoryProvider),
);

final alertRepositoryProvider = Provider<AlertRepository>(
  (ref) => ref.watch(remoteAlertRepositoryProvider),
);

final historyRepositoryProvider = Provider<HistoryRepository>(
  (ref) => ref.watch(remoteHistoryRepositoryProvider),
);

final settingsRepositoryProvider = Provider<SettingsRepository>(
  (ref) => ref.watch(remoteSettingsRepositoryProvider),
);

final cameraRepositoryProvider = Provider<CameraRepository>(
  (ref) => ref.watch(remoteCameraRepositoryProvider),
);

final groupRepositoryProvider = Provider<GroupRepository>(
  (ref) => ref.watch(remoteGroupRepositoryProvider),
);

final notificationServiceProvider = Provider<NotificationService>(
  (ref) => LocalNotificationService(),
);

final phoneDialerProvider = Provider<PhoneDialer>(
  (ref) => const SystemPhoneDialer(),
);

final cameraFeedProvider = Provider.family<FeedSource?, Camera>((ref, camera) {
  final url = camera.liveStreamUrl;
  return url == null ? null : networkFeed(url);
});

final cameraStillProvider = Provider.family<String?, String>(
  (ref, cameraId) => null,
);

final eventStillProvider =
    Provider.family<String?, ({String cameraId, DetectedSign? sign})>(
      (ref, event) => null,
    );
