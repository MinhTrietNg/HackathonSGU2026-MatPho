import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/providers.dart';
import '../../features/ai_mode/ai_mode_routes.dart';
import '../../features/alert/alert_listener.dart';
import '../../features/alert/alert_routes.dart';
import '../../features/auth/auth_routes.dart';
import '../../features/cameras/camera_monitor_screen.dart';
import '../../features/cameras/camera_routes.dart';
import '../../features/detection/detection_routes.dart';
import '../../features/groups/group_routes.dart';
import '../../features/history/history_routes.dart';
import '../../features/history/history_screen.dart';
import '../../features/settings/settings_routes.dart';
import '../../features/settings/settings_screen.dart';
import '../widgets/mp_tab_bar.dart';

abstract final class AppRoutes {
  static const monitor = '/monitor';
  static const history = '/history';
  static const settings = '/settings';

  static const splash = '/splash';
  static const login = '/login';

  static String watch(String cameraId) => '/monitor/watch/$cameraId';

  static String alert(String eventId) => '/alert/$eventId';

  static String historyDetail(String eventId) => '/history/$eventId';

  static const addCamera = '/monitor/cameras/add';

  static String signalLost(String cameraId) => '/monitor/cameras/$cameraId';
}

final rootNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'root');

final appRouterProvider = Provider<GoRouter>((ref) {
  final notifSvc = ref.read(notificationServiceProvider);
  final launchAlertId = notifSvc.launchAlertId;
  // Mở từ nút "Gọi 114" của thông báo: vào màn sự cố, AlertNotifications gọi 114 thật
  // (không qua màn quay số mô phỏng, vốn không gọi và còn đánh dấu sự cố đã xử lý).
  final router = GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: launchAlertId != null
        ? AppRoutes.alert(launchAlertId)
        : AppRoutes.monitor,
    redirect: (context, state) => authRedirect(ref, state),
    routes: [
      ...authRoutes,
      ...alertRoutes,
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => _TabShell(shell: shell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.monitor,
                builder: (context, state) => const CameraMonitorScreen(),
                routes: [...detectionRoutes, ...cameraSubRoutes],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.history,
                builder: (context, state) => const HistoryScreen(),
                routes: historySubRoutes,
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.settings,
                builder: (context, state) => const SettingsScreen(),
                routes: [
                  ...settingsSubRoutes,
                  ...groupSubRoutes,
                  ...aiModeSubRoutes,
                ],
              ),
            ],
          ),
        ],
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});

class _TabShell extends StatelessWidget {
  const _TabShell({required this.shell});

  final StatefulNavigationShell shell;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: AlertListener(child: shell),
      bottomNavigationBar: MpTabBar(
        currentIndex: shell.currentIndex,
        // Re-tapping the active tab pops its stack back to the root.
        onTap: (i) =>
            shell.goBranch(i, initialLocation: i == shell.currentIndex),
      ),
    );
  }
}
