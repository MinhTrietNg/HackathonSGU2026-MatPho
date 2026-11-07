import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;

import 'package:mat_pho/core/widgets/mp_tab_bar.dart';
import '../../fakes/fake_data.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/settings/change_password_screen.dart';
import 'package:mat_pho/features/settings/settings_dialogs.dart';
import 'package:mat_pho/features/settings/settings_screen.dart';
import 'package:mat_pho/features/settings/test_alert_screen.dart';
import '../gallery_registry.dart';
import '../gallery_scope.dart';

final _h1Overrides = <Override>[
  authSessionProvider.overrideWith(_SignedInAsMinhAnh.new),
];

final rowHEntries = <GalleryEntry>[
  GalleryEntry(
    code: 'H1',
    title: 'Cài đặt',
    builder: (_) =>
        GalleryScope(overrides: _h1Overrides, child: const _SettingsTab()),
  ),
  GalleryEntry(
    code: 'H4',
    title: 'Gửi thử cảnh báo',
    builder: (_) => const GalleryScope(child: TestAlertScreen()),
  ),
  GalleryEntry(
    code: 'H5',
    title: 'Đổi mật khẩu',
    builder: (_) => const GalleryScope(
      child: ChangePasswordScreen(
        initialCurrent: FakeData.password,
        initialNew: 'matkhaumoi12',
        initialConfirmation: 'matkhaumoi12',
        previewFocused: true,
      ),
    ),
  ),
  GalleryEntry(
    code: 'H6',
    title: 'Đăng xuất (overlay)',
    builder: (_) => GalleryScope(
      overrides: _h1Overrides,
      child: _ShowOnStart(show: confirmLogout, child: const _SettingsTab()),
    ),
  ),
];

class _SettingsTab extends StatelessWidget {
  const _SettingsTab();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: const SettingsScreen(),
      bottomNavigationBar: MpTabBar(currentIndex: 2, onTap: (_) {}),
    );
  }
}

class _ShowOnStart extends StatefulWidget {
  const _ShowOnStart({required this.show, required this.child});

  final void Function(BuildContext context) show;
  final Widget child;

  @override
  State<_ShowOnStart> createState() => _ShowOnStartState();
}

class _ShowOnStartState extends State<_ShowOnStart> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) widget.show(context);
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

class _SignedInAsMinhAnh extends AuthSessionNotifier {
  @override
  AuthSession build() => const SignedIn(FakeData.user);
}
