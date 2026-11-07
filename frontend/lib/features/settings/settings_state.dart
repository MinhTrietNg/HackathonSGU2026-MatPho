import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/errors.dart';
import '../../data/models/models.dart';
import '../../data/providers.dart';
import '../auth/auth_session.dart';
import '../groups/current_group.dart';

final settingsUserProvider = Provider<User?>(
  (ref) => switch (ref.watch(authSessionProvider)) {
    SignedIn(:final user) => user,
    _ => null,
  },
);

String initialsOf(String fullName) {
  final words = fullName.trim().split(RegExp(r'\s+'));
  final given = words.length > 1 ? words.skip(1).toList() : words;
  final picked = given.length > 2 ? given.sublist(given.length - 2) : given;
  return picked.map((w) => w.isEmpty ? '' : w[0].toUpperCase()).join();
}

final settingsGroupCountProvider = FutureProvider<int>(
  (ref) async => (await ref.watch(
    groupsProvider.future,
  )).where((g) => !g.isPersonal).length,
);

final loudWhenSilentProvider = AsyncNotifierProvider<LoudWhenSilent, bool>(
  LoudWhenSilent.new,
);

class LoudWhenSilent extends AsyncNotifier<bool> {
  @override
  Future<bool> build() {
    ref.watch(sessionUserIdProvider);
    return ref.watch(settingsRepositoryProvider).loudWhenSilent();
  }

  Future<void> set(bool enabled) async {
    final previous = state.value;
    state = AsyncData(enabled);
    try {
      await ref.read(settingsRepositoryProvider).setLoudWhenSilent(enabled);
    } on MpException {
      if (ref.mounted && previous != null) state = AsyncData(previous);
    }
  }
}

final testAlertProvider =
    NotifierProvider.autoDispose<TestAlert, AsyncValue<TestAlertResult>>(
      TestAlert.new,
    );

class TestAlert extends Notifier<AsyncValue<TestAlertResult>> {
  @override
  AsyncValue<TestAlertResult> build() {
    Future.microtask(send);
    return const AsyncLoading();
  }

  Future<void> send() async {
    if (!ref.mounted) return;
    state = const AsyncLoading();
    final result = await AsyncValue.guard(() async {
      final permission = await ref.read(notificationServiceProvider).status();
      if (permission != NotificationPermission.granted) {
        throw const TestAlertBlocked();
      }
      final received = await ref
          .read(settingsRepositoryProvider)
          .sendTestAlert();
      await ref.read(notificationServiceProvider).showTestAlert();
      return received;
    });
    if (ref.mounted) state = result;
  }
}

final class TestAlertBlocked implements Exception {
  const TestAlertBlocked();
}

String formatSeconds(Duration d) =>
    '${(d.inMilliseconds / 1000).toStringAsFixed(1).replaceAll('.', ',')} giây';

final changePasswordProvider =
    NotifierProvider.autoDispose<ChangePassword, AsyncValue<bool>>(
      ChangePassword.new,
    );

class ChangePassword extends Notifier<AsyncValue<bool>> {
  @override
  AsyncValue<bool> build() => const AsyncData(false);

  Future<void> submit({
    required String currentPassword,
    required String newPassword,
  }) async {
    if (state.isLoading) return;
    state = const AsyncLoading();
    final result = await AsyncValue.guard(() async {
      await ref
          .read(settingsRepositoryProvider)
          .changePassword(
            currentPassword: currentPassword,
            newPassword: newPassword,
          );
      return true;
    });
    if (ref.mounted) state = result;
  }

  void reset() {
    if (state.hasError) state = const AsyncData(false);
  }
}
