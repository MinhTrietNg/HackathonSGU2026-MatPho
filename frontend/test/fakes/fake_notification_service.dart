import 'dart:async';
import 'dart:typed_data';

import 'package:mat_pho/data/models/fire_event.dart';
import 'package:mat_pho/data/models/settings.dart';
import 'package:mat_pho/data/services/notification_service.dart';
import 'fake_scenario.dart';

typedef FakeNotification = ({String title, String body, String? eventId});

final class FakeNotificationService implements NotificationService {
  FakeNotificationService(
    FakeScenario scenario, {
    this.grantOnRequest = true,
    this.settingsTurnOn = true,
    this.launchAlertId,
  }) : permission = scenario.has(FakeCase.notificationsDenied)
           ? NotificationPermission.denied
           : scenario.has(FakeCase.notificationsNotDetermined)
           ? NotificationPermission.notDetermined
           : NotificationPermission.granted;

  final bool grantOnRequest;

  final bool settingsTurnOn;
  NotificationPermission permission;
  final shown = <FakeNotification>[];
  final _taps = StreamController<AlertTap>.broadcast();

  @override
  final String? launchAlertId;

  @override
  Future<NotificationPermission> status() async => permission;

  @override
  Future<NotificationPermission> request() async => permission = grantOnRequest
      ? NotificationPermission.granted
      : NotificationPermission.denied;

  @override
  Future<void> openSystemSettings() async {
    if (settingsTurnOn) permission = NotificationPermission.granted;
  }

  final pictures = <Uint8List?>[];

  @override
  Future<void> showFireAlert(FireEvent alert, {Uint8List? picture}) async {
    shown.add((
      title: fireAlertTitle(alert),
      body: fireAlertBody(alert),
      eventId: alert.id,
    ));
    pictures.add(picture);
  }

  @override
  Future<void> showGenericFireAlert(String eventId) async {
    shown.add((
      title: genericFireAlertTitle,
      body: genericFireAlertBody,
      eventId: eventId,
    ));
    pictures.add(null);
  }

  int clears = 0;

  @override
  Future<void> clearFireAlerts() async => clears++;

  final cleared = <String>[];

  @override
  Future<void> clearFireAlert(String eventId) async => cleared.add(eventId);

  @override
  Future<void> showTestAlert() async =>
      shown.add((title: testAlertTitle, body: testAlertBody, eventId: null));

  @override
  Stream<AlertTap> get taps => _taps.stream;

  void tap(String eventId, {bool call114 = false}) =>
      _taps.add((eventId: eventId, call114: call114));

  void dispose() => _taps.close();
}
