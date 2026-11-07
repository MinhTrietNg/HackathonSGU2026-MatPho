import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/appearance.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_banner.dart';
import 'package:mat_pho/core/widgets/mp_button.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import 'package:mat_pho/core/widgets/mp_toggle.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_notification_service.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/services/notification_service.dart';
import 'package:mat_pho/features/auth/auth_routes.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/auth/permission_controller.dart';
import 'package:mat_pho/features/groups/current_group.dart';
import 'package:mat_pho/features/settings/settings_routes.dart';
import 'package:mat_pho/features/settings/settings_screen.dart';
import 'package:mat_pho/features/settings/settings_state.dart';

const _monitorStub = 'MONITOR';
const _loginStub = 'LOGIN';
const _forgotStub = 'FORGOT';

class _SignedIn extends AuthSessionNotifier {
  @override
  AuthSession build() => const SignedIn(FakeData.user);
}

Future<ProviderContainer> _pumpSettings(
  WidgetTester tester, {
  String initial = AppRoutes.settings,
  Set<FakeCase> cases = const {},
  List<Override> overrides = const [],
}) async {
  tester.view
    ..physicalSize = const Size(360, 780) * 2
    ..devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  addTearDown(hideMpToast);
  final container = ProviderContainer(
    overrides: fakeOverrides([
      fakeScenarioProvider.overrideWithValue(FakeScenario.test(cases: cases)),
      authSessionProvider.overrideWith(_SignedIn.new),
      ...overrides,
    ]),
  );
  addTearDown(container.dispose);
  Widget stub(String text) => Scaffold(body: Center(child: Text(text)));
  final router = GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: initial,
    routes: [
      GoRoute(
        path: AppRoutes.settings,
        builder: (_, _) => const SettingsScreen(),
        routes: settingsSubRoutes,
      ),
      GoRoute(path: AppRoutes.monitor, builder: (_, _) => stub(_monitorStub)),
      GoRoute(path: AppRoutes.login, builder: (_, _) => stub(_loginStub)),
      GoRoute(
        path: AuthRoutes.forgotPassword,
        builder: (_, _) => stub(_forgotStub),
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
  await _settle(tester);
  return container;
}

Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 3; i++) {
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
  }
}

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await _settle(tester);
}

Finder _button(String label) => find.widgetWithText(MpButton, label);

Finder _toggle(String label) =>
    find.byWidgetPredicate((w) => w is MpToggle && w.semanticLabel == label);

bool _toggleValue(WidgetTester tester, String label) =>
    tester.widget<MpToggle>(_toggle(label)).value;

