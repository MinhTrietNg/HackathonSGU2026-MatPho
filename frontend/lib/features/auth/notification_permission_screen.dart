library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/widgets/mp_animated_illustrations.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_page.dart';
import '../../data/models/settings.dart';
import 'auth_routes.dart';
import 'auth_widgets.dart';
import 'permission_controller.dart';

class NotificationPermissionScreen extends ConsumerWidget {
  const NotificationPermissionScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen(notificationPermissionControllerProvider, (_, next) {
      switch (next) {
        case AsyncData(value: NotificationPermission.granted):
          finishOnboarding(context, ref);
        case AsyncData(value: NotificationPermission.denied):
          context.go(AuthRoutes.notificationsDenied);
        default:
      }
    });
    final request = ref.watch(notificationPermissionControllerProvider);

    return MpPage(
      children: [
        const Spacer(),
        ?authFailureBanner(request.error),
        const Center(child: MpPermNotifyIllustration()),
        const AuthHeadline(
          title: 'Bật thông báo',
          subtitle: 'Chỉ báo khi có cháy. Không làm phiền.',
          gap: 8,
        ),
        const Spacer(),
        MpButton(
          label: 'Cho phép thông báo',
          icon: MpIcons.bell,
          onPressed: request.isLoading
              ? null
              : ref
                    .read(notificationPermissionControllerProvider.notifier)
                    .request,
        ),
        MpButton(
          label: 'Để sau',
          kind: MpButtonKind.ghost,
          onPressed: () => context.go(AuthRoutes.notificationsDenied),
        ),
      ],
    );
  }
}
