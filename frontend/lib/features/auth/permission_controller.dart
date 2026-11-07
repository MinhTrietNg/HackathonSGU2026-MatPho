import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/dev_flags.dart';
import '../../data/models/settings.dart';
import '../../data/providers.dart';
import '../cameras/camera_routes.dart';
import 'auth_routes.dart';
import 'auth_session.dart';

final notificationPermissionProvider =
    AsyncNotifierProvider<
      NotificationPermissionNotifier,
      NotificationPermission
    >(NotificationPermissionNotifier.new);

class NotificationPermissionNotifier
    extends AsyncNotifier<NotificationPermission> {
  @override
  Future<NotificationPermission> build() =>
      ref.watch(notificationServiceProvider).status();

  Future<void> refresh() async {
    final next = await AsyncValue.guard(
      ref.read(notificationServiceProvider).status,
    );
    if (!ref.mounted) return;
    if (next case AsyncData(:final value) when value == state.value) return;
    state = next;
  }

  Future<NotificationPermission> request() async {
    final result = await ref.read(notificationServiceProvider).request();
    if (ref.mounted) state = AsyncData(result);
    return result;
  }

  Future<void> openSystemSettings() async {
    await ref.read(notificationServiceProvider).openSystemSettings();
    await refresh();
  }
}

final notificationPermissionControllerProvider =
    NotifierProvider.autoDispose<
      NotificationPermissionController,
      AsyncValue<NotificationPermission?>
    >(NotificationPermissionController.new);

class NotificationPermissionController
    extends Notifier<AsyncValue<NotificationPermission?>> {
  @override
  AsyncValue<NotificationPermission?> build() => const AsyncData(null);

  Future<void> request() async {
    if (state.isLoading) return;
    state = const AsyncLoading();
    final result = await AsyncValue.guard(
      () => ref.read(notificationPermissionProvider.notifier).request(),
    );
    if (ref.mounted) state = result;
  }
}

final onboardingEveryLoginProvider = Provider<bool>(
  (ref) => kOnboardingEveryLogin,
);

bool onboardingNeeded(
  NotificationPermission permission, {
  required bool everyLogin,
}) => everyLogin || permission == NotificationPermission.notDetermined;

Future<void> continueAfterRegistration(
  BuildContext context,
  WidgetRef ref,
) async {
  final router = GoRouter.of(context);
  var permission = NotificationPermission.notDetermined;
  try {
    permission = await ref.read(notificationServiceProvider).status();
  } on Object {
    // Unknown: ask.
  }
  if (!context.mounted) return;
  if (onboardingNeeded(
    permission,
    everyLogin: ref.read(onboardingEveryLoginProvider),
  )) {
    router.go(AuthRoutes.notificationPermission);
  } else {
    await finishOnboarding(context, ref);
  }
}

Future<void> finishOnboarding(BuildContext context, WidgetRef ref) =>
    enterMonitor(
      context,
      ref,
      addCamera: switch (ref.read(authSessionProvider)) {
        SignedIn(:final newAccount) => newAccount,
        _ => false,
      },
    );
