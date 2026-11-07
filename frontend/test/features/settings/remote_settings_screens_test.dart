library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_button.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/repositories/settings_repository.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/settings/settings_routes.dart';
import 'package:mat_pho/features/settings/settings_screen.dart';

import '../../data/remote/remote_harness.dart';

class _SignedIn extends AuthSessionNotifier {
  @override
  AuthSession build() => const SignedIn(FakeData.user);
}

void main() {
  late RemoteHarness h;

  setUp(() => h = RemoteHarness(idToken: 'tok-1'));
  tearDown(() => h.dispose());

  Future<void> pumpSettings(
    WidgetTester tester,
    String initial,
    SettingsRepository settings,
  ) async {
    tester.view
      ..physicalSize = const Size(360, 780) * 2
      ..devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    final container = ProviderContainer(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(FakeScenario.test()),
        authSessionProvider.overrideWith(_SignedIn.new),
        settingsRepositoryProvider.overrideWithValue(settings),
      ]),
    );
    addTearDown(container.dispose);
    final router = GoRouter(
      navigatorKey: rootNavigatorKey,
      initialLocation: initial,
      routes: [
        GoRoute(
          path: AppRoutes.settings,
          builder: (_, _) => const SettingsScreen(),
          routes: settingsSubRoutes,
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(
          theme: AppTheme.dark(),
          locale: const Locale('vi'),
          supportedLocales: const [Locale('vi')],
          localizationsDelegates: GlobalMaterialLocalizations.delegates,
          routerConfig: router,
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('H5 · 422 WRONG_PASSWORD → "Sai mật khẩu" on its field', (
    tester,
  ) async {
    h.on(
      'POST',
      '/auth/change-password',
      (_) => errorResponse(422, 'WRONG_PASSWORD', {'attempts_left': 0}),
    );
    await pumpSettings(tester, SettingsRoutes.changePassword, h.settings());
    final fields = find.byType(TextField);
    await tester.enterText(fields.at(0), 'saimatkhau1');
    await tester.enterText(fields.at(1), 'matkhaumoi12');
    await tester.enterText(fields.at(2), 'matkhaumoi12');
    await tester.pump();
    final save = find.widgetWithText(MpButton, 'Lưu');
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(find.text('Sai mật khẩu'), findsOneWidget);
  });

  group('H4', () {
    void answerTestAlert() => h.on(
      'POST',
      '/settings/test-alert',
      (_) => jsonResponse({
        'sent_at': '2026-11-04T12:00:00.000Z',
        'status': 'dispatched',
      }),
    );

    testWidgets('the TEST_ALERT push arrives → "Đã nhận sau …"', (
      tester,
    ) async {
      final pushes = StreamController<void>.broadcast();
      addTearDown(pushes.close);
      answerTestAlert();
      h.on('GET', '/users/me', (_) => jsonResponse(contractUser));
      await pumpSettings(
        tester,
        SettingsRoutes.testAlert,
        h.settings(testAlertPushes: pushes.stream),
      );
      expect(find.textContaining('Đã nhận sau'), findsNothing);
      pushes.add(null);
      await tester.pumpAndSettle();
      expect(find.textContaining('Đã nhận sau'), findsOneWidget);
      expect(find.text('Máy kêu cả khi im lặng. Ổn rồi.'), findsOneWidget);
    });

    testWidgets('no push before the timeout → the failure banner', (
      tester,
    ) async {
      final pushes = StreamController<void>.broadcast();
      addTearDown(pushes.close);
      answerTestAlert();
      await pumpSettings(
        tester,
        SettingsRoutes.testAlert,
        h.settings(
          testAlertPushes: pushes.stream,
          testAlertTimeout: const Duration(seconds: 20),
        ),
      );
      await tester.pump(const Duration(seconds: 21));
      await tester.pumpAndSettle();
      expect(find.text('Máy chủ đang bận'), findsOneWidget);
      expect(find.textContaining('Đã nhận sau'), findsNothing);
    });
  });
}
