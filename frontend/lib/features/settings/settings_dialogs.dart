library;

import 'package:flutter/material.dart';

import '../../core/widgets/mp_dialog.dart';
import '../../core/widgets/mp_illustration.dart';

Future<bool> confirmLogout(BuildContext context) => showMpConfirm(
  context,
  const MpConfirmDialog(
    illustration: MpIllustration(
      MpIllustrations.logout,
      size: MpDialog.illustrationSize,
    ),
    title: 'Đăng xuất?',
    body: 'Máy này sẽ không nhận báo cháy nữa.',
    confirmLabel: 'Đăng xuất',
    cancelLabel: 'Ở lại',
  ),
);
