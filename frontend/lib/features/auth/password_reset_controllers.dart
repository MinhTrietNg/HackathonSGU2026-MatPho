import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/user.dart';
import '../../data/providers.dart';

final forgotPasswordControllerProvider =
    NotifierProvider.autoDispose<
      ForgotPasswordController,
      AsyncValue<OtpChallenge?>
    >(ForgotPasswordController.new);

class ForgotPasswordController extends Notifier<AsyncValue<OtpChallenge?>> {
  @override
  AsyncValue<OtpChallenge?> build() => const AsyncData(null);

  Future<void> submit(String phone) async {
    if (state.isLoading) return;
    state = const AsyncLoading();
    final result = await AsyncValue.guard(
      () => ref.read(authRepositoryProvider).requestPasswordReset(phone),
    );
    if (ref.mounted) state = result;
  }

  void reset() {
    if (state is! AsyncData || state.value != null) {
      state = const AsyncData(null);
    }
  }
}

final newPasswordControllerProvider =
    NotifierProvider.autoDispose<NewPasswordController, AsyncValue<bool>>(
      NewPasswordController.new,
    );

class NewPasswordController extends Notifier<AsyncValue<bool>> {
  @override
  AsyncValue<bool> build() => const AsyncData(false);

  Future<void> submit({
    required String resetToken,
    required String newPassword,
  }) async {
    if (state.isLoading) return;
    state = const AsyncLoading();
    final result = await AsyncValue.guard(() async {
      await ref
          .read(authRepositoryProvider)
          .setNewPassword(resetToken: resetToken, newPassword: newPassword);
      return true;
    });
    if (ref.mounted) state = result;
  }
}
