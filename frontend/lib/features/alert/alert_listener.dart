library;

import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/widgets/mp_banner.dart';
import '../../data/models/fire_event.dart';
import '../../data/providers.dart';
import '../auth/auth_session.dart';

class AlertListener extends ConsumerStatefulWidget {
  const AlertListener({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<AlertListener> createState() => _AlertListenerState();
}

// In-app fire alerts (WebSocket FIRE_ALERT, or a push while the app is open):
// F6 banner on other tabs; nothing when F2 or that camera's E2 is already open.
class _AlertListenerState extends ConsumerState<AlertListener> {
  StreamSubscription<FireEvent>? _subscription;
  StreamSubscription<AlertUpdate>? _updates;

  String? _bannerEventId;

  @override
  void initState() {
    super.initState();
    ref.listenManual(sessionUserIdProvider, (_, userId) {
      _subscription?.cancel();
      _updates?.cancel();
      final repository = ref.read(alertRepositoryProvider);
      _subscription = userId == null
          ? null
          : repository.incomingAlerts().listen(_onAlert);
      _updates = userId == null
          ? null
          : repository.alertUpdates().listen(_onClosed);
    }, fireImmediately: true);
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _updates?.cancel();
    super.dispose();
  }

  void _onAlert(FireEvent event) {
    if (!mounted) return;
    final router = GoRouter.maybeOf(context);
    final path = router?.state.uri.path ?? '';
    final watch = AppRoutes.watch(event.cameraId);
    if (path.startsWith(AppRoutes.alert('')) ||
        path == watch ||
        path.startsWith('$watch/')) {
      return;
    }
    unawaited(HapticFeedback.vibrate());
    final where = event.locationName;
    final unverified = event.status == EventStatus.unverified;
    _bannerEventId = event.id;
    showMpAlertBanner(
      context,
      MpAlertBanner(
        title: unverified ? 'Có thể có khói ở $where' : 'Cháy · $where',
        subtitle: unverified ? 'chạm để xem' : '${event.summary} · chạm để xem',
        onTap: () {
          unawaited(ref.read(notificationServiceProvider).clearFireAlert(event.id));
          router?.push<void>(AppRoutes.alert(event.id));
        },
      ),
    );
  }

  void _onClosed(AlertUpdate update) {
    unawaited(
      ref.read(notificationServiceProvider).clearFireAlert(update.eventId),
    );
    if (_bannerEventId == update.eventId) {
      _bannerEventId = null;
      hideMpAlertBanner();
    }
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
