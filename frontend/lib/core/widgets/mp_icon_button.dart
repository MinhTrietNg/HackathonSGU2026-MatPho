import 'package:flutter/material.dart';

import '../theme/theme.dart';
import 'mp_duotone_icon.dart';

class MpIconButton extends StatelessWidget {
  const MpIconButton({
    super.key,
    required this.icon,
    required this.semanticLabel,
    required this.onPressed,
    this.accent = false,
    this.iconAccent,
  });

  final String icon;

  final String semanticLabel;
  final VoidCallback? onPressed;

  final bool accent;

  final Color? iconAccent;

  static const size = 40.0;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final fg = accent ? c.brandOnAccent : c.textPrimary;
    return Semantics(
      button: true,
      enabled: onPressed != null,
      label: semanticLabel,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onPressed,
        child: Container(
          width: size,
          height: size,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: accent ? c.brandAccent : c.bgCard,
            borderRadius: BorderRadius.circular(12),
          ),
          child: MpDuotoneIcon(
            icon,
            outline: fg,
            accent: iconAccent ?? fg,
            size: 20,
          ),
        ),
      ),
    );
  }
}
