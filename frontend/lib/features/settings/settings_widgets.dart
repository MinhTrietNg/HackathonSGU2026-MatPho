import 'package:flutter/material.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_toast.dart';
import '../../data/errors.dart';

void showSettingsFailureToast(
  BuildContext context,
  Object error, {
  double bottom = MpToast.defaultBottom,
}) {
  final c = context.mpColors;
  final network = error is NetworkException;
  showMpToast(
    context,
    MpToast(
      icon: MpDuotoneIcon(
        network ? MpIcons.wifiOff : MpIcons.alert,
        outline: c.statusWarn,
        accent: c.statusWarn,
        size: 18,
      ),
      title: network
          ? 'Không có mạng. Kiểm tra kết nối rồi thử lại.'
          : 'Máy chủ đang bận. Thử lại sau ít phút.',
    ),
    duration: const Duration(seconds: 4),
    bottom: bottom,
  );
}
