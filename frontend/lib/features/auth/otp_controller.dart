import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/user.dart';
import '../../data/providers.dart';
import 'auth_session.dart';

final class OtpState {
  const OtpState({
    required this.challenge,
    this.verify = const AsyncData(null),
    this.resend = const AsyncData(null),
  });

  final OtpChallenge challenge;
  final AsyncValue<OtpVerified?> verify;
  final AsyncValue<void> resend;
}

final otpControllerProvider = NotifierProvider.autoDispose
    .family<OtpController, OtpState, OtpChallenge>(OtpController.new);

class OtpController extends Notifier<OtpState> {
  OtpController(this.initialChallenge);

  final OtpChallenge initialChallenge;

  @override
  OtpState build() => OtpState(challenge: initialChallenge);

  Future<void> verify(String code) async {
    if (state.verify.isLoading) return;
    final challenge = state.challenge;
    state = OtpState(challenge: challenge, verify: const AsyncLoading());
    final result = await AsyncValue.guard(() async {
      final verified = await ref
          .read(authRepositoryProvider)
          .verifyOtp(challenge: challenge, code: code);
      if (verified case RegistrationCompleted(:final user)) {
        ref.read(authSessionProvider.notifier).signIn(user, newAccount: true);
      }
      return verified;
    });
    if (ref.mounted) {
      state = OtpState(challenge: state.challenge, verify: result);
    }
  }

  Future<void> resend() async {
    if (state.resend.isLoading) return;
    final before = state;
    state = OtpState(
      challenge: before.challenge,
      verify: before.verify,
      resend: const AsyncLoading(),
    );
    try {
      final challenge = await ref
          .read(authRepositoryProvider)
          .resendOtp(before.challenge);
      if (ref.mounted) state = OtpState(challenge: challenge);
    } catch (error, stack) {
      if (ref.mounted) {
        state = OtpState(
          challenge: before.challenge,
          verify: before.verify,
          resend: AsyncError(error, stack),
        );
      }
    }
  }
}
