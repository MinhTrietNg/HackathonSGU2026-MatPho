import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/settings.dart';
import '../../data/providers.dart';
import 'auth_session.dart';
import 'permission_controller.dart';

enum LoginNext { notificationPermission, monitor }

final loginControllerProvider =
    NotifierProvider.autoDispose<LoginController, AsyncValue<LoginNext?>>(
      LoginController.new,
    );

class LoginController extends Notifier<AsyncValue<LoginNext?>> {
  @override
  AsyncValue<LoginNext?> build() => const AsyncData(null);

  Future<void> submit({required String phone, required String password}) async {
    if (state.isLoading) return;
    state = const AsyncLoading();
    final result = await AsyncValue.guard(() async {
      final user = await ref
          .read(authRepositoryProvider)
          .login(phone: phone, password: password);
      ref.read(authSessionProvider.notifier).signIn(user);
      var permission = NotificationPermission.notDetermined;
      try {
        permission = await ref.read(notificationServiceProvider).status();
      } on Object {
        // Unknown: C1 asks.
      }
      return onboardingNeeded(
            permission,
            everyLogin: ref.read(onboardingEveryLoginProvider),
          )
          ? LoginNext.notificationPermission
          : LoginNext.monitor;
    });
    if (ref.mounted) state = result;
  }
}
