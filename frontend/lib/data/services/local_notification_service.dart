import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show MethodChannel;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../core/theme/mp_colors.dart';
import '../models/fire_event.dart';
import '../models/settings.dart';
import 'notification_service.dart';

final class LocalNotificationService implements NotificationService {
  final _plugin = FlutterLocalNotificationsPlugin();
  final _taps = StreamController<AlertTap>.broadcast();
  String? _launchAlertId;
  bool _launchCall114 = false;
  Timer? _testSirenStop;

  static const testSirenDuration = Duration(seconds: 5);

  static const _androidIcon = 'ic_notification';

  static const _call114Action = 'call114';
  static const _viewAction = 'view';
  static const _iosFireCategory = 'FIRE_ALERT_CATEGORY';

  static const _sirenChannel = MethodChannel('com.matpho.mat_pho/siren');

  static const _flagInsistent = 4;

  static const _sirenSound = RawResourceAndroidNotificationSound('fire_alarm_siren');
  static final _sirenVibration = Int64List.fromList([0, 500, 200, 500, 200, 500, 200, 500, 200, 1000]);

  static const _darwin = DarwinNotificationDetails(
    presentAlert: true,
    presentBanner: true,
    presentList: true,
    presentSound: true,
    sound: 'fire_alarm_siren.wav',
    categoryIdentifier: _iosFireCategory,
    // critical/timeSensitive need entitlements a free Apple ID cannot sign.
    interruptionLevel: InterruptionLevel.active,
  );

  static AndroidNotificationDetails _android({
    StyleInformation? style,
    bool alarm = false,
    List<AndroidNotificationAction>? actions,
  }) => AndroidNotificationDetails(
    fireAlertChannelId,
    fireAlertChannelName,
    channelDescription: 'Báo khi AI xác nhận có cháy.',
    importance: Importance.max,
    priority: Priority.max,
    category: AndroidNotificationCategory.alarm,
    visibility: NotificationVisibility.public,
    ticker: fireAlertChannelName,
    audioAttributesUsage: AudioAttributesUsage.alarm,
    color: MpColors.dark.statusFire,
    styleInformation: style,
    actions: actions,
    fullScreenIntent: alarm,
    sound: alarm ? _sirenSound : null,
    playSound: true,
    enableVibration: true,
    vibrationPattern: alarm ? _sirenVibration : null,
    additionalFlags: alarm ? Int32List.fromList([_flagInsistent]) : null,
  );

  Future<void> init() async {
    try {
      await _plugin.initialize(
        settings: InitializationSettings(
          android: const AndroidInitializationSettings(_androidIcon),
          iOS: DarwinInitializationSettings(
            requestAlertPermission: false,
            requestBadgePermission: false,
            requestSoundPermission: false,
            requestCriticalPermission: false,
            notificationCategories: [
              DarwinNotificationCategory(
                _iosFireCategory,
                actions: [
                  DarwinNotificationAction.plain(
                    _call114Action,
                    'Gọi 114',
                    options: {DarwinNotificationActionOption.foreground},
                  ),
                  DarwinNotificationAction.plain(
                    _viewAction,
                    'Xem',
                    options: {DarwinNotificationActionOption.foreground},
                  ),
                ],
              ),
            ],
          ),
        ),
        onDidReceiveNotificationResponse: (response) {
          unawaited(_stopSiren());
          final eventId = response.payload;
          if (eventId == null || eventId.isEmpty) return;
          _taps.add((
            eventId: eventId,
            call114: response.actionId == _call114Action,
          ));
        },
      );
      final androidPlugin = _plugin
          .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin
          >();
      if (androidPlugin != null) {
        await androidPlugin.deleteNotificationChannel(channelId: legacyFireAlertChannelId);
        await androidPlugin.deleteNotificationChannel(channelId: 'fire_alarms');
        final channel = AndroidNotificationChannel(
          fireAlertChannelId,
          fireAlertChannelName,
          description: 'Còi hú báo động cháy khẩn cấp cấp cao nhất.',
          importance: Importance.max,
          sound: _sirenSound,
          playSound: true,
          enableVibration: true,
          vibrationPattern: _sirenVibration,
          audioAttributesUsage: AudioAttributesUsage.alarm,
        );
        await androidPlugin.createNotificationChannel(channel);
      }
      final launch = await _plugin.getNotificationAppLaunchDetails();
      if (launch != null && launch.didNotificationLaunchApp) {
        final resp = launch.notificationResponse;
        final eventId = resp?.payload;
        if (eventId != null && eventId.isNotEmpty) {
          _launchAlertId = eventId;
          _launchCall114 = resp?.actionId == _call114Action;
        }
      }
    } on Object catch (error) {
      debugPrint('Notifications unavailable: $error');
    }
  }

