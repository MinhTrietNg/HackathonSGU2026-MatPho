import 'dart:io' show Platform;

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart' show debugPrint, kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'data/providers.dart';
import 'data/remote/core/api_config.dart';
import 'data/remote/core/remote_providers.dart';
import 'data/services/local_notification_service.dart';
import 'data/services/push_background.dart';
import 'data/services/push_inbox.dart';
import 'data/services/push_source.dart';
import 'data/session/push_token_source.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  } catch (_) {}

  bool firebaseReady = false;
  if (!kIsWeb && (Platform.isAndroid || Platform.isIOS)) {
    try {
      await Firebase.initializeApp();
      FirebaseMessaging.onBackgroundMessage(pushBackgroundHandler);
      firebaseReady = true;
    } catch (e, st) {
      debugPrint('[Firebase] Warning: Failed to initialize Firebase: $e\n$st');
    }
  }

  final notifications = LocalNotificationService();
  try {
    await notifications.init();
  } catch (e, st) {
    debugPrint('[Notifications] Warning: Failed to init notifications: $e\n$st');
  }

  ApiConfig apiConfig;
  try {
    apiConfig = await ApiConfig.resolveActive();
  } catch (e) {
    debugPrint('[ApiConfig] Warning: Failed to resolve ApiConfig: $e');
    apiConfig = const ApiConfig.fromEnvironment();
  }

  runApp(
    ProviderScope(
      overrides: [
        apiConfigProvider.overrideWithValue(apiConfig),
        notificationServiceProvider.overrideWithValue(notifications),
        pushTokenSourceProvider.overrideWithValue(
          firebaseReady ? FirebasePushTokenSource() : const NoPushTokenSource(),
        ),
        pushMessageSourceProvider.overrideWithValue(
          firebaseReady ? FirebasePushMessageSource() : const NoPushMessageSource(),
        ),
      ],
      child: const MatPhoApp(),
    ),
  );
}
