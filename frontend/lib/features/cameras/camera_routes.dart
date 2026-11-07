import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../data/errors.dart';
import 'add_camera_screen.dart';
import 'camera_screen.dart';
import 'camera_state.dart';
import 'connect_error_screen.dart';
import 'name_camera_screen.dart';

abstract final class CameraRoutes {
  static const add = AppRoutes.addCamera;

  static const connectError = '$add/error';

  static const name = '$add/name';

  static String signalLost(String cameraId) => AppRoutes.signalLost(cameraId);
}

final cameraSubRoutes = <RouteBase>[
  GoRoute(
    path: 'cameras/add',
    parentNavigatorKey: rootNavigatorKey,
    builder: (context, state) => const AddCameraScreen(),
    routes: [
      GoRoute(
        path: 'error',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const ConnectErrorScreen(),
      ),
      GoRoute(
        path: 'name',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const NameCameraScreen(),
      ),
    ],
  ),
  GoRoute(
    path: 'cameras/:cameraId',
    parentNavigatorKey: rootNavigatorKey,
    builder: (context, state) =>
        CameraScreen(cameraId: state.pathParameters['cameraId']!),
  ),
];

Future<void> enterMonitor(
  BuildContext context,
  WidgetRef ref, {
  bool addCamera = false,
}) async {
  final router = GoRouter.of(context);
  final flow = ref.read(addCameraProvider.notifier);
  var add = false;
  try {
    final place = await ref.read(currentPlaceProvider.future);
    if (place.myRole.canManage) {
      add = addCamera || (await ref.read(placeCamerasProvider.future)).isEmpty;
    }
  } on MpException {
    add = false;
  }
  if (add) {
    flow.start();
    router.go(CameraRoutes.add);
  } else {
    router.go(AppRoutes.monitor);
  }
}
