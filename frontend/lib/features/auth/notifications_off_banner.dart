import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/widgets/mp_banner.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../data/models/settings.dart';
import 'permission_controller.dart';

class NotificationsOffBanner extends ConsumerWidget {
  const NotificationsOffBanner({super.key, this.unlessGranted = false});

  final bool unlessGranted;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final permission = ref.watch(notificationPermissionProvider).value;
    final off = unlessGranted
        ? permission != null && permission != NotificationPermission.granted
        : permission == NotificationPermission.denied;
    if (!off) {
      return const SizedBox.shrink();
    }
    return MpBanner(
      tone: MpBannerTone.warn,
      icon: MpIcons.bell,
      title: 'Có thể bỏ lỡ báo cháy',
      body: 'Vào Cài đặt › Mắt Phố › Thông báo.',
      actionLabel: 'Mở Cài đặt',
      onAction: ref
          .read(notificationPermissionProvider.notifier)
          .openSystemSettings,
    );
  }
}
