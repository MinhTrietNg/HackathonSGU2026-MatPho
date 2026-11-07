import 'package:flutter/material.dart';

import '../theme/theme.dart';
import 'mp_dashed_border.dart';

class MpListCard extends StatelessWidget {
  const MpListCard({
    super.key,
    required this.thumbnail,
    required this.title,
    required this.subtitle,
    this.badge,
    this.trailing,
    this.onTap,
    this.dashed = false,
    this.dimmed = false,
  });

  final Widget thumbnail;
  final String title;
  final String subtitle;
  final Widget? badge;
  final Widget? trailing;
  final VoidCallback? onTap;
  final bool dashed;
  final bool dimmed;

  static const _radius = 14.0;
  static const _dashWidth = 1.5;
  static const thumbnailSize = Size(64, 48);

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    Widget slot = Container(
      width: thumbnailSize.width,
      height: thumbnailSize.height,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: dashed ? c.brandAccentSoft : c.bgBase,
        borderRadius: BorderRadius.circular(10),
      ),
      child: OverflowBox(
        minWidth: 0,
        minHeight: 0,
        maxWidth: double.infinity,
        maxHeight: double.infinity,
        child: thumbnail,
      ),
    );
    if (dimmed) slot = Opacity(opacity: 0.45, child: slot);

    final border = dashed ? _dashWidth : 0.0;
    Widget card = Container(
      padding: EdgeInsets.symmetric(
        horizontal: 14 + border,
        vertical: 12 + border,
      ),
      decoration: dashed
          ? null
          : BoxDecoration(
              color: c.bgCard,
              borderRadius: BorderRadius.circular(_radius),
            ),
      child: Row(
        spacing: 12,
        children: [
          slot,
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              spacing: 2,
              children: [
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: t.body.copyWith(
                    fontWeight: FontWeight.w700,
                    color: dimmed ? c.textSecondary : c.textPrimary,
                  ),
                ),
                Text(
                  subtitle,
                  style: t.caption.copyWith(
                    fontWeight: FontWeight.w500,
                    color: c.textSecondary,
                  ),
                ),
                ?badge,
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
    if (dashed) {
      card = MpDashedBorder(
        color: c.brandAccentFg,
        radius: _radius,
        width: _dashWidth,
        child: card,
      );
    }
    return MergeSemantics(
      child: Semantics(
        button: onTap != null,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: card,
        ),
      ),
    );
  }
}
