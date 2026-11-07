import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_button.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_scenario.dart';
import '../../fakes/fake_notification_service.dart';
import 'package:mat_pho/data/models/settings.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/features/auth/auth_routes.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/auth/permission_controller.dart';

const _monitorStub = 'MONITOR';
const _addCameraStub = 'ADD CAMERA';

final _routerProvider = Provider.family<GoRouter, String>((ref, initial) {
  final router = GoRouter(
    initialLocation: initial,
    redirect: (context, state) => authRedirect(ref, state),
    routes: [
      ...authRoutes,
      GoRoute(
        path: AppRoutes.monitor,
        builder: (context, state) =>
            const Scaffold(body: Center(child: Text(_monitorStub))),
        routes: [
          GoRoute(
            path: 'cameras/add',
            builder: (context, state) =>
                const Scaffold(body: Center(child: Text(_addCameraStub))),
          ),
        ],
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});

Future<ProviderContainer> _pumpApp(
  WidgetTester tester, {
  Set<FakeCase> cases = const {},
  String initial = AppRoutes.monitor,
  List<Override> overrides = const [],
  bool onboardingEveryLogin = false,
}) async {
  final container = ProviderContainer(
    overrides: fakeOverrides([
      fakeScenarioProvider.overrideWithValue(FakeScenario.test(cases: cases)),
      onboardingEveryLoginProvider.overrideWithValue(onboardingEveryLogin),
      ...overrides,
    ]),
  );
  addTearDown(container.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: Consumer(
        builder: (context, ref, _) => MaterialApp.router(
          theme: AppTheme.dark(),
          locale: const Locale('vi'),
          supportedLocales: const [Locale('vi')],
          localizationsDelegates: GlobalMaterialLocalizations.delegates,
          routerConfig: ref.watch(_routerProvider(initial)),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return container;
}

Finder _button(String label) => find.widgetWithText(MpButton, label);

bool _enabled(WidgetTester tester, String label) =>
    tester.widget<MpButton>(_button(label)).onPressed != null;

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Finder _field(int index) => find.byType(TextField).at(index);

Future<void> _login(
  WidgetTester tester, {
  String phone = '0912 345 678',
  String password = 'matkhau123',
}) async {
  await tester.enterText(_field(0), phone);
  await tester.enterText(_field(1), password);
  await _tap(tester, _button('Đăng nhập'));
}

void main() {
  group('A1 · splash', () {
    testWidgets('a saved session goes straight to Theo dõi', (tester) async {
      final container = await _pumpApp(tester);
      expect(find.text(_monitorStub), findsOneWidget);
      expect(container.read(authSessionProvider), isA<SignedIn>());
    });

    testWidgets('no session goes to A5', (tester) async {
      await _pumpApp(tester, cases: {FakeCase.signedOut});
      expect(find.text('Quên mật khẩu?'), findsOneWidget);
      expect(_button('Đăng nhập'), findsOneWidget);
    });

    testWidgets('a deep link is opened after the splash', (tester) async {
      await _pumpApp(tester, initial: AuthRoutes.notificationsDenied);
      expect(find.text('Có thể bỏ lỡ báo cháy'), findsOneWidget);
    });

    testWidgets('signed out, protected routes go to A5', (tester) async {
      await _pumpApp(
        tester,
        cases: {FakeCase.signedOut},
        initial: AuthRoutes.notificationPermission,
      );
      expect(find.text('Quên mật khẩu?'), findsOneWidget);
    });
  });

  group('A5 / A6 · login', () {
    testWidgets('later logins go to Theo dõi', (tester) async {
      await _pumpApp(tester, cases: {FakeCase.signedOut});
      await _login(tester);
      expect(find.text(_monitorStub), findsOneWidget);
    });

    testWidgets('first login goes to C1', (tester) async {
      await _pumpApp(
        tester,
        cases: {FakeCase.signedOut, FakeCase.notificationsNotDetermined},
      );
      await _login(tester);
      expect(find.text('Bật thông báo'), findsOneWidget);
    });

    testWidgets('kOnboardingEveryLogin: C1 after every login', (tester) async {
      await _pumpApp(
        tester,
        cases: {FakeCase.signedOut},
        onboardingEveryLogin: true,
      );
      await _login(tester);
      expect(find.text('Bật thông báo'), findsOneWidget);
      await _tap(tester, _button('Cho phép thông báo'));
      expect(find.text(_monitorStub), findsOneWidget);
    });

    testWidgets('invalid input is caught before calling the server', (
      tester,
    ) async {
      await _pumpApp(tester, cases: {FakeCase.signedOut});
      await _login(tester, phone: '0912', password: 'abc');
      expect(find.text('Số điện thoại cần đủ 10 số'), findsOneWidget);
      expect(find.text('Mật khẩu cần ít nhất 8 ký tự'), findsOneWidget);
      expect(find.text('Sai mật khẩu'), findsNothing);
    });

    testWidgets('wrong passwords count down, then lock for 15 minutes', (
      tester,
    ) async {
      await _pumpApp(tester, cases: {FakeCase.signedOut});
      await _login(tester, password: 'saimatkhau1');
      expect(find.text('Sai mật khẩu'), findsOneWidget);
      expect(
        find.text('Còn 4 lần thử. Sai tiếp sẽ khoá 15 phút.'),
        findsOneWidget,
      );
      expect(find.text('Mật khẩu không đúng'), findsOneWidget);

      for (var i = 0; i < 3; i++) {
        await _login(tester, password: 'saimatkhau1');
      }
      expect(
        find.text('Còn 1 lần thử. Sai tiếp sẽ khoá 15 phút.'),
        findsOneWidget,
      );

      await _login(tester, password: 'saimatkhau1');
      expect(find.text('Tạm khoá đăng nhập'), findsOneWidget);
      expect(
        find.text('Sai 5 lần. Thử lại lúc 22:02 hoặc chọn "Quên mật khẩu?".'),
        findsOneWidget,
      );

      await _login(tester);
      expect(find.text('Tạm khoá đăng nhập'), findsOneWidget);
      expect(find.text(_monitorStub), findsNothing);
    });

    testWidgets('A6 · forced wrong password shows 3 attempts left', (
      tester,
    ) async {
      await _pumpApp(
        tester,
        cases: {FakeCase.signedOut, FakeCase.wrongPassword},
      );
      await _login(tester);
      expect(
        find.text('Còn 3 lần thử. Sai tiếp sẽ khoá 15 phút.'),
        findsOneWidget,
      );
    });

    testWidgets('no network shows its own banner', (tester) async {
      await _pumpApp(
        tester,
        cases: {FakeCase.signedOut, FakeCase.loginNetworkError},
      );
      await _login(tester);
      expect(find.text('Không có mạng'), findsOneWidget);
      expect(find.text('Mật khẩu không đúng'), findsNothing);
    });
  });

  group('B · register', () {
    Future<void> openRegister(WidgetTester tester, Set<FakeCase> cases) async {
      await _pumpApp(tester, cases: {FakeCase.signedOut, ...cases});
      await _tap(tester, find.text('Đăng ký'));
      expect(find.text('Tạo tài khoản'), findsOneWidget);
    }

    testWidgets('B1 → B2 → C1 → C3 → I2 (a new account adds a camera)', (
      tester,
    ) async {
      await openRegister(tester, {FakeCase.notificationsNotDetermined});
      expect(_enabled(tester, 'Gửi mã OTP'), isFalse);
      await tester.enterText(_field(0), 'Trần Văn Bình');
      await tester.enterText(_field(1), '0933 222 111');
      await tester.enterText(_field(2), 'matkhau789');
      await _tap(
        tester,
        find.text('Tôi đồng ý với Điều khoản & Chính sách quyền riêng tư'),
      );
      expect(_enabled(tester, 'Gửi mã OTP'), isTrue);
      await _tap(tester, _button('Gửi mã OTP'));

      expect(find.text('Nhập mã 6 số'), findsOneWidget);
      expect(find.text('Mã đã gửi tới 0933 ••• 111.'), findsOneWidget);
      expect(find.text('Gửi lại mã sau'), findsOneWidget);
      expect(find.text('1:00'), findsOneWidget);

      await tester.enterText(find.byType(TextField), '123456');
      await tester.pumpAndSettle();
      expect(find.text('Bật thông báo'), findsOneWidget);

      await _tap(tester, _button('Để sau'));
      await _tap(tester, _button('Để sau'));
      expect(find.text(_addCameraStub), findsOneWidget);
    });

    testWidgets('permission already answered on this phone: B2 → I2', (
      tester,
    ) async {
      await openRegister(tester, const {});
      await tester.enterText(_field(0), 'Trần Văn Bình');
      await tester.enterText(_field(1), '0933 222 111');
      await tester.enterText(_field(2), 'matkhau789');
      await _tap(
        tester,
        find.text('Tôi đồng ý với Điều khoản & Chính sách quyền riêng tư'),
      );
      await _tap(tester, _button('Gửi mã OTP'));
      await tester.enterText(find.byType(TextField), '123456');
      await tester.pumpAndSettle();
      expect(find.text('Bật thông báo'), findsNothing);
      expect(find.text(_addCameraStub), findsOneWidget);
    });

    testWidgets('B1 · a registered phone is flagged when the field is left', (
      tester,
    ) async {
      await openRegister(tester, {FakeCase.phoneExists});
      await tester.enterText(_field(1), '0912 345 678');
      await tester.showKeyboard(_field(2));
      await tester.pumpAndSettle();
      expect(find.text('Số này đã có tài khoản'), findsOneWidget);

      await tester.enterText(_field(1), '0912 345 679');
      await tester.pump();
      expect(find.text('Số này đã có tài khoản'), findsNothing);
    });
  });

  group('B · OTP', () {
    Future<void> openOtp(WidgetTester tester, Set<FakeCase> cases) async {
      await _pumpApp(tester, cases: {FakeCase.signedOut, ...cases});
      await _tap(tester, find.text('Quên mật khẩu?'));
      await tester.enterText(find.byType(TextField), '0912 345 678');
      await _tap(tester, _button('Gửi mã OTP'));
      expect(find.text('Nhập mã 6 số'), findsOneWidget);
    }

    testWidgets('B3 · wrong codes keep the digits, then wait 5 minutes', (
      tester,
    ) async {
      await openOtp(tester, {});
      await tester.enterText(find.byType(TextField), '482910');
      await tester.pumpAndSettle();
      expect(find.text('Mã sai hoặc hết hạn'), findsOneWidget);
      expect(find.text('Xem lại tin nhắn mới nhất.'), findsOneWidget);
      expect(find.text('Còn 2 lần thử'), findsOneWidget);
      for (final digit in '482910'.split('')) {
        expect(find.text(digit), findsOneWidget);
      }

      await tester.enterText(find.byType(TextField), '482911');
      await tester.pumpAndSettle();
      expect(find.text('Còn 1 lần thử'), findsOneWidget);

      await tester.enterText(find.byType(TextField), '482912');
      await tester.pumpAndSettle();
      expect(find.text('Sai 3 lần. Thử lại sau 5:00'), findsOneWidget);
      expect(_enabled(tester, 'Gửi lại mã'), isFalse);
    });

    testWidgets('B3 · an expired code can be resent right away', (
      tester,
    ) async {
      await openOtp(tester, {FakeCase.otpExpired});
      await tester.enterText(find.byType(TextField), '123456');
      await tester.pumpAndSettle();
      expect(find.text('Mã đã hết hạn'), findsOneWidget);
      expect(_enabled(tester, 'Gửi lại mã'), isTrue);

      await _tap(tester, _button('Gửi lại mã'));
      expect(find.text('Mã sai hoặc hết hạn'), findsNothing);
      expect(find.text('Mã đã gửi tới 0912 ••• 678.'), findsOneWidget);
    });
  });

  group('B · forgot password', () {
    testWidgets('B4 → B2 → B5 → A5', (tester) async {
      await _pumpApp(tester, cases: {FakeCase.signedOut});
      await _tap(tester, find.text('Quên mật khẩu?'));
      expect(find.text('Lấy lại mật khẩu'), findsOneWidget);
      await tester.enterText(find.byType(TextField), '0912 345 678');
      await _tap(tester, _button('Gửi mã OTP'));

      await tester.enterText(find.byType(TextField), '123456');
      await tester.pumpAndSettle();
      expect(find.text('Đặt mật khẩu mới'), findsOneWidget);

      expect(_enabled(tester, 'Đặt lại mật khẩu'), isFalse);
      await tester.enterText(_field(0), 'matkhau');
      await tester.pump();
      expect(_enabled(tester, 'Đặt lại mật khẩu'), isFalse);
      await tester.enterText(_field(0), 'matkhau456');
      await tester.pump();
      expect(_enabled(tester, 'Đặt lại mật khẩu'), isFalse);
      await tester.enterText(_field(1), 'matkhau45');
      await tester.pump();
      expect(_enabled(tester, 'Đặt lại mật khẩu'), isFalse);
      await tester.enterText(_field(1), 'matkhau456');
      await tester.pump();
      expect(_enabled(tester, 'Đặt lại mật khẩu'), isTrue);

      await _tap(tester, _button('Đặt lại mật khẩu'));
      expect(find.text('Quên mật khẩu?'), findsOneWidget);
      expect(
        find.text('Đã đổi mật khẩu. Máy khác đã đăng xuất.'),
        findsOneWidget,
      );
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();

      await _login(tester);
      expect(find.text('Mật khẩu không đúng'), findsOneWidget);
      await _login(tester, password: 'matkhau456');
      expect(find.text(_monitorStub), findsOneWidget);
    });

    testWidgets('B4 · an unregistered phone gets an inline error', (
      tester,
    ) async {
      await _pumpApp(
        tester,
        cases: {FakeCase.signedOut, FakeCase.phoneNotRegistered},
      );
      await _tap(tester, find.text('Quên mật khẩu?'));
      await tester.enterText(find.byType(TextField), '0912 345 678');
      await _tap(tester, _button('Gửi mã OTP'));
      expect(find.text('Số này chưa đăng ký'), findsOneWidget);
      expect(find.text('Nhập mã 6 số'), findsNothing);
    });
  });

  group('C · notification permission', () {
    testWidgets('C1 "Cho phép" → granted → Theo dõi', (tester) async {
      final container = await _pumpApp(
        tester,
        cases: {FakeCase.notificationsNotDetermined},
        initial: AuthRoutes.notificationPermission,
      );
      await _tap(tester, _button('Cho phép thông báo'));
      expect(find.text(_monitorStub), findsOneWidget);
      expect(
        _notifications(container).permission,
        NotificationPermission.granted,
      );
    });

    testWidgets('C1 · denied in the system dialog → C3', (tester) async {
      await _pumpApp(
        tester,
        cases: {FakeCase.notificationsNotDetermined},
        initial: AuthRoutes.notificationPermission,
        overrides: [
          notificationServiceProvider.overrideWith(
            (ref) => FakeNotificationService(
              ref.watch(fakeScenarioProvider),
              grantOnRequest: false,
            ),
          ),
        ],
      );
      await _tap(tester, _button('Cho phép thông báo'));
      expect(find.text('Có thể bỏ lỡ báo cháy'), findsOneWidget);
    });

    testWidgets('C3 "Mở Cài đặt" → turned on → Theo dõi', (tester) async {
      final container = await _pumpApp(
        tester,
        cases: {FakeCase.notificationsDenied},
        initial: AuthRoutes.notificationsDenied,
      );
      await _tap(tester, _button('Mở Cài đặt'));
      expect(find.text(_monitorStub), findsOneWidget);
      expect(
        _notifications(container).permission,
        NotificationPermission.granted,
      );
    });

    testWidgets('C3 · settings still off: stays, re-read on resume', (
      tester,
    ) async {
      final service = FakeNotificationService(
        FakeScenario.test(cases: {FakeCase.notificationsDenied}),
        settingsTurnOn: false,
      );
      final container = await _pumpApp(
        tester,
        cases: {FakeCase.notificationsDenied},
        initial: AuthRoutes.notificationsDenied,
        overrides: [notificationServiceProvider.overrideWithValue(service)],
      );
      await _tap(tester, _button('Mở Cài đặt'));
      expect(find.text('Có thể bỏ lỡ báo cháy'), findsOneWidget);

      service.permission = NotificationPermission.granted;
      await container.read(notificationPermissionProvider.notifier).refresh();
      await tester.pumpAndSettle();
      expect(find.text(_monitorStub), findsOneWidget);
    });

    testWidgets('C1 "Để sau" → C3 → "Để sau" → Theo dõi', (tester) async {
      await _pumpApp(
        tester,
        cases: {FakeCase.notificationsNotDetermined},
        initial: AuthRoutes.notificationPermission,
      );
      await _tap(tester, _button('Để sau'));
      expect(find.text('Có thể bỏ lỡ báo cháy'), findsOneWidget);
      expect(find.text('Vào Cài đặt › Mắt Phố › Thông báo.'), findsOneWidget);
      await _tap(tester, _button('Để sau'));
      expect(find.text(_monitorStub), findsOneWidget);
    });

    testWidgets('no camera yet: C1 → I2, back lands on Theo dõi', (
      tester,
    ) async {
      final container = await _pumpApp(
        tester,
        cases: {FakeCase.notificationsNotDetermined, FakeCase.noCameras},
        initial: AuthRoutes.notificationPermission,
      );
      await _tap(tester, _button('Cho phép thông báo'));
      expect(find.text(_addCameraStub), findsOneWidget);

      container.read(_routerProvider(AuthRoutes.notificationPermission)).pop();
      await tester.pumpAndSettle();
      expect(find.text(_monitorStub), findsOneWidget);
    });

    testWidgets('no camera yet: C3 "Để sau" → I2', (tester) async {
      await _pumpApp(
        tester,
        cases: {FakeCase.notificationsDenied, FakeCase.noCameras},
        initial: AuthRoutes.notificationsDenied,
      );
      await _tap(tester, _button('Để sau'));
      expect(find.text(_addCameraStub), findsOneWidget);
    });
  });
}

FakeNotificationService _notifications(ProviderContainer container) =>
    container.read(notificationServiceProvider) as FakeNotificationService;
