import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/providers.dart';
import '../../features/auth/auth_routes.dart';
import '../../features/cameras/camera_monitor_screen.dart';
import '../../features/cameras/camera_routes.dart';
import '../../features/groups/group_routes.dart';
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
  final launchAlertId = ref.read(notificationServiceProvider).launchAlertId;
  final router = GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: launchAlertId != null
        ? AppRoutes.alert(launchAlertId)
        : AppRoutes.monitor,
    redirect: (context, state) => authRedirect(ref, state),
    routes: [
      ...authRoutes,
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => _TabShell(shell: shell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.monitor,
                builder: (context, state) => const CameraMonitorScreen(),
                routes: cameraSubRoutes,
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.history,
                builder: (context, state) => const SizedBox.shrink(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.settings,
                builder: (context, state) => const SettingsScreen(),
                routes: [...settingsSubRoutes, ...groupSubRoutes],
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
      body: shell,
      bottomNavigationBar: MpTabBar(
        currentIndex: shell.currentIndex,
        // Re-tapping the active tab pops its stack back to the root.
        onTap: (i) =>
            shell.goBranch(i, initialLocation: i == shell.currentIndex),
      ),
    );
  }
}
