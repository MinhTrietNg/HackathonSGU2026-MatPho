import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
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

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  await Firebase.initializeApp();
  FirebaseMessaging.onBackgroundMessage(pushBackgroundHandler);
  final notifications = LocalNotificationService();
  await notifications.init();
  final apiConfig = await ApiConfig.resolveActive();
  runApp(
    ProviderScope(
      overrides: [
        apiConfigProvider.overrideWithValue(apiConfig),
        notificationServiceProvider.overrideWithValue(notifications),
        pushTokenSourceProvider.overrideWithValue(FirebasePushTokenSource()),
        pushMessageSourceProvider.overrideWithValue(
          FirebasePushMessageSource(),
        ),
      ],
      child: const MatPhoApp(),
    ),
  );
}
