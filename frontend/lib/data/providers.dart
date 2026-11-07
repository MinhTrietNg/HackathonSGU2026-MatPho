library;

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/painting.dart';
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

typedef CameraThumbnail = ({Uint8List png, String? url});

// Frames captured on leaving the live view this session: shown at once,
// uploaded in the background; a failed upload keeps the picture here only.
class CameraThumbnailsNotifier extends Notifier<Map<String, CameraThumbnail>> {
  @override
  Map<String, CameraThumbnail> build() => const {};

  void capture(String cameraId, Uint8List png) {
    state = {...state, cameraId: (png: png, url: null)};
    unawaited(_upload(cameraId, png));
  }

  Future<void> _upload(String cameraId, Uint8List png) async {
    try {
      final url = await ref
          .read(cameraRepositoryProvider)
          .uploadThumbnail(cameraId, png);
      if (!ref.mounted || state[cameraId]?.png != png) return;
      state = {...state, cameraId: (png: png, url: url)};
    } on Object {
      // Silent by design.
    }
  }
}

final cameraThumbnailsProvider =
    NotifierProvider<CameraThumbnailsNotifier, Map<String, CameraThumbnail>>(
      CameraThumbnailsNotifier.new,
    );

final cameraStillProvider = Provider.family<ImageProvider?, Camera>((
  ref,
  camera,
) {
  final png = ref.watch(
    cameraThumbnailsProvider.select((t) => t[camera.id]?.png),
  );
  if (png != null) return MemoryImage(png);
  final url = camera.thumbnailUrl;
  return url == null ? null : NetworkImage(url);
});

final eventStillProvider =
    Provider.family<String?, ({String cameraId, DetectedSign? sign})>(
      (ref, event) => null,
    );
