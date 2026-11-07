library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/widgets/mp_animated_illustrations.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_page.dart';
import '../../data/models/settings.dart';
import 'auth_widgets.dart';
import 'permission_controller.dart';

class NotificationsDeniedScreen extends ConsumerWidget {
  const NotificationsDeniedScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen(notificationPermissionProvider, (previous, next) {
      if (previous case AsyncData(:final value)
          when value != NotificationPermission.granted &&
              next.value == NotificationPermission.granted) {
        finishOnboarding(context, ref);
      }
    });

    return MpPage(
      children: [
        const Spacer(),
        Center(
          child: MpPermNotifyIllustration(size: Size(220, 220 * 180 / 280)),
        ),
        const AuthHeadline(
          title: 'Có thể bỏ lỡ báo cháy',
          subtitle: 'Vào Cài đặt › Mắt Phố › Thông báo.',
          gap: 8,
        ),
        const Spacer(),
        MpButton(
          label: 'Mở Cài đặt',
          icon: MpIcons.settings,
          onPressed: ref
              .read(notificationPermissionProvider.notifier)
              .openSystemSettings,
        ),
        MpButton(
          label: 'Để sau',
          kind: MpButtonKind.ghost,
          onPressed: () => finishOnboarding(context, ref),
        ),
      ],
    );
  }
}
