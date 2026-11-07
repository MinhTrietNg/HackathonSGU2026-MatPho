import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/app.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/widgets/mp_button.dart';
import 'fakes/fake_data.dart';
import 'fakes/fake_scenario.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/repositories/repositories.dart';

import 'fakes/fake_overrides.dart';

Future<void> _launch(
  WidgetTester tester,
  Set<FakeCase> cases, {
  DetectionRepository? detection,
}) async {
  tester.view
    ..physicalSize = const Size(360, 780) * 2
    ..devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    ProviderScope(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(FakeScenario.test(cases: cases)),
        if (detection != null)
          detectionRepositoryProvider.overrideWithValue(detection),
      ]),
      child: const MatPhoApp(),
    ),
  );
  await tester.pump(const Duration(seconds: 2));
  await tester.pumpAndSettle();
}

Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 3; i++) {
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
  }
}

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await _settle(tester);
}

Finder _button(String label) => find.widgetWithText(MpButton, label);

class _QuietDetection implements DetectionRepository {
  StreamController<DetectionState>? _session;

  @override
  Stream<DetectionState> start(Camera camera) {
    _session?.close();
    final session = StreamController<DetectionState>()
      ..add(const DetectionWatching());
    _session = session;
    return session.stream;
  }

  @override
  Future<void> dismissSuspect() async {}

  @override
  Future<void> stop() async => _session?.close();
}

Future<void> _pumpFrames(WidgetTester tester) async {
  for (var i = 0; i < 10; i++) {
    await tester.pump(const Duration(milliseconds: 500));
  }
}

void main() {
  testWidgets('signed in: splash leads to Theo dõi and tabs switch', (
    tester,
  ) async {
    await _launch(tester, const {});

    expect(find.bySemanticsLabel('Theo dõi'), findsWidgets);
    expect(find.text('Chung cư Sky Garden'), findsOneWidget);
    expect(find.text('Thêm camera RTSP'), findsOneWidget);

    await tester.tap(find.bySemanticsLabel('Cài đặt'));
    await tester.pumpAndSettle();
    expect(find.text('Cài đặt'), findsWidgets);
    expect(find.byType(StretchingOverscrollIndicator), findsNothing);
    expect(find.byType(GlowingOverscrollIndicator), findsNothing);
  });

  testWidgets('Cài đặt › Nhóm & thành viên opens the groups list (J7)', (
    tester,
  ) async {
    await _launch(tester, const {});
    await tester.tap(find.bySemanticsLabel('Cài đặt'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Nhóm & thành viên'));
    await tester.pumpAndSettle();
    expect(find.text('Tạo nhóm'), findsOneWidget);
    expect(find.text('Tham gia nhóm'), findsNothing);
  });

  testWidgets('no camera yet: login → C1 → I2, back lands on the list', (
    tester,
  ) async {
    await _launch(tester, const {
      FakeCase.signedOut,
      FakeCase.notificationsNotDetermined,
      FakeCase.noCameras,
    });
    await tester.enterText(find.byType(TextField).at(0), '0912 345 678');
    await tester.enterText(find.byType(TextField).at(1), FakeData.password);
    await _tap(tester, _button('Đăng nhập'));
    expect(find.text('Bật thông báo'), findsOneWidget);

    await _tap(tester, _button('Cho phép thông báo'));
    expect(find.text('Thêm camera RTSP'), findsOneWidget);
    expect(_button('Kết nối'), findsOneWidget);

    await _tap(tester, find.bySemanticsLabel('Quay lại'));
    expect(find.text('Camera của tôi'), findsOneWidget);
    expect(find.text('Dán đường dẫn RTSP · AI quét 24/7'), findsOneWidget);
    expect(find.text('Khu sạc xe'), findsNothing);
  });

  testWidgets('saving I5 opens E2 with the list behind it', (tester) async {
    await _launch(tester, const {}, detection: _QuietDetection());
    await _tap(tester, find.text('Dán đường dẫn RTSP · AI quét 24/7'));
    await tester.enterText(find.byType(TextField), FakeData.rtspExample);
    await _tap(tester, _button('Kết nối'));
    expect(find.text('Đặt tên camera'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'Cửa hầm');
    await tester.pump();
    await tester.tap(_button('Lưu'));
    await _pumpFrames(tester);
    expect(find.text('Hầm B1 · Cửa hầm'), findsOneWidget);
    expect(find.text('AI đang quét'), findsOneWidget);
    expect(find.bySemanticsLabel('Lịch sử'), findsWidgets);

    await tester.tap(find.bySemanticsLabel('Quay lại'));
    await _settle(tester);
    expect(find.text('Chung cư Sky Garden'), findsOneWidget);
    expect(find.text('Cửa hầm'), findsOneWidget);
  });

  testWidgets('a new camera plays the fire: E2 → E2d → F2 by itself', (
    tester,
  ) async {
    await _launch(tester, const {});
    await _tap(tester, find.text('Dán đường dẫn RTSP · AI quét 24/7'));
    await tester.enterText(find.byType(TextField), FakeData.rtspExample);
    await _tap(tester, _button('Kết nối'));
    await tester.enterText(find.byType(TextField), 'Cửa hầm');
    await tester.pump();

    await tester.tap(_button('Lưu'));
    await _pumpFrames(tester);
    expect(find.text('Cháy ở Hầm xe'), findsOneWidget);
  });

  testWidgets('F4 "Xem camera" opens the watch screen in Theo dõi', (
    tester,
  ) async {
    await _launch(tester, const {FakeCase.verificationServerError});
    await tester.tap(find.text('Khu sạc xe'));
    await _pumpFrames(tester);
    expect(find.text('Xem camera'), findsOneWidget);

    await tester.tap(find.text('Xem camera'));
    await _pumpFrames(tester);
    expect(find.text('Hầm B1 · Khu sạc xe'), findsOneWidget);
    expect(find.text('AI đang quét'), findsOneWidget);
    expect(find.bySemanticsLabel('Lịch sử'), findsWidgets);
    expect(find.text('Máy phát hiện khói'), findsNothing);

    await tester.tap(find.bySemanticsLabel('Quay lại'));
    await _settle(tester);
    expect(find.text('Chung cư Sky Garden'), findsOneWidget);
  });

  testWidgets('"Xem camera" from an alert opened elsewhere opens E2', (
    tester,
  ) async {
    await _launch(tester, const {}, detection: _QuietDetection());
    final router = ProviderScope.containerOf(
      tester.element(find.byType(MatPhoApp)),
    ).read(appRouterProvider);
    await tester.tap(find.bySemanticsLabel('Lịch sử'));
    await _settle(tester);
    unawaited(router.push(AppRoutes.alert('evt-unverified')));
    await _settle(tester);

    await tester.tap(find.text('Xem camera'));
    await _pumpFrames(tester);
    expect(router.state.uri.path, AppRoutes.watch(FakeData.fireCameraId));
    expect(find.text('Hầm B1 · Khu sạc xe'), findsOneWidget);
    expect(find.text('AI đang quét'), findsOneWidget);

    await tester.tap(find.bySemanticsLabel('Quay lại'));
    await _settle(tester);
    expect(find.text('Chung cư Sky Garden'), findsOneWidget);
  });

  testWidgets('signed out: splash leads to the login screen', (tester) async {
    await _launch(tester, const {FakeCase.signedOut});

    expect(find.text('Đăng nhập'), findsWidgets);
    expect(find.text('Chung cư Sky Garden'), findsNothing);
  });
}
