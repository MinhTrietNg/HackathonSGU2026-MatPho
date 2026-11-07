library;

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show ProviderListenable;

import '../models/fire_event.dart';
import '../providers.dart';
import '../remote/core/remote_providers.dart';
import '../repositories/alert_repository.dart';
import '../session/emergency_token_store.dart';
import 'local_notification_service.dart';
import 'notification_service.dart';
import 'push_message.dart';
import 'push_source.dart';

// Runs in its own isolate with its own ProviderContainer, so repositories must
// be wired in provider defaults (providers.dart), not in main.dart overrides.
@pragma('vm:entry-point')
Future<void> pushBackgroundHandler(RemoteMessage message) async {
  final data = message.data;
  if (FirebasePushMessageSource.deliverInAppIsolate(data)) return;

  WidgetsFlutterBinding.ensureInitialized();
  try {
    if (Firebase.apps.isEmpty) await Firebase.initializeApp();
  } on Object catch (error) {
    debugPrint('Firebase unavailable in the background: ${error.runtimeType}');
  }
  final notifications = LocalNotificationService();
  await notifications.init();
  final container = ProviderContainer();
  try {
    await handleBackgroundPush(
      data,
      notifications: notifications,
      alerts: _read(container, alertRepositoryProvider),
      signedIn: () => _signedIn(container),
      relay: FirebasePushMessageSource.relayFromBackground,
    );
  } finally {
    container.dispose();
  }
}

Future<void> handleBackgroundPush(
  Map<String, Object?> data, {
  required NotificationService notifications,
  required Future<bool> Function() signedIn,
  AlertRepository? alerts,
  void Function(Map<String, String> data)? relay,
}) async {
  final message = PushMessage.decode(data);
  switch (message) {
    case null:
      return;
    case FireAlertPush(:final alertId, :final emergencyToken):
      if (emergencyToken != null) {
        EmergencyTokenStore.instance.save(alertId, emergencyToken);
      }
      if (!await signedIn() && emergencyToken == null) return;
      await showPushedFireAlert(
        alertId,
        notifications: notifications,
        alerts: alerts,
      );
    case FireAlertUpdatedPush(:final alertId):
      await notifications.clearFireAlert(alertId);
    case TestAlertPush() ||
        InvitationPush() ||
        RoleChangedPush() ||
        CameraOfflinePush():
      break;
  }
  relay?.call({
    for (final MapEntry(:key, :value) in data.entries)
      if (value != null) key: '$value',
  });
}

Future<void> showPushedFireAlert(
  String alertId, {
  required NotificationService notifications,
  AlertRepository? alerts,
  Duration timeout = const Duration(seconds: 10),
}) async {
  FireEvent? event;
  if (alerts != null) {
    try {
      event = await alerts.getAlert(alertId).timeout(timeout);
    } on Object catch (error) {
      debugPrint('Fire alert $alertId not fetched: ${error.runtimeType}');
    }
  }
  if (event == null) return notifications.showGenericFireAlert(alertId);
  final rings =
      !event.resolved &&
      (event.status == EventStatus.fire ||
          event.status == EventStatus.unverified);
  if (rings) await notifications.showFireAlert(event);
}

T? _read<T>(ProviderContainer container, ProviderListenable<T> provider) {
  try {
    return container.read(provider);
  } on Object catch (error) {
    debugPrint('Background push: ${error.runtimeType}');
    return null;
  }
}

Future<bool> _signedIn(ProviderContainer container) async {
  try {
    if (await container.read(sessionStoreProvider).read() != null) return true;
  } on Object {
    // Fall through to Firebase.
  }
  try {
    return container.read(authTokenSourceProvider).isSignedIn;
  } on Object {
    return true;
  }
}
