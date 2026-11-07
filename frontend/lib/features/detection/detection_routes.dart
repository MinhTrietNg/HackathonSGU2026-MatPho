import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import 'watch_full_screen.dart';
import 'watch_screen.dart';

abstract final class DetectionPaths {
  static String fullScreen(String cameraId) =>
      '${AppRoutes.watch(cameraId)}/full';
}

final detectionRoutes = <RouteBase>[
  GoRoute(
    path: 'watch/:cameraId',
    builder: (context, state) =>
        WatchScreen(cameraId: state.pathParameters['cameraId']!),
    routes: [
      GoRoute(
        path: 'full',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) =>
            WatchFullScreen(cameraId: state.pathParameters['cameraId']!),
      ),
    ],
  ),
];
