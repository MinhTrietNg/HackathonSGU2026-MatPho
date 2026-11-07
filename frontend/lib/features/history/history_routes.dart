import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import 'history_detail_screen.dart';

final historySubRoutes = <RouteBase>[
  GoRoute(
    path: ':eventId',
    parentNavigatorKey: rootNavigatorKey,
    builder: (context, state) =>
        HistoryDetailScreen(eventId: state.pathParameters['eventId']!),
  ),
];
