import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../data/models/user.dart';
import '../../data/session/emergency_token_store.dart';
import 'auth_session.dart';
import 'forgot_password_screen.dart';
import 'login_screen.dart';
import 'new_password_screen.dart';
import 'notification_permission_screen.dart';
import 'notifications_denied_screen.dart';
import 'otp_screen.dart';
import 'register_screen.dart';
import 'splash_screen.dart';

abstract final class AuthRoutes {
  static const register = '/register';

  static const otp = '/otp';

  static const forgotPassword = '/forgot-password';

  static const newPassword = '/new-password';

  static const notificationPermission = '/permission/notifications';

  static const notificationsDenied = '/permission/notifications/denied';
}

const _publicPaths = {
  AppRoutes.splash,
  AppRoutes.login,
  AuthRoutes.register,
  AuthRoutes.otp,
  AuthRoutes.forgotPassword,
  AuthRoutes.newPassword,
};

final authRoutes = <RouteBase>[
  GoRoute(
    path: AppRoutes.splash,
    builder: (context, state) => SplashScreen(
      onSessionRestored: (session) => context.go(switch (session) {
        SignedIn() =>
          appPathOrNull(state.uri.queryParameters['from']) ?? AppRoutes.monitor,
        _ => AppRoutes.login,
      }),
    ),
  ),
  GoRoute(
    path: AppRoutes.login,
    builder: (context, state) => const LoginScreen(),
  ),
  GoRoute(
    path: AuthRoutes.register,
    builder: (context, state) => const RegisterScreen(),
  ),
  GoRoute(
    path: AuthRoutes.otp,
    redirect: (context, state) =>
        state.extra is OtpChallenge ? null : AppRoutes.login,
    builder: (context, state) =>
        OtpScreen(challenge: state.extra! as OtpChallenge),
  ),
  GoRoute(
    path: AuthRoutes.forgotPassword,
    builder: (context, state) => const ForgotPasswordScreen(),
  ),
  GoRoute(
    path: AuthRoutes.newPassword,
    redirect: (context, state) =>
        state.extra is String ? null : AppRoutes.login,
    builder: (context, state) =>
        NewPasswordScreen(resetToken: state.extra! as String),
  ),
  GoRoute(
    path: AuthRoutes.notificationPermission,
    builder: (context, state) => const NotificationPermissionScreen(),
  ),
  GoRoute(
    path: AuthRoutes.notificationsDenied,
    builder: (context, state) => const NotificationsDeniedScreen(),
  ),
];

// Auth gate: session unknown → A1 splash (then back to the asked path);
// signed out → A5 unless the path is public; signed in on A5/B1 → tabs.
String? authRedirect(Ref ref, GoRouterState state) {
  final path = state.matchedLocation;

  // Emergency bypass check (ADR 0011 / Plan B):
  // When an alert is accessed with a valid emergency token, bypass authentication and splash
  if (path.startsWith('/alert/')) {
    final eventId = state.pathParameters['eventId'] ??
        (state.uri.pathSegments.length > 1 ? state.uri.pathSegments[1] : null);
    final emgTok = state.uri.queryParameters['emergency_token'];
    if (eventId != null && emgTok != null && emgTok.isNotEmpty) {
      EmergencyTokenStore.instance.save(eventId, emgTok);
    }
    if (eventId != null && EmergencyTokenStore.instance.get(eventId) != null) {
      return null;
    }
  }

  switch (ref.read(authSessionProvider)) {
    case SessionUnknown():
      if (path == AppRoutes.splash) return null;
      final target = state.uri.toString();
      return target == AppRoutes.monitor
          ? AppRoutes.splash
          : Uri(
              path: AppRoutes.splash,
              queryParameters: {'from': target},
            ).toString();
    case SignedOut():
      return _publicPaths.contains(path) ? null : AppRoutes.login;
    case SignedIn():
      final signingIn =
          path == AppRoutes.login ||
          path == AuthRoutes.register ||
          (path == AuthRoutes.otp &&
              state.extra is OtpChallenge &&
              (state.extra! as OtpChallenge).purpose == OtpPurpose.register);
      return signingIn ? AppRoutes.monitor : null;
  }
}

String? appPathOrNull(String? from) {
  if (from == null || !from.startsWith('/') || from.startsWith('//')) {
    return null;
  }
  final uri = Uri.tryParse(from);
  return uri == null || uri.hasScheme || uri.hasAuthority ? null : from;
}
