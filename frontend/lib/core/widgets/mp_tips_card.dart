import 'package:flutter/widgets.dart';

import '../theme/theme.dart';
import 'mp_duotone_icon.dart';

class MpTipsCard extends StatelessWidget {
  const MpTipsCard({super.key, required this.tips});

  final List<(String icon, String text)> tips;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: c.bgSurface,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 8,
        children: [
          for (final (icon, text) in tips)
            MergeSemantics(
              child: Row(
                spacing: 10,
                children: [
                  MpDuotoneIcon(
                    icon,
                    outline: c.textSecondary,
                    accent: c.textSecondary,
                    size: 18,
                  ),
                  Expanded(
                    child: Text(
                      text,
                      style: context.mpText.body.copyWith(
                        fontWeight: FontWeight.w500,
                        color: c.textSecondary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
