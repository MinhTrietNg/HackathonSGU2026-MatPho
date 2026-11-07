import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:mat_pho/app.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/services/local_notification_service.dart';
import 'package:mat_pho/data/services/notification_service.dart';
import 'package:mat_pho/data/services/phone_dialer.dart';

import '../fakes/fake_overrides.dart';
import '../fakes/fake_scenario.dart';

// Chạy app bằng backend giả trong RAM, không Firebase, không gọi mạng:
//   flutter run -t test/mock/main.dart
//   flutter run -t test/mock/main.dart --dart-define=MOCK_CASES=noCameras,historyEmpty
// MOCK_CASES là tên các FakeCase, cách nhau bằng dấu phẩy. Mặc định: signedOut.
// Tính năng của máy (gọi điện, mở cài đặt, thông báo) là thật, trừ khi
// MOCK_CASES có notificationsDenied hoặc notificationsNotDetermined thì
// thông báo vẫn giả để xem được các trạng thái quyền.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  final cases = mockCases();
  final devices = await deviceOverrides(cases);
  runApp(
    ProviderScope(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(FakeScenario(cases: cases)),
        ...devices,
      ]),
      child: const MatPhoApp(),
    ),
  );
}

Set<FakeCase> mockCases([
  String raw = const String.fromEnvironment(
    'MOCK_CASES',
    defaultValue: 'signedOut',
  ),
]) {
  final byName = {for (final c in FakeCase.values) c.name: c};
  return {
    for (final name in raw.split(',').map((s) => s.trim()))
      if (name.isNotEmpty)
        byName[name] ??
            (throw ArgumentError.value(
              name,
              'MOCK_CASES',
              'Không có FakeCase này',
            )),
  };
}

Future<List<Override>> deviceOverrides(
  Set<FakeCase> cases, {
  Future<NotificationService> Function() notifications = _localNotifications,
}) async {
  final fakeNotifications =
      cases.contains(FakeCase.notificationsDenied) ||
      cases.contains(FakeCase.notificationsNotDetermined);
  return [
    phoneDialerProvider.overrideWithValue(const SystemPhoneDialer()),
    if (!fakeNotifications)
      notificationServiceProvider.overrideWithValue(await notifications()),
  ];
}

Future<NotificationService> _localNotifications() async {
  final service = LocalNotificationService();
  await service.init();
  return service;
}