void main() {
  group('H1 · Cài đặt', () {
    testWidgets('shows the account and the loud-when-silent state', (
      tester,
    ) async {
      await _pumpSettings(tester);
      expect(find.text('Nguyễn Minh Anh'), findsOneWidget);
      expect(find.text('0912 345 678'), findsOneWidget);
      expect(find.text('MA'), findsOneWidget);
      expect(_toggleValue(tester, 'Kêu cả khi im lặng'), isTrue);
    });

    testWidgets('"Kêu cả khi im lặng" saves the new value', (tester) async {
      final container = await _pumpSettings(tester);
      await _tap(tester, _toggle('Kêu cả khi im lặng'));
      expect(_toggleValue(tester, 'Kêu cả khi im lặng'), isFalse);
      expect(container.read(fakeWorldProvider).loudWhenSilent, isFalse);
    });

    testWidgets('"Giao diện sáng" updates the appearance', (tester) async {
      final container = await _pumpSettings(tester);
      expect(container.read(lightAppearanceProvider), isFalse);
      await _tap(tester, _toggle('Giao diện sáng'));
      expect(container.read(lightAppearanceProvider), isTrue);
      expect(_toggleValue(tester, 'Giao diện sáng'), isTrue);
    });

    testWidgets('"Thông báo" reads "Đang bật" when allowed', (tester) async {
      await _pumpSettings(tester);
      expect(find.text('Thông báo'), findsOneWidget);
      expect(find.text('Đang bật'), findsOneWidget);
    });

    testWidgets('"Thông báo" never asked → the system dialog', (tester) async {
      final container = await _pumpSettings(
        tester,
        cases: {FakeCase.notificationsNotDetermined},
      );
      expect(find.text('Đang tắt'), findsOneWidget);
      await _tap(tester, find.text('Thông báo'));
      expect(find.text('Đang bật'), findsOneWidget);
      expect(
        _notifications(container).permission,
        NotificationPermission.granted,
      );
    });

    testWidgets('"Thông báo" refused → system settings, re-read', (
      tester,
    ) async {
      final service = FakeNotificationService(
        const FakeScenario.test(cases: {FakeCase.notificationsDenied}),
        settingsTurnOn: false,
      );
      final container = await _pumpSettings(
        tester,
        cases: {FakeCase.notificationsDenied},
        overrides: [notificationServiceProvider.overrideWithValue(service)],
      );
      expect(find.text('Đang tắt'), findsOneWidget);
      await _tap(tester, find.text('Thông báo'));
      expect(find.text('Đang tắt'), findsOneWidget);
      expect(service.permission, NotificationPermission.denied);

      service.permission = NotificationPermission.granted;
      await container.read(notificationPermissionProvider.notifier).refresh();
      await _settle(tester);
      expect(find.text('Đang bật'), findsOneWidget);
    });

    test('initials skip the family name', () {
      expect(initialsOf('Nguyễn Minh Anh'), 'MA');
      expect(initialsOf('Trần Lan'), 'L');
      expect(initialsOf('An'), 'A');
    });

    test('"Nhóm & thành viên" counts the shared groups, not the personal '
        'one, whichever place is chosen', () async {
      final container = ProviderContainer(
        overrides: fakeOverrides([
          fakeScenarioProvider.overrideWithValue(const FakeScenario.test()),
        ]),
      );
      addTearDown(container.dispose);
      container
          .read(currentGroupIdProvider.notifier)
          .select(FakeData.office.id);
      final groups = container.read(fakeWorldProvider).groups;
      expect(groups.where((g) => g.isPersonal), hasLength(1));
      expect(
        await container.read(settingsGroupCountProvider.future),
        groups.length - 1,
      );
    });
  });

  group('H6 · Đăng xuất', () {
    testWidgets('"Ở lại" keeps the session', (tester) async {
      final container = await _pumpSettings(tester);
      await _tap(tester, find.text('Đăng xuất'));
      expect(find.text('Máy này sẽ không nhận báo cháy nữa.'), findsOneWidget);
      await _tap(tester, _button('Ở lại'));
      expect(find.text('Đăng xuất?'), findsNothing);
      expect(container.read(authSessionProvider), isA<SignedIn>());
      expect(container.read(fakeWorldProvider).signedIn, isTrue);
    });

    testWidgets('confirming signs out and opens A5', (tester) async {
      final container = await _pumpSettings(tester);
      await _tap(tester, find.text('Đăng xuất'));
      await _tap(tester, _button('Đăng xuất'));
      expect(container.read(authSessionProvider), isA<SignedOut>());
      expect(container.read(fakeWorldProvider).signedIn, isFalse);
      expect(find.text(_loginStub), findsOneWidget);
    });
  });

  testWidgets('no "Camera" row: cameras are managed on Theo dõi', (
    tester,
  ) async {
    await _pumpSettings(tester);
    expect(find.text('Camera'), findsNothing);
    expect(find.text('Nhóm & thành viên'), findsOneWidget);
  });

  group('H4 · Gửi thử cảnh báo', () {
    testWidgets('opens from H1 and shows when the test arrived', (
      tester,
    ) async {
      final container = await _pumpSettings(tester);
      await _tap(tester, find.text('Thử báo cháy'));
      expect(find.text('Máy có kêu không?'), findsOneWidget);
      expect(find.text('Đã nhận sau 1,2 giây'), findsOneWidget);
      expect(find.text('Máy kêu cả khi im lặng. Ổn rồi.'), findsOneWidget);
      expect(tester.widget<MpButton>(_button('Thử lại')).onPressed, isNotNull);
      await _tap(tester, _button('Thử lại'));
      expect(find.text('Đã nhận sau 1,2 giây'), findsOneWidget);
      expect(_notifications(container).shown.map((n) => n.title), [
        testAlertTitle,
        testAlertTitle,
      ]);
    });

    testWidgets('warns when the phone stays silent', (tester) async {
      final container = await _pumpSettings(tester);
      container.read(fakeWorldProvider).loudWhenSilent = false;
      await _tap(tester, find.text('Thử báo cháy'));
      final banner = tester.widget<MpBanner>(find.byType(MpBanner));
      expect(banner.tone, MpBannerTone.warn);
      expect(banner.title, 'Đã nhận sau 1,2 giây');
    });
  });

  group('H5 · Đổi mật khẩu', () {
    Finder field(int i) => find.byType(TextField).at(i);

    Future<void> fill(
      WidgetTester tester, {
      required String current,
      String next = 'matkhaumoi12',
    }) async {
      await tester.enterText(field(0), current);
      await tester.enterText(field(1), next);
      await tester.enterText(field(2), next);
      await tester.pump();
    }

    testWidgets('"Lưu" waits for valid passwords', (tester) async {
      await _pumpSettings(tester, initial: SettingsRoutes.changePassword);
      expect(tester.widget<MpButton>(_button('Lưu')).onPressed, isNull);
      await fill(tester, current: FakeData.password, next: 'ngan1');
      expect(tester.widget<MpButton>(_button('Lưu')).onPressed, isNull);
      await fill(tester, current: FakeData.password);
      expect(tester.widget<MpButton>(_button('Lưu')).onPressed, isNotNull);
    });

    testWidgets('changes the password and goes back to H1', (tester) async {
      final container = await _pumpSettings(tester);
      await _tap(tester, find.text('Đổi mật khẩu'));
      await fill(tester, current: FakeData.password);
      await _tap(tester, _button('Lưu'));
      expect(container.read(fakeWorldProvider).password, 'matkhaumoi12');
      expect(find.text('Cài đặt'), findsOneWidget);
      expect(find.text('Đã đổi mật khẩu.'), findsOneWidget);
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
      expect(find.text('Đã đổi mật khẩu.'), findsNothing);
    });

    testWidgets('a wrong current password is shown on its field', (
      tester,
    ) async {
      final container = await _pumpSettings(
        tester,
        initial: SettingsRoutes.changePassword,
      );
      await fill(tester, current: 'saimatkhau1');
      await _tap(tester, _button('Lưu'));
      expect(find.text('Sai mật khẩu'), findsOneWidget);
      expect(container.read(fakeWorldProvider).password, FakeData.password);
      await tester.enterText(field(0), FakeData.password);
      await tester.pump();
      expect(find.text('Sai mật khẩu'), findsNothing);
    });

    testWidgets('"Quên mật khẩu?" opens B4', (tester) async {
      await _pumpSettings(tester, initial: SettingsRoutes.changePassword);
      await _tap(tester, find.text('Quên mật khẩu?'));
      expect(find.text(_forgotStub), findsOneWidget);
    });
  });
}

FakeNotificationService _notifications(ProviderContainer container) =>
    container.read(notificationServiceProvider) as FakeNotificationService;
