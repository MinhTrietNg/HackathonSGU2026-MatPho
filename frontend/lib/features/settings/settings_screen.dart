library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/appearance.dart';
import '../../core/theme/theme.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_section_label.dart';
import '../../core/widgets/mp_settings_row.dart';
import '../../core/widgets/mp_toggle.dart';
import '../../data/models/settings.dart';
import '../../data/models/user.dart';
import '../auth/auth_session.dart';
import '../auth/notifications_off_banner.dart';
import '../auth/permission_controller.dart';
import '../groups/group_routes.dart';
import 'settings_dialogs.dart';
import 'settings_routes.dart';
import 'settings_state.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  Future<void> _logout(BuildContext context, WidgetRef ref) async {
    if (!await confirmLogout(context)) return;
    unawaited(ref.read(authSessionProvider.notifier).logout());
    if (context.mounted) context.go(AppRoutes.login);
  }

  void _openNotifications(WidgetRef ref, NotificationPermission permission) {
    final notifier = ref.read(notificationPermissionProvider.notifier);
    if (permission == NotificationPermission.notDetermined) {
      notifier.request();
    } else {
      notifier.openSystemSettings();
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.mpColors;
    final user = ref.watch(settingsUserProvider);
    final groupCount = ref.watch(settingsGroupCountProvider).value;
    final loud = ref.watch(loudWhenSilentProvider).value;
    final light = ref.watch(lightAppearanceProvider);
    final notifications = ref.watch(notificationPermissionProvider).value;

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 8, 20, 10),
              child: MpHeader.title(title: 'Cài đặt'),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  spacing: 10,
                  children: [
                    if (notifications == NotificationPermission.denied)
                      const NotificationsOffBanner(),
                    if (user != null) _ProfileCard(user),
                    const MpSectionLabel('CẢNH BÁO'),
                    MpSettingsGroup(
                      children: [
                        MpSettingsRow(
                          icon: MpIcons.bell,
                          iconColor:
                              notifications == null ||
                                  notifications ==
                                      NotificationPermission.granted
                              ? c.brandAccent
                              : c.textSecondary,
                          title: 'Thông báo',
                          value: switch (notifications) {
                            null => null,
                            NotificationPermission.granted => 'Đang bật',
                            _ => 'Đang tắt',
                          },
                          onTap: notifications == null
                              ? null
                              : () => _openNotifications(ref, notifications),
                        ),
                        MpSettingsRow(
                          icon: MpIcons.bell,
                          iconColor: c.brandAccent,
                          title: 'Thử báo cháy',
                          subtitle: 'Xem máy có kêu không',
                          onTap: () => context.push(SettingsRoutes.testAlert),
                        ),
                        MpSettingsRow(
                          icon: MpIcons.sound,
                          iconColor: c.brandAccent,
                          title: 'Kêu cả khi im lặng',
                          trailing: MpToggle(
                            value: loud ?? false,
                            semanticLabel: 'Kêu cả khi im lặng',
                            onChanged: loud == null
                                ? null
                                : ref.read(loudWhenSilentProvider.notifier).set,
                          ),
                        ),
                      ],
                    ),
                    const MpSectionLabel('GIAO DIỆN'),
                    MpSettingsGroup(
                      children: [
                        MpSettingsRow(
                          icon: MpIcons.sun,
                          iconColor: c.brandAccent,
                          title: 'Giao diện sáng',
                          trailing: MpToggle(
                            value: light,
                            semanticLabel: 'Giao diện sáng',
                            onChanged: ref
                                .read(lightAppearanceProvider.notifier)
                                .set,
                          ),
                        ),
                      ],
                    ),
                    const MpSectionLabel('TÀI KHOẢN'),
                    MpSettingsGroup(
                      children: [
                        MpSettingsRow(
                          icon: MpIcons.user,
                          iconColor: c.brandAccent,
                          title: 'Nhóm & thành viên',
                          value: groupCount == null ? null : '$groupCount',
                          onTap: () => context.push(GroupRoutes.groups),
                        ),
                        MpSettingsRow(
                          icon: MpIcons.key,
                          iconColor: c.textSecondary,
                          title: 'Đổi mật khẩu',
                          onTap: () =>
                              context.push(SettingsRoutes.changePassword),
                        ),
                        MpSettingsRow(
                          icon: MpIcons.shield,
                          iconColor: c.textSecondary,
                          title: 'Quyền riêng tư',
                          onTap: () {},
                        ),
                      ],
                    ),
                    _LogoutButton(onTap: () => _logout(context, ref)),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProfileCard extends StatelessWidget {
  const _ProfileCard(this.user);

  final User user;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return MergeSemantics(
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: c.bgCard,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          spacing: 12,
          children: [
            Container(
              width: 44,
              height: 44,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: c.brandAccentSoft,
                shape: BoxShape.circle,
              ),
              child: ExcludeSemantics(
                child: Text(
                  initialsOf(user.fullName),
                  style: t.body.copyWith(
                    fontWeight: FontWeight.w700,
                    color: c.brandAccentFg,
                  ),
                ),
              ),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                spacing: 2,
                children: [
                  Text(
                    user.fullName,
                    style: t.body.copyWith(
                      fontWeight: FontWeight.w700,
                      color: c.textPrimary,
                    ),
                  ),
                  Text(
                    formatPhone(user.phone),
                    style: t.mono.copyWith(
                      fontWeight: FontWeight.w600,
                      color: c.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LogoutButton extends StatelessWidget {
  const _LogoutButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Semantics(
      button: true,
      label: 'Đăng xuất',
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            spacing: 8,
            children: [
              MpDuotoneIcon(
                MpIcons.logout,
                outline: c.statusFire,
                accent: c.statusFire,
                size: 18,
              ),
              Text(
                'Đăng xuất',
                style: context.mpText.body.copyWith(
                  fontWeight: FontWeight.w700,
                  color: c.statusFire,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
