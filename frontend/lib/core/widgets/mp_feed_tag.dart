import 'package:flutter/widgets.dart';

import '../theme/mp_overlay_colors.dart';
import '../theme/theme.dart';

class MpFeedTag extends StatelessWidget {
  const MpFeedTag(this.text, {super.key, this.style});

  final String text;

  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    final base =
        style ?? context.mpText.mono.copyWith(fontWeight: FontWeight.w600);
    return Text(
      text,
      maxLines: 1,
      style: base.copyWith(
        color: MpOverlayColors.onFeed,
        shadows: const [
          Shadow(color: MpOverlayColors.feedPill, blurRadius: 3),
          Shadow(color: MpOverlayColors.feedPill, offset: Offset(0, 1)),
        ],
      ),
    );
  }
}

String formatFeedTime(DateTime t) {
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(t.day)}/${two(t.month)}/${t.year} '
      '${two(t.hour)}:${two(t.minute)}:${two(t.second)}';
}
