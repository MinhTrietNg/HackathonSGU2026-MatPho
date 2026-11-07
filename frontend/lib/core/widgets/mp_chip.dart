import 'package:flutter/material.dart';

import '../theme/theme.dart';
import 'mp_ceil_width.dart';
import 'mp_dashed_border.dart';

enum MpChipStyle { outlined, suggestion, filled, add }

class MpChip extends StatelessWidget {
  const MpChip({
    super.key,
    required this.label,
    required this.onTap,
    this.selected = false,
    this.style = MpChipStyle.outlined,
  });

  final String label;
  final VoidCallback? onTap;
  final bool selected;
  final MpChipStyle style;

  static const _radius = 99.0;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final (Color bg, Color fg, Color? line) = switch (style) {
      MpChipStyle.outlined || MpChipStyle.suggestion when selected => (
        c.brandAccentSoft,
        c.brandAccentFg,
        c.brandAccent,
      ),
      MpChipStyle.outlined ||
      MpChipStyle.suggestion => (c.bgCard, c.textSecondary, c.lineSubtle),
      MpChipStyle.filled when selected => (
        c.brandAccent,
        c.brandOnAccent,
        null,
      ),
      MpChipStyle.filled => (c.bgCard, c.textSecondary, null),
      MpChipStyle.add => (c.bgCard, c.brandAccentFg, null),
    };
    final padding = switch (style) {
      MpChipStyle.filled => const EdgeInsets.symmetric(
        horizontal: 9,
        vertical: 7,
      ),
      MpChipStyle.suggestion => const EdgeInsets.symmetric(
        horizontal: 14,
        vertical: 8,
      ),
      MpChipStyle.outlined => const EdgeInsets.symmetric(
        horizontal: 9,
        vertical: 8,
      ),
      MpChipStyle.add => const EdgeInsets.symmetric(
        horizontal: 10,
        vertical: 9,
      ),
    };

    Widget chip = Container(
      padding: padding,
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(_radius),
        border: line == null ? null : Border.all(color: line),
      ),
      child: MpCeilWidth(
        child: Text(label, style: context.mpText.label.copyWith(color: fg)),
      ),
    );
    if (style == MpChipStyle.add) {
      chip = MpDashedBorder(color: c.lineSubtle, radius: _radius, child: chip);
    }

    return Semantics(
      button: true,
      selected: style == MpChipStyle.add ? null : selected,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: chip,
      ),
    );
  }
}
