import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/user.dart';
import '../../data/providers.dart';

final class RegisterState {
  const RegisterState({
    this.phoneCheck = const AsyncData(null),
    this.submit = const AsyncData(null),
  });

  final AsyncValue<void> phoneCheck;
  final AsyncValue<OtpChallenge?> submit;

  RegisterState copyWith({
    AsyncValue<void>? phoneCheck,
    AsyncValue<OtpChallenge?>? submit,
  }) => RegisterState(
    phoneCheck: phoneCheck ?? this.phoneCheck,
    submit: submit ?? this.submit,
  );
}

final registerControllerProvider =
    NotifierProvider.autoDispose<RegisterController, RegisterState>(
      RegisterController.new,
    );

class RegisterController extends Notifier<RegisterState> {
  @override
  RegisterState build() => const RegisterState();

  Future<void> checkPhone(String phone) async {
    state = state.copyWith(phoneCheck: const AsyncLoading());
    final result = await AsyncValue.guard(
      () => ref.read(authRepositoryProvider).checkPhoneAvailable(phone),
    );
    if (ref.mounted) state = state.copyWith(phoneCheck: result);
  }

  void phoneChanged() {
    if (state.phoneCheck is! AsyncData || state.submit is AsyncError) {
      state = const RegisterState();
    }
  }

  Future<void> submit({
    required String fullName,
    required String phone,
    required String password,
  }) async {
    if (state.submit.isLoading) return;
    state = state.copyWith(submit: const AsyncLoading());
    final result = await AsyncValue.guard(
      () => ref
          .read(authRepositoryProvider)
          .register(fullName: fullName, phone: phone, password: password),
    );
    if (ref.mounted) state = state.copyWith(submit: result);
  }

  void challengeShown() =>
      state = state.copyWith(submit: const AsyncData(null));
}
