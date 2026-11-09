import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/widgets/mp_banner.dart';
import '../../core/widgets/mp_toast.dart';
import '../../data/errors.dart';
import '../../data/providers.dart';
import '../../data/services/phone_dialer.dart';
import '../cameras/camera_state.dart'
    show CameraDetail, cameraDetailProvider, noLiveViewNote;
import '../cameras/monitor_toasts.dart';
import '../detection/detection_routes.dart' show DetectionPaths;
import 'alert_controller.dart' show AlertClosing, alertProvider, alertStillOpen;
import 'pending_alert_actions.dart';

export 'pending_alert_actions.dart' show AlertOutcome;

const cameraUnavailableNote = 'Không mở được camera. Kiểm tra kết nối rồi thử lại.';

Future<void> dial114(
  BuildContext context,
  WidgetRef ref,
  String eventId,
) async {
  // Immediately silence siren sound and stop device vibration
  unawaited(ref.read(notificationServiceProvider).clearFireAlerts());
  final repository = ref.read(alertRepositoryProvider);
  // No siren over the call to 114.
  unawaited(ref.read(notificationServiceProvider).clearFireAlert(eventId));
  if (!await callEmergency(context, ref)) return;
  try {
    await repository.recordCall114(eventId);
  } on MpException {
    // Only G1's mark is lost; the call itself went ahead.
  }
}

Future<bool> callEmergency(BuildContext context, WidgetRef ref) async {
  // Immediately silence siren sound and stop device vibration
  unawaited(ref.read(notificationServiceProvider).clearFireAlerts());
  final opened = await ref.read(phoneDialerProvider).dial(emergencyNumber);
  if (!opened && context.mounted) {
    showMpToast(
      context,
      const MpToast(
        title: 'Máy này không gọi được. Hãy gọi 114 bằng máy khác.',
      ),
    );
  }
  return opened;
}

class AlertToasts {
  const AlertToasts();

  void resolved(
    BuildContext context, {
    required String locationName,
    VoidCallback? onUndo,
  }) =>
      showResolvedToastFor(context, locationName: locationName, onUndo: onUndo);

  void falseAlarm(
    BuildContext context, {
    required String locationName,
    required VoidCallback onUndo,
  }) => showFalseAlarmToastFor(
    context,
    locationName: locationName,
    onUndo: onUndo,
  );
}

final alertToastsProvider = Provider<AlertToasts>((ref) => const AlertToasts());

Future<void> closeAlert(
  BuildContext context,
  WidgetRef ref,
  String eventId,
  AlertOutcome outcome,
) async {
  final alert = ref.read(alertProvider(eventId)).value;
  if (alert == null || alert.closing != AlertClosing.allowed) return;
  final router = GoRouter.of(context);
  final toasts = ref.read(alertToastsProvider);
  final notifications = ref.read(notificationServiceProvider);
  final pending = ref.read(pendingAlertActionsProvider.notifier);
  final where = alert.event.locationName;
  unawaited(notifications.clearFireAlert(eventId));
  hideMpAlertBanner();
  pending.schedule(eventId, outcome);
  router.go(AppRoutes.monitor);
  void undo() {
    if (pending.cancel(eventId)) router.push(AppRoutes.alert(eventId));
  }

  WidgetsBinding.instance.addPostFrameCallback((_) {
    final host = router.routerDelegate.navigatorKey.currentContext;
    if (host == null || !host.mounted) return;
    switch (outcome) {
      case AlertOutcome.resolved:
        toasts.resolved(host, locationName: where, onUndo: undo);
      case AlertOutcome.falseAlarm:
        toasts.falseAlarm(host, locationName: where, onUndo: undo);
    }
  });
}

Future<void> openEventCamera(
  BuildContext context,
  WidgetRef ref,
  String eventId,
) async {
  final router = GoRouter.of(context);
  final CameraDetail detail;
  final String cameraId;
  try {
    // The alert on screen already names its camera; fetch only without it.
    cameraId =
        ref.read(alertProvider(eventId)).value?.event.cameraId ??
        (await ref.read(alertRepositoryProvider).getAlert(eventId)).cameraId;
    final provider = cameraDetailProvider(cameraId);
    final hold = ref.listenManual(provider, (_, _) {});
    try {
      detail = await ref.read(provider.future);
    } finally {
      hold.close();
    }
  } on MpException {
    if (context.mounted) {
      showMpToast(context, const MpToast(title: cameraUnavailableNote));
    }
    return;
  }
  if (!detail.group.myRole.canWatch) {
    if (context.mounted) {
      showMpToast(context, const MpToast(title: noLiveViewNote));
    }
    return;
  }
  final watch = AppRoutes.watch(cameraId);
  // An alert still to be handled keeps ringing: the camera opens full screen
  // (E8, on the root navigator) over F2, so × returns to its "Gọi 114" /
  // "Đã xử lý" / "Báo nhầm". The shell's E2 cannot be pushed over F2.
  if (ref.read(alertProvider(eventId)).value?.event case final event?
      when alertStillOpen(event)) {
    unawaited(router.push<void>(DetectionPaths.fullScreen(cameraId)));
    return;
  }
  if (!_inStack(router.routerDelegate.currentConfiguration.matches, watch)) {
    router.go(watch);
    return;
  }
  while (router.state.uri.path != watch && router.canPop()) {
    router.pop();
  }
}

bool _inStack(List<RouteMatchBase> matches, String location) {
  for (final match in matches) {
    final found = switch (match) {
      ImperativeRouteMatch(matches: final pushed) => _inStack(
        pushed.matches,
        location,
      ),
      ShellRouteMatch(matches: final inner) => _inStack(inner, location),
      _ => match.matchedLocation == location,
    };
    if (found) return true;
  }
  return false;
}

void popOrGo(BuildContext context, String location) {
  final router = GoRouter.of(context);
  if (router.canPop()) {
    router.pop();
  } else {
    router.go(location);
  }
}
