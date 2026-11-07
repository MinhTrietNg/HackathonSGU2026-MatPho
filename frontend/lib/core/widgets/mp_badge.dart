import 'package:flutter/material.dart';

import '../theme/theme.dart';
import 'mp_ceil_width.dart';

enum MpBadgeTone { fire, ok, warn, neutral, accent, live }

class MpBadge extends StatelessWidget {
  const MpBadge({
    super.key,
    required this.label,
    required this.tone,
    this.dot = true,
  });

  final String label;
  final MpBadgeTone tone;
  final bool dot;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final (bg, fg) = switch (tone) {
      MpBadgeTone.fire => (c.statusFireSoft, c.statusFire),
      MpBadgeTone.ok => (c.statusOkSoft, c.statusOk),
      MpBadgeTone.warn => (c.statusWarnSoft, c.statusWarn),
      MpBadgeTone.neutral => (c.bgRaised, c.textSecondary),
      MpBadgeTone.accent => (c.brandAccentSoft, c.brandAccent),
      MpBadgeTone.live => (c.brandAccentSoft, c.brandAccentFg),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(99),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        spacing: 6,
        children: [
          if (dot)
            Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(color: fg, shape: BoxShape.circle),
            ),
          MpCeilWidth(
            child: Text(
              label,
              style: context.mpText.label.copyWith(fontSize: 12, color: fg),
            ),
          ),
        ],
      ),
    );
  }
}
