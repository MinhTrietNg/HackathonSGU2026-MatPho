import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import 'ai_camera_screen.dart';
import 'ai_cameras_screen.dart';

abstract final class AiModeRoutes {
  static const cameras = '${AppRoutes.settings}/ai';

  static String camera(String cameraId) => '$cameras/$cameraId';
}

final aiModeSubRoutes = <RouteBase>[
  GoRoute(
    path: 'ai',
    parentNavigatorKey: rootNavigatorKey,
    builder: (context, state) => const AiCamerasScreen(),
    routes: [
      GoRoute(
        path: ':cameraId',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) =>
            AiCameraScreen(cameraId: state.pathParameters['cameraId']!),
      ),
    ],
  ),
];
