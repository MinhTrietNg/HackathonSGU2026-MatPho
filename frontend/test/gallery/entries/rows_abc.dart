import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;

import 'package:mat_pho/data/errors.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/models/user.dart';
import 'package:mat_pho/features/auth/forgot_password_screen.dart';
import 'package:mat_pho/features/auth/login_controller.dart';
import 'package:mat_pho/features/auth/login_screen.dart';
import 'package:mat_pho/features/auth/new_password_screen.dart';
import 'package:mat_pho/features/auth/notification_permission_screen.dart';
import 'package:mat_pho/features/auth/notifications_denied_screen.dart';
import 'package:mat_pho/features/auth/otp_controller.dart';
import 'package:mat_pho/features/auth/otp_screen.dart';
import 'package:mat_pho/features/auth/register_screen.dart';
import 'package:mat_pho/features/auth/splash_screen.dart';
import '../gallery_registry.dart';
import '../gallery_scope.dart';

typedef AuthFrame = ({
  String code,
  String title,
  Set<FakeCase> cases,
  List<Override> overrides,
  WidgetBuilder builder,
});

OtpChallenge _challenge({required Duration resendIn}) => OtpChallenge(
  id: 'otp-preview',
  phone: FakeData.user.phone,
  purpose: OtpPurpose.register,
  resendAvailableAt: FakeData.demoNow.add(resendIn),
);

final _b2Challenge = _challenge(resendIn: const Duration(seconds: 42));

final _b3Challenge = _challenge(resendIn: Duration.zero);

final authFrames = <AuthFrame>[
  (
    code: 'A1',
    title: 'Splash',
    cases: const {},
    overrides: const [],
    builder: (_) => const SplashScreen(),
  ),
  (
    code: 'A5',
    title: 'Đăng nhập',
    cases: const {},
    overrides: const [],
    builder: (_) => const LoginScreen(
      initialPhone: '0912 345 678',
      initialPassword: FakeData.password,
    ),
  ),
  (
    code: 'A6',
    title: 'Đăng nhập · sai mật khẩu',
    cases: const {FakeCase.wrongPassword},
    overrides: [
      loginControllerProvider.overrideWithBuild(
        (ref, notifier) => const AsyncError(
          WrongPasswordException(attemptsLeft: 3),
          StackTrace.empty,
        ),
      ),
    ],
    builder: (_) => const LoginScreen(
      initialPhone: '0912 345 678',
      initialPassword: '123456',
    ),
  ),
  (
    code: 'B1',
    title: 'Đăng ký',
    cases: const {},
    overrides: const [],
    builder: (_) => const RegisterScreen(
      initialFullName: 'Nguyễn Minh Anh',
      initialPhone: '0912 345 678',
      initialPassword: FakeData.password,
      initialAgreed: true,
    ),
  ),
  (
    code: 'B2',
    title: 'Nhập OTP',
    cases: const {},
    overrides: const [],
    builder: (_) => OtpScreen(challenge: _b2Challenge, initialCode: '482'),
  ),
  (
    code: 'B3',
    title: 'OTP sai / hết hạn',
    cases: const {FakeCase.otpWrong},
    overrides: [
      otpControllerProvider.overrideWithBuild(
        (ref, notifier) => OtpState(
          challenge: notifier.initialChallenge,
          verify: const AsyncError(
            OtpWrongException(attemptsLeft: 2),
            StackTrace.empty,
          ),
        ),
      ),
    ],
    builder: (_) => OtpScreen(challenge: _b3Challenge, initialCode: '482910'),
  ),
  (
    code: 'B4',
    title: 'Quên mật khẩu',
    cases: const {},
    overrides: const [],
    builder: (_) => const ForgotPasswordScreen(
      initialPhone: '0912 345 678',
      previewFocused: true,
    ),
  ),
  (
    code: 'B5',
    title: 'Mật khẩu mới',
    cases: const {},
    overrides: const [],
    builder: (_) => const NewPasswordScreen(
      resetToken: 'fake-reset-token',
      initialPassword: FakeData.password,
      initialConfirmation: 'matkhau12',
      previewFocused: true,
    ),
  ),
  (
    code: 'C1',
    title: 'Xin quyền thông báo',
    cases: const {FakeCase.notificationsNotDetermined},
    overrides: const [],
    builder: (_) => const NotificationPermissionScreen(),
  ),
  (
    code: 'C3',
    title: 'Đã từ chối thông báo',
    cases: const {FakeCase.notificationsDenied},
    overrides: const [],
    builder: (_) => const NotificationsDeniedScreen(),
  ),
];

List<GalleryEntry> _row(String row) => [
  for (final frame in authFrames)
    if (frame.code.startsWith(row))
      GalleryEntry(
        code: frame.code,
        title: frame.title,
        builder: (_) => AuthFramePreview(frame),
      ),
];

final rowAEntries = _row('A');
final rowBEntries = _row('B');
final rowCEntries = _row('C');

class AuthFramePreview extends StatelessWidget {
  const AuthFramePreview(this.frame, {super.key});

  final AuthFrame frame;

  @override
  Widget build(BuildContext context) => GalleryScope(
    cases: frame.cases,
    overrides: frame.overrides,
    child: Builder(builder: frame.builder),
  );
}
