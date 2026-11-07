import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import 'alert_screen.dart';
import 'call_screen.dart';
import 'dialer_screen.dart';

abstract final class AlertPaths {
  static String dialer(String eventId) => '${AppRoutes.alert(eventId)}/dial';

  static String call(String eventId) => '${AppRoutes.alert(eventId)}/call';
}

final alertRoutes = <RouteBase>[
  GoRoute(
    path: AppRoutes.alert(':eventId'),
    builder: (context, state) =>
        AlertScreen(eventId: state.pathParameters['eventId']!),
    routes: [
      GoRoute(
        path: 'dial',
        builder: (context, state) =>
            DialerScreen(eventId: state.pathParameters['eventId']!),
      ),
      GoRoute(
        path: 'call',
        builder: (context, state) =>
            CallScreen(eventId: state.pathParameters['eventId']!),
      ),
    ],
  ),
];
