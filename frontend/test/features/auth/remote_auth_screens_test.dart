library;

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
import '../../fakes/fake_notification_service.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/remote/auth_remote.dart';
import 'package:mat_pho/data/remote/core/remote_providers.dart';
import 'package:mat_pho/features/auth/auth_routes.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/auth/permission_controller.dart';

import '../../data/remote/remote_harness.dart';

const _monitorStub = 'MONITOR';

final _refProvider = Provider<Ref>((ref) => ref);

String _serverTime(Duration after) =>
    FakeData.demoNow.add(after).toUtc().toIso8601String();

void main() {
  late RemoteHarness h;

  setUp(() => h = RemoteHarness());
  tearDown(() => h.dispose());

  Future<ProviderContainer> pumpApp(WidgetTester tester) async {
    final container = ProviderContainer(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(FakeScenario.test()),
        onboardingEveryLoginProvider.overrideWithValue(false),
        apiClientProvider.overrideWithValue(h.api),
        authRepositoryProvider.overrideWith(
          (ref) => RemoteAuthRepository(
            api: h.api,
            session: h.session,
            push: h.push,
            now: ref.watch(clockProvider),
          ),
        ),
        settingsRepositoryProvider.overrideWithValue(h.settings()),
      ]),
    );
    addTearDown(container.dispose);
    final router = GoRouter(
      navigatorKey: rootNavigatorKey,
      initialLocation: AppRoutes.monitor,
      redirect: (context, state) =>
          authRedirect(container.read(_refProvider), state),
      routes: [
        ...authRoutes,
        GoRoute(
          path: AppRoutes.monitor,
          builder: (_, _) =>
              const Scaffold(body: Center(child: Text(_monitorStub))),
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
    return container;
  }

  Finder button(String label) => find.widgetWithText(MpButton, label);
  Finder field(int index) => find.byType(TextField).at(index);

  Future<void> tap(WidgetTester tester, Finder finder) async {
    await tester.ensureVisible(finder);
    await tester.tap(finder);
    await tester.pumpAndSettle();
  }

  Future<void> login(WidgetTester tester) async {
    await tester.enterText(field(0), '0912 345 678');
    await tester.enterText(field(1), 'matkhau123');
    await tap(tester, button('Đăng nhập'));
  }

  group('A5 / A6', () {
    testWidgets('login signs in and opens Theo dõi', (tester) async {
      h.on(
        'POST',
        '/auth/login',
        (_) => jsonResponse({'custom_token': 'ct', 'user': contractUser}),
      );
      final container = await pumpApp(tester);
      await login(tester);
      expect(find.text(_monitorStub), findsOneWidget);
      final session = container.read(authSessionProvider);
      expect(session, isA<SignedIn>());
      expect((session as SignedIn).user.phone, '0912345678');
      expect(h.store.user, contractUser);
    });

    testWidgets('422 WRONG_PASSWORD → "Còn 3 lần thử"', (tester) async {
      h.on(
        'POST',
        '/auth/login',
        (_) => errorResponse(422, 'WRONG_PASSWORD', {'attempts_left': 3}),
      );
      await pumpApp(tester);
      await login(tester);
      expect(find.text('Sai mật khẩu'), findsOneWidget);
      expect(
        find.text('Còn 3 lần thử. Sai tiếp sẽ khoá 15 phút.'),
        findsOneWidget,
      );
      expect(find.text('Mật khẩu không đúng'), findsOneWidget);
    });

    testWidgets('423 ACCOUNT_LOCKED → locked until 22:02', (tester) async {
      h.on(
        'POST',
        '/auth/login',
        (_) => errorResponse(423, 'ACCOUNT_LOCKED', {
          'locked_until': _serverTime(const Duration(minutes: 15)),
        }),
      );
      await pumpApp(tester);
      await login(tester);
      expect(find.text('Tạm khoá đăng nhập'), findsOneWidget);
      expect(
        find.text('Sai 5 lần. Thử lại lúc 22:02 hoặc chọn "Quên mật khẩu?".'),
        findsOneWidget,
      );
    });
  });

  testWidgets('B1 · check-phone not available → inline error', (tester) async {
    h.on(
      'POST',
      '/auth/check-phone',
      (_) =>
          jsonResponse({'phone_number': '+84912345678', 'is_available': false}),
    );
    await pumpApp(tester);
    await tap(tester, find.text('Đăng ký'));
    await tester.enterText(field(1), '0912 345 678');
    await tester.showKeyboard(field(2));
    await tester.pumpAndSettle();
    expect(find.text('Số này đã có tài khoản'), findsOneWidget);
  });

  testWidgets('B4 · 404 PHONE_NOT_REGISTERED → inline error', (tester) async {
    h.on(
      'POST',
      '/auth/forgot-password/request-otp',
      (_) => errorResponse(404, 'PHONE_NOT_REGISTERED'),
    );
    await pumpApp(tester);
    await tap(tester, find.text('Quên mật khẩu?'));
    await tester.enterText(find.byType(TextField), '0912 345 678');
    await tap(tester, button('Gửi mã OTP'));
    expect(find.text('Số này chưa đăng ký'), findsOneWidget);
  });

  group('B3', () {
    Future<void> enterCode(
      WidgetTester tester,
      int status,
      String code, [
      Map<String, Object?>? details,
    ]) async {
      h.on(
        'POST',
        '/auth/forgot-password/request-otp',
        (_) => jsonResponse({
          'challenge_id': 'otp_chl_reset_55f2b',
          'expires_in': 60,
          'resend_cooldown': 60,
        }),
      );
      h.on(
        'POST',
        '/auth/verify-otp',
        (_) => errorResponse(status, code, details),
      );
      await pumpApp(tester);
      await tap(tester, find.text('Quên mật khẩu?'));
      await tester.enterText(find.byType(TextField), '0912 345 678');
      await tap(tester, button('Gửi mã OTP'));
      expect(find.text('Mã đã gửi tới 0912 ••• 678.'), findsOneWidget);
      expect(find.text('1:00'), findsOneWidget);
      await tester.enterText(find.byType(TextField), '482910');
      await tester.pumpAndSettle();
      expect(find.text('Mã sai hoặc hết hạn'), findsOneWidget);
    }

    testWidgets('422 OTP_WRONG → "Còn 2 lần thử"', (tester) async {
      await enterCode(tester, 422, 'OTP_WRONG', {'attempts_left': 2});
      expect(find.text('Còn 2 lần thử'), findsOneWidget);
    });

    testWidgets('410 OTP_EXPIRED → resend at once', (tester) async {
      await enterCode(tester, 410, 'OTP_EXPIRED');
      expect(find.text('Mã đã hết hạn'), findsOneWidget);
      expect(
        tester.widget<MpButton>(button('Gửi lại mã')).onPressed,
        isNotNull,
      );
    });

    testWidgets('429 OTP_LOCKED → wait 5:00', (tester) async {
      await enterCode(tester, 429, 'OTP_LOCKED', {
        'retry_at': _serverTime(const Duration(minutes: 5)),
      });
      expect(find.text('Sai 3 lần. Thử lại sau 5:00'), findsOneWidget);
    });
  });

  group('session', () {
    void savedSession() {
      h.tokens.token = 'tok-1';
      h.store.user = contractUser;
      h.on('GET', '/users/me', (_) => jsonResponse(contractUser));
    }

    testWidgets('A1 restores a saved session from GET /users/me', (
      tester,
    ) async {
      savedSession();
      final container = await pumpApp(tester);
      expect(find.text(_monitorStub), findsOneWidget);
      expect(container.read(sessionUserIdProvider), 'usr_abc123');
    });

    testWidgets('A1 · expired session → A5, cache cleared', (tester) async {
      h.tokens.token = 'tok-1';
      h.store.user = contractUser;
      h.on('GET', '/users/me', (_) => errorResponse(401, 'TOKEN_EXPIRED'));
      final container = await pumpApp(tester);
      expect(button('Đăng nhập'), findsOneWidget);
      expect(container.read(authSessionProvider), isA<SignedOut>());
      expect(h.store.user, isNull);
    });

    testWidgets('a 401 later signs out to A5 the logout way', (tester) async {
      savedSession();
      h.on('GET', '/groups', (_) => errorResponse(401, 'TOKEN_EXPIRED'));
      h.on('POST', '/auth/logout', (_) => errorResponse(401, 'TOKEN_EXPIRED'));
      final container = await pumpApp(tester);
      expect(find.text(_monitorStub), findsOneWidget);

      await expectLater(
        container.read(apiClientProvider).get('/groups'),
        throwsA(anything),
      );
      await tester.pumpAndSettle();

      expect(container.read(authSessionProvider), isA<SignedOut>());
      expect(button('Đăng nhập'), findsOneWidget);
      expect(h.store.user, isNull);
      expect(h.tokens.isSignedIn, isFalse);
      final notifications =
          container.read(notificationServiceProvider)
              as FakeNotificationService;
      expect(notifications.clears, greaterThan(0));
    });
  });
}
