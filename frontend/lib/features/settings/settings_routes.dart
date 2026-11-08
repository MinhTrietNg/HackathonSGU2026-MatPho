import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import 'camera_trash_screen.dart';
import 'change_password_screen.dart';
import 'test_alert_screen.dart';

abstract final class SettingsRoutes {
  static const testAlert = '${AppRoutes.settings}/test-alert';

  static const changePassword = '${AppRoutes.settings}/password';

  static const cameraTrash = '${AppRoutes.settings}/camera-trash';
}

final settingsSubRoutes = <RouteBase>[
  GoRoute(
    path: 'camera-trash',
    parentNavigatorKey: rootNavigatorKey,
    builder: (context, state) => const CameraTrashScreen(),
  ),
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
