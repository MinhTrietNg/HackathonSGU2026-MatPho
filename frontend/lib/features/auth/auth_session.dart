import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../data/errors.dart';
import '../../data/models/user.dart';
import '../../data/providers.dart';
import '../../data/remote/core/remote_providers.dart';

sealed class AuthSession {
  const AuthSession();
}

final class SessionUnknown extends AuthSession {
  const SessionUnknown();
}

final class SignedIn extends AuthSession {
  const SignedIn(this.user, {this.newAccount = false});

  final User user;

  final bool newAccount;
}

final class SignedOut extends AuthSession {
  const SignedOut();
}

final authSessionProvider = NotifierProvider<AuthSessionNotifier, AuthSession>(
  AuthSessionNotifier.new,
);

class AuthSessionNotifier extends Notifier<AuthSession> {
  static const restoreTimeout = Duration(milliseconds: 1500);

  @override
  AuthSession build() {
    final expired = ref.read(sessionExpiredProvider).listen((_) => _expired());
    ref.onDispose(expired.cancel);
    return const SessionUnknown();
  }

  void _expired() {
    if (state is! SignedIn) return;
    unawaited(logout());
    final context = rootNavigatorKey.currentContext;
    if (context != null && context.mounted) {
      GoRouter.of(context).go(AppRoutes.login);
    }
  }

  Future<AuthSession> restore() async {
    User? user;
    try {
      user = await ref
          .read(authRepositoryProvider)
          .restoreSession()
          .timeout(restoreTimeout);
    } catch (_) {
      user = null;
    }
    final session = user == null ? const SignedOut() : SignedIn(user);
    if (ref.mounted) state = session;
    return session;
  }

  void signIn(User user, {bool newAccount = false}) =>
      state = SignedIn(user, newAccount: newAccount);

  void signOut() => state = const SignedOut();

  Future<void> logout() async {
    final sends = [
      for (final send in [...ref.read(beforeLogoutProvider)]) send(),
    ];
    signOut();
    try {
      await ref.read(notificationServiceProvider).clearFireAlerts();
      await Future.wait(sends);
    } on MpException {
      // A held action that cannot be sent is lost, as when the app is killed.
    }
    try {
      await ref.read(settingsRepositoryProvider).logout();
    } on MpException {
      // The server drops the session on its own; this phone already has.
    }
  }
}

final beforeLogoutProvider = Provider<Set<Future<void> Function()>>(
  (ref) => {},
);

final sessionUserIdProvider = Provider<String?>(
  (ref) => switch (ref.watch(authSessionProvider)) {
    SignedIn(:final user) => user.id,
    _ => null,
  },
);

String formatCountdown(Duration remaining) {
  final seconds = (remaining.inMilliseconds / 1000).ceil().clamp(0, 359999);
  return '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';
}
