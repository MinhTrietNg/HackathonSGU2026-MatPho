import 'package:flutter/material.dart';

import '../theme/theme.dart';
import 'mp_ceil_width.dart';
import 'mp_duotone_icon.dart';

class MpSettingsRow extends StatelessWidget {
  const MpSettingsRow({
    super.key,
    required this.icon,
    required this.iconColor,
    required this.title,
    this.subtitle,
    this.value,
    this.trailing,
    this.onTap,
  });

  final String icon;

  final Color iconColor;
  final String title;
  final String? subtitle;
  final String? value;

  final Widget? trailing;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final chevron = onTap == null ? null : const MpChevron();
    final row = Container(
      color: c.bgCard,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      child: Row(
        spacing: 12,
        children: [
          Container(
            width: 40,
            height: 40,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: c.bgRaised,
              borderRadius: BorderRadius.circular(12),
            ),
            child: MpDuotoneIcon(
              icon,
              outline: iconColor,
              accent: iconColor,
              size: 22,
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              spacing: 2,
              children: [
                Text(
                  title,
                  style: t.body.copyWith(
                    fontWeight: FontWeight.w700,
                    color: c.textPrimary,
                  ),
                ),
                if (subtitle != null)
                  Text(
                    subtitle!,
                    style: t.caption.copyWith(
                      fontWeight: FontWeight.w500,
                      color: c.textSecondary,
                    ),
                  ),
              ],
            ),
          ),
          if (value != null)
            MpCeilWidth(
              child: Text(
                value!,
                style: t.mono.copyWith(
                  fontWeight: FontWeight.w600,
                  color: c.textMuted,
                ),
              ),
            ),
          ?(trailing ?? chevron),
        ],
      ),
    );
    if (onTap == null) return MergeSemantics(child: row);
    return MergeSemantics(
      child: Semantics(
        button: true,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: row,
        ),
      ),
    );
  }
}

class MpSettingsGroup extends StatelessWidget {
  const MpSettingsGroup({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 2,
        children: children,
      ),
    );
  }
}
