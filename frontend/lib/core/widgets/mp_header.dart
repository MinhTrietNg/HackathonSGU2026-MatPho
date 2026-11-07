import 'package:flutter/material.dart';

import '../theme/theme.dart';
import 'mp_duotone_icon.dart';
import 'mp_icon_button.dart';

class MpHeader extends StatelessWidget {
  const MpHeader.back({
    super.key,
    required this.title,
    required VoidCallback this.onBack,
    this.action,
  });

  const MpHeader.title({super.key, required this.title, this.action})
    : onBack = null;

  final String title;

  final VoidCallback? onBack;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final isBack = onBack != null;
    final style = isBack
        ? t.headline.copyWith(fontWeight: FontWeight.w700, color: c.textPrimary)
        : t.title.copyWith(fontWeight: FontWeight.w800, color: c.textPrimary);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        spacing: 10,
        children: [
          if (isBack)
            MpIconButton(
              icon: MpIcons.back,
              semanticLabel: 'Quay lại',
              onPressed: onBack,
            ),
          Expanded(
            child: Semantics(header: true, child: Text(title, style: style)),
          ),
          ?action,
        ],
      ),
    );
  }
}
