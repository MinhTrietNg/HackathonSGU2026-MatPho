library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/widgets/mp_animated_illustrations.dart';
import '../../core/widgets/mp_banner.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_page.dart';
import '../auth/auth_widgets.dart';
import '../auth/notifications_off_banner.dart';
import 'settings_state.dart';

class TestAlertScreen extends ConsumerWidget {
  const TestAlertScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.mpColors;
    final t = context.mpText;
    final test = ref.watch(testAlertProvider);

    final Widget? result = switch (test) {
      AsyncData(:final value) when value.loudWhenSilent => Semantics(
        liveRegion: true,
        container: true,
        child: MpBanner(
          tone: MpBannerTone.ok,
          icon: MpIcons.check,
          title: 'Đã nhận sau ${formatSeconds(value.receivedAfter)}',
          body: 'Máy kêu cả khi im lặng. Ổn rồi.',
          outlined: false,
        ),
      ),
      AsyncData(:final value) => MpBanner(
        tone: MpBannerTone.warn,
        icon: MpIcons.sound,
        title: 'Đã nhận sau ${formatSeconds(value.receivedAfter)}',
        body:
            'Máy chưa kêu khi im lặng. Bật "Kêu cả khi im lặng" trong Cài đặt.',
      ),
      AsyncError(error: TestAlertBlocked()) => const NotificationsOffBanner(
        unlessGranted: true,
      ),
      AsyncError(:final error) => authFailureBanner(error),
      _ => null,
    };

    return MpPage(
      header: MpHeader.back(
        title: 'Thử báo cháy',
        onBack: () =>
            context.canPop() ? context.pop() : context.go(AppRoutes.settings),
      ),
      headerBottom: 14,
      gap: 14,
      children: [
        const Center(
          child: MpPermNotifyIllustration(size: Size(240, 240 * 180 / 280)),
        ),
        Column(
          spacing: 6,
          children: [
            Text(
              'Máy có kêu không?',
              textAlign: TextAlign.center,
              style: t.title.copyWith(
                fontWeight: FontWeight.w800,
                color: c.textPrimary,
              ),
            ),
            Text(
              'Gửi một thông báo thử, giống hệt cảnh báo cháy thật nhưng có '
              'nhãn "THỬ".',
              textAlign: TextAlign.center,
              style: t.body.copyWith(
                fontWeight: FontWeight.w500,
                color: c.textSecondary,
              ),
            ),
          ],
        ),
        ?result,
        const Spacer(),
        MpButton(
          label: 'Thử lại',
          icon: MpIcons.bell,
          onPressed: test.isLoading
              ? null
              : ref.read(testAlertProvider.notifier).send,
        ),
      ],
    );
  }
}
