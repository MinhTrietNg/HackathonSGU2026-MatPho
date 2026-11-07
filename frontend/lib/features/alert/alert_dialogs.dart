library;

import 'package:flutter/material.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_dialog.dart';
import '../../core/widgets/mp_duotone_icon.dart';

Future<bool> confirmFalseAlarm(BuildContext context) => showMpConfirm(
  context,
  const MpConfirmDialog(
    illustration: _GlyphDisc(MpIcons.flag),
    title: 'Báo nhầm?',
    body: 'AI sẽ ghi nhận đây không phải cháy và tắt cảnh báo này.',
    confirmLabel: 'Xác nhận',
    confirmKind: MpButtonKind.report,
    cancelLabel: 'Không',
  ),
);

Future<bool> confirmResolved(BuildContext context) => showMpConfirm(
  context,
  const MpConfirmDialog(
    illustration: _GlyphDisc(MpIcons.check),
    title: 'Đã xử lý xong?',
    body: 'Cảnh báo sẽ đóng lại và được lưu vào Lịch sử.',
    confirmLabel: 'Xác nhận',
    confirmKind: MpButtonKind.resolve,
    cancelLabel: 'Không',
  ),
);

class _GlyphDisc extends StatelessWidget {
  const _GlyphDisc(this.icon);

  final String icon;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Container(
      width: 64,
      height: 64,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: c.brandAccentSoft,
        shape: BoxShape.circle,
      ),
      child: MpDuotoneIcon(
        icon,
        outline: c.textPrimary,
        accent: c.brandAccent,
        size: 28,
      ),
    );
  }
}
