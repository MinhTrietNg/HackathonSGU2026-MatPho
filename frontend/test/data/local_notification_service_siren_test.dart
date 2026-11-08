import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/services/local_notification_service.dart';

const _siren = MethodChannel('com.matpho.mat_pho/siren');

List<String> _recordSiren(WidgetTester tester) {
  final calls = <String>[];
  tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(_siren, (
    call,
  ) async {
    calls.add(call.method);
    return null;
  });
  addTearDown(
    () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      _siren,
      null,
    ),
  );
  return calls;
}

void main() {
  testWidgets('iOS test alert rings the in-app siren, then stops it', (
    tester,
  ) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    final calls = _recordSiren(tester);

    await LocalNotificationService().showTestAlert();
    await tester.pump();
    expect(calls, ['start']);

    await tester.pump(LocalNotificationService.testSirenDuration);
    expect(calls, ['start', 'stop']);

    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('Android test alert leaves the siren alone', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    final calls = _recordSiren(tester);

    await LocalNotificationService().showTestAlert();
    await tester.pump(LocalNotificationService.testSirenDuration);
    expect(calls, isEmpty);

    debugDefaultTargetPlatformOverride = null;
  });
}