  @override
  Future<NotificationPermission> status() async =>
      switch (await Permission.notification.status) {
        PermissionStatus.granted ||
        PermissionStatus.limited ||
        PermissionStatus.provisional => NotificationPermission.granted,
        PermissionStatus.denied => NotificationPermission.notDetermined,
        PermissionStatus.permanentlyDenied ||
        PermissionStatus.restricted => NotificationPermission.denied,
      };

  @override
  Future<NotificationPermission> request() async =>
      switch (await Permission.notification.request()) {
        PermissionStatus.granted ||
        PermissionStatus.limited ||
        PermissionStatus.provisional => NotificationPermission.granted,
        _ => NotificationPermission.denied,
      };

  @override
  Future<void> openSystemSettings() async {
    await openAppSettings();
  }

  @override
  Future<void> showFireAlert(FireEvent alert, {Uint8List? picture}) =>
      _showFire(
        alert.id,
        title: fireAlertTitle(alert),
        body: fireAlertBody(alert),
        picture: picture,
      );

  @override
  Future<void> showGenericFireAlert(String eventId) => _showFire(
    eventId,
    title: genericFireAlertTitle,
    body: genericFireAlertBody,
  );

  Future<void> _showFire(
    String eventId, {
    required String title,
    required String body,
    Uint8List? picture,
  }) async {
    // A real alarm must not be silenced by a test siren's stop timer.
    _testSirenStop?.cancel();
    unawaited(_startSiren());
    await _show(
      id: _fireAlertId(eventId),
      title: title,
      body: body,
      payload: eventId,
      android: _android(
        alarm: true,
        style: picture == null
            ? BigTextStyleInformation(body)
            : BigPictureStyleInformation(
                ByteArrayAndroidBitmap(picture),
                contentTitle: title,
                summaryText: body,
              ),
        actions: const [
          AndroidNotificationAction(
            _call114Action,
            'Gọi 114',
            showsUserInterface: true,
          ),
          AndroidNotificationAction(_viewAction, 'Xem', showsUserInterface: true),
        ],
      ),
    );
  }

  @override
  Future<void> clearFireAlert(String eventId) async {
    unawaited(_stopSiren());
    try {
      await _plugin.cancel(id: _fireAlertId(eventId));
    } on Object catch (error) {
      debugPrint('Notification not cleared: $error');
    }
  }

  @override
  Future<void> clearFireAlerts() async {
    unawaited(_stopSiren());
    try {
      await _plugin.cancelAll();
    } on Object catch (error) {
      debugPrint('Notifications not cleared: $error');
    }
  }

  @override
  Future<void> stopSiren() => _stopSiren();

  Future<void> _startSiren() async {
    try {
      await _sirenChannel.invokeMethod<void>('start');
    } on Object catch (_) {}
  }

  Future<void> _stopSiren() async {
    try {
      await _sirenChannel.invokeMethod<void>('stop');
    } on Object catch (_) {}
  }

  @override
  Future<void> showTestAlert() async {
    if (defaultTargetPlatform == TargetPlatform.iOS) {
      // iOS notification sounds obey the silent switch; the in-app siren
      // (AVAudioSession .playback) does not, so ring it briefly as well.
      unawaited(_startSiren());
      _testSirenStop?.cancel();
      _testSirenStop = Timer(testSirenDuration, () => unawaited(_stopSiren()));
    }
    await _show(
      id: 0,
      title: testAlertTitle,
      body: testAlertBody,
      android: _android(),
    );
  }

  Future<void> _show({
    required int id,
    required String title,
    required String body,
    required AndroidNotificationDetails android,
    String? payload,
  }) async {
    try {
      await _plugin.show(
        id: id,
        title: title,
        body: body,
        notificationDetails: NotificationDetails(
          android: android,
          iOS: _darwin,
        ),
        payload: payload,
      );
    } on Object catch (error) {
      debugPrint('Notification not shown: $error');
    }
  }

  @override
  Stream<AlertTap> get taps => _taps.stream;

  @override
  String? get launchAlertId => _launchAlertId;

  @override
  bool get launchCall114 => _launchCall114;
}

int _fireAlertId(String eventId) => (eventId.hashCode & 0x7ffffffe) + 1;
