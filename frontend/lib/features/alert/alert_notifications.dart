import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/router/app_router.dart';
import '../../data/models/fire_event.dart';
import '../../data/providers.dart';
import '../../data/services/notification_service.dart';
import '../../data/services/push_background.dart' show showPushedFireAlert;
import '../../data/services/push_inbox.dart';
import '../../data/services/push_message.dart';
import '../../data/services/push_token_registrar.dart';
import '../../data/session/emergency_token_store.dart';
import '../auth/auth_session.dart';
import '../auth/permission_controller.dart';
import '../groups/current_group.dart' show currentGroupIdProvider;
import '../groups/group_routes.dart';
import '../groups/group_state.dart'
    show groupActionsProvider, myInvitationsProvider;
import 'alert_actions.dart';
import 'alert_controller.dart' show alertProvider;

class AlertNotifications extends ConsumerStatefulWidget {
  const AlertNotifications({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<AlertNotifications> createState() => _AlertNotificationsState();
}

class _AlertNotificationsState extends ConsumerState<AlertNotifications> {
  late final AppLifecycleListener _lifecycle;
  late final PushTokenRegistrar _registrar;
  StreamSubscription<FireEvent>? _alerts;
  StreamSubscription<AlertTap>? _taps;
  final _pushes = <StreamSubscription<PushMessage>>[];

  final _ringing = <String>[];

  @override
  void initState() {
    super.initState();
    _registrar = ref.read(pushTokenRegistrarProvider);
    ref.listenManual(sessionUserIdProvider, (_, userId) {
      _alerts?.cancel();
      _alerts = null;
      _ringing.clear();
      if (userId == null) {
        _registrar.stop();
        return;
      }
      unawaited(_registrar.start());
      _alerts = ref
          .read(alertRepositoryProvider)
          .incomingAlerts()
          .listen(_onAlert);
    }, fireImmediately: true);
    _taps = ref.read(notificationServiceProvider).taps.listen(_onTap);
    final inbox = ref.read(pushInboxProvider);
    _pushes
      ..add(inbox.received.listen(_onPush))
      ..add(inbox.handledInBackground.listen(_onBackgroundPush))
      ..add(inbox.opened.listen(_onOpenedPush));
    unawaited(
      inbox.initialOpened().then((push) {
        if (push != null && mounted) unawaited(_onOpenedPush(push));
      }),
    );
    _lifecycle = AppLifecycleListener(onResume: _onResume);
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    _alerts?.cancel();
    _taps?.cancel();
    for (final s in _pushes) {
      s.cancel();
    }
    _registrar.stop();
    super.dispose();
  }

  bool get _inForeground {
    final lifecycle = WidgetsBinding.instance.lifecycleState;
    return lifecycle == null || lifecycle == AppLifecycleState.resumed;
  }

  bool get _signedIn => ref.read(sessionUserIdProvider) != null;

  Future<void> _onAlert(FireEvent event) async {
    if (event.status != EventStatus.fire &&
        event.status != EventStatus.unverified) {
      return;
    }
    _ring(event.id);
    final notifications = ref.read(notificationServiceProvider);
    await notifications.showFireAlert(event, picture: await _picture(event));
    if (_inForeground) {
      await _openAlert(event.id, clearNotification: false);
    }
  }

  void _ring(String eventId) => _ringing
    ..remove(eventId)
    ..add(eventId);

  Future<void> _onPush(PushMessage push) async {
    if (push is FireAlertPush && push.emergencyToken != null) {
      EmergencyTokenStore.instance.save(push.alertId, push.emergencyToken!);
    }
    if (!_signedIn && push is! FireAlertPush) return;
    switch (push) {
      case FireAlertPush(:final alertId):
        _ring(alertId);
        await showPushedFireAlert(
          alertId,
          notifications: ref.read(notificationServiceProvider),
          alerts: ref.read(alertRepositoryProvider),
        );
        if (_inForeground) {
          await _openAlert(alertId, clearNotification: false);
        }
      case FireAlertUpdatedPush(:final alertId):
        await _alertUpdated(alertId);
      case InvitationPush():
        ref.invalidate(myInvitationsProvider);
      case RoleChangedPush(:final groupId):
        ref.read(groupActionsProvider).roleChanged(groupId);
      case TestAlertPush() || CameraOfflinePush():
        break;
    }
  }

  void _onBackgroundPush(PushMessage push) {
    if (push is FireAlertPush && push.emergencyToken != null) {
      EmergencyTokenStore.instance.save(push.alertId, push.emergencyToken!);
    }
    if (!_signedIn && push is! FireAlertPush) return;
    switch (push) {
      case FireAlertPush(:final alertId):
        _ring(alertId);
      case FireAlertUpdatedPush(:final alertId):
        unawaited(_alertUpdated(alertId));
      case InvitationPush():
        ref.invalidate(myInvitationsProvider);
      case RoleChangedPush(:final groupId):
        ref.read(groupActionsProvider).roleChanged(groupId);
      case TestAlertPush() || CameraOfflinePush():
        break;
    }
  }

  Future<void> _alertUpdated(String alertId) async {
    _ringing.remove(alertId);
    await ref.read(notificationServiceProvider).clearFireAlert(alertId);
    if (!mounted) return;
    ref.invalidate(alertProvider(alertId));
  }

  Future<void> _onOpenedPush(PushMessage push) async {
    await WidgetsBinding.instance.endOfFrame;
    if (!mounted) return;
    final router = ref.read(appRouterProvider);
    void open(String path) {
      if (router.state.uri.path != path) unawaited(router.push<void>(path));
    }

    switch (push) {
      case FireAlertPush(:final alertId, :final emergencyToken):
        if (emergencyToken != null) {
          EmergencyTokenStore.instance.save(alertId, emergencyToken);
        }
        await _openAlert(alertId);
      case FireAlertUpdatedPush(:final alertId):
        await _openAlert(alertId);
      case InvitationPush(:final invitationId):
        open(GroupRoutes.invitation(invitationId));
      case RoleChangedPush(:final groupId):
        ref.read(currentGroupIdProvider.notifier).select(groupId);
        open(GroupRoutes.members);
      case CameraOfflinePush(:final cameraId):
        open(AppRoutes.signalLost(cameraId));
      case TestAlertPush():
        break;
    }
  }

  Future<Uint8List?> _picture(FireEvent event) async {
    final asset = ref.read(
      eventStillProvider((cameraId: event.cameraId, sign: event.sign)),
    );
    if (asset == null) return null;
    try {
      return (await rootBundle.load(asset)).buffer.asUint8List();
    } on Object {
      return null;
    }
  }

  void _onResume() {
    ref.read(notificationPermissionProvider.notifier).refresh();
    if (_ringing.isNotEmpty) {
      unawaited(_openAlert(_ringing.last, clearNotification: false));
    }
  }

  Future<void> _onTap(AlertTap tap) async {
    await _openAlert(tap.eventId, clearNotification: true);
    if (!tap.call114 || !mounted) return;
    final host = ref.read(appRouterProvider).routerDelegate.navigatorKey;
    final context = host.currentContext;
    if (context != null && context.mounted) {
      await dial114(context, ref, tap.eventId);
    }
  }

  Future<void> _openAlert(String eventId, {bool clearNotification = true}) async {
    _ringing.remove(eventId);
    if (clearNotification) {
      unawaited(ref.read(notificationServiceProvider).clearFireAlert(eventId));
    }
    await WidgetsBinding.instance.endOfFrame;
    if (!mounted) return;
    final router = ref.read(appRouterProvider);
    final path = AppRoutes.alert(eventId);
    if (router.state.uri.path == path) return;
    unawaited(router.push<void>(path));
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
