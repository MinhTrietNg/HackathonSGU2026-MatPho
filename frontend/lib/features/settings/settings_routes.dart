import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import 'change_password_screen.dart';
import 'test_alert_screen.dart';

abstract final class SettingsRoutes {
  static const testAlert = '${AppRoutes.settings}/test-alert';

  static const changePassword = '${AppRoutes.settings}/password';
}

final settingsSubRoutes = <RouteBase>[
  GoRoute(
    path: 'test-alert',
    parentNavigatorKey: rootNavigatorKey,
    builder: (context, state) => const TestAlertScreen(),
  ),
  GoRoute(
    path: 'password',
    parentNavigatorKey: rootNavigatorKey,
    builder: (context, state) => const ChangePasswordScreen(),
  ),
];
