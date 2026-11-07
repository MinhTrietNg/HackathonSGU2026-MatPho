import 'package:flutter/widgets.dart';

import '../theme/theme.dart';
import 'mp_duotone_icon.dart';

// Stands in for a camera picture the backend has not sent yet.
class MpFeedPlaceholder extends StatelessWidget {
  const MpFeedPlaceholder({super.key, this.caption, this.size});

  final String? caption;

  // Null fills the parent's bounds.
  final Size? size;

  @override
  Widget build(BuildContext context) =>
      MpDarkIsland(child: Builder(builder: _buildBox));

  Widget _buildBox(BuildContext context) {
    final c = context.mpColors;
    final caption = this.caption;
    Widget icon(double size) => MpDuotoneIcon(
      MpIcons.camera,
      outline: c.textMuted,
      accent: c.textMuted,
      size: size,
    );
    return Container(
      width: size?.width ?? double.infinity,
      height: size?.height ?? double.infinity,
      color: c.bgSurface,
      alignment: Alignment.center,
      child: caption == null
          ? icon(20)
          : Column(
              mainAxisSize: MainAxisSize.min,
              spacing: 8,
              children: [
                icon(32),
                Text(
                  caption,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: context.mpText.caption.copyWith(
                    fontWeight: FontWeight.w600,
                    color: c.textMuted,
                  ),
                ),
              ],
            ),
    );
  }
}
