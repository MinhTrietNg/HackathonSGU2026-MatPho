library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/mp_overlay_colors.dart';
import '../../core/theme/theme.dart';
import '../../core/time_format.dart';
import '../../core/widgets/mp_ceil_width.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_feed_placeholder.dart';
import '../../core/widgets/mp_feed_tag.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../core/widgets/mp_still.dart';
import '../../data/models/models.dart';
import '../../data/providers.dart';
import 'feed_player.dart';
import 'feed_snapshot.dart';

typedef WatchArt = ({String art, String? overlay, double overlayOpacity});

const _faintSmoke = 0.45;

WatchArt watchArtOf(DetectionState state) => switch (state) {
  DetectionVerifying(verdict: final _?) || DetectionNotified() => (
    art: MpIllustrations.feedFire,
    overlay: null,
    overlayOpacity: 1,
  ),
  DetectionVerifying(:final steps) when steps.length == 1 => (
    art: MpIllustrations.feed,
    overlay: MpIllustrations.feedSmoke,
    overlayOpacity: _faintSmoke,
  ),
  DetectionVerifying() => (
    art: MpIllustrations.feedSmoke,
    overlay: null,
    overlayOpacity: 1,
  ),
  _ => (art: MpIllustrations.feed, overlay: null, overlayOpacity: 1),
};

class WatchFeedArt extends StatelessWidget {
  const WatchFeedArt(this.art, {super.key});

  final WatchArt art;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, box) {
        final scale = [
          box.maxWidth / MpIllustration.figmaSize.width,
          box.maxHeight / MpIllustration.figmaSize.height,
        ].reduce((a, b) => a > b ? a : b);
        final size = MpIllustration.figmaSize * scale;
        return OverflowBox(
          maxWidth: double.infinity,
          maxHeight: double.infinity,
          child: SizedBox.fromSize(
            size: size,
            child: Stack(
              children: [
                MpIllustration(art.art, size: size),
                if (art.overlay case final overlay?)
                  Opacity(
                    opacity: art.overlayOpacity,
                    child: MpIllustration(overlay, size: size),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class WatchFeedPicture extends ConsumerWidget {
  const WatchFeedPicture({
    super.key,
    required this.art,
    this.video,
    this.still,
    this.snapshot,
  });

  final WatchArt art;
  final FeedSource? video;

  final ImageProvider? still;

  final FeedSnapshotTarget? snapshot;

  @override
  Widget build(BuildContext context, WidgetRef ref) => switch (video) {
    final source? => FeedVideo(
      source: source,
      still: still,
      snapshot: snapshot,
    ),
    null when ref.watch(demoSceneArtProvider) => WatchFeedArt(art),
    null => const MpFeedPlaceholder(caption: 'Không có hình trực tiếp'),
  };
}

class WatchFeed extends StatelessWidget {
  const WatchFeed({
    super.key,
    required this.art,
    required this.place,
    required this.clock,
    this.border,
    this.onFullScreen,
    this.video,
    this.still,
    this.snapshot,
  });

  final WatchArt art;

  final String place;

  final DateTime Function() clock;
  final Color Function(MpColors c)? border;
  final VoidCallback? onFullScreen;

  final FeedSource? video;

  final ImageProvider? still;

  final FeedSnapshotTarget? snapshot;

  @override
  Widget build(BuildContext context) =>
      MpDarkIsland(child: Builder(builder: _buildFeed));

  Widget _buildFeed(BuildContext context) {
    final c = context.mpColors;
    final radius = BorderRadius.circular(16);
    final placeText = place.toUpperCase();
    return AspectRatio(
      aspectRatio: MpStill.aspectRatio,
      child: _buildBox(context, c, radius, placeText),
    );
  }

  Widget _buildBox(
    BuildContext context,
    MpColors c,
    BorderRadius radius,
    String placeText,
  ) {
    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(color: c.bgSurface, borderRadius: radius),
      foregroundDecoration: border == null
          ? null
          : BoxDecoration(
              borderRadius: radius,
              border: Border.all(color: border!(c), width: 1.5),
            ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          WatchFeedPicture(
            art: art,
            video: video,
            still: still,
            snapshot: snapshot,
          ),
          Positioned(
            left: 10,
            top: 10,
            child: WatchTicker(
              clock: clock,
              builder: (now) =>
                  MpFeedTag('$placeText · ${formatFeedTime(now)}'),
            ),
          ),
          if (onFullScreen case final open?)
            Positioned(
              right: 10,
              bottom: 10,
              child: _FullScreenPill(onTap: open),
            ),
        ],
      ),
    );
  }
}

class WatchTicker extends StatefulWidget {
  const WatchTicker({super.key, required this.clock, required this.builder});

  final DateTime Function() clock;
  final Widget Function(DateTime now) builder;

  @override
  State<WatchTicker> createState() => _WatchTickerState();
}

class _WatchTickerState extends State<WatchTicker> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => setState(() {}));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.builder(widget.clock());
}

class _FullScreenPill extends StatelessWidget {
  const _FullScreenPill({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.fromLTRB(10, 6, 12, 6),
          decoration: BoxDecoration(
            color: MpOverlayColors.feedPill,
            borderRadius: BorderRadius.circular(99),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            spacing: 6,
            children: [
              const CustomPaint(
                size: Size.square(14),
                painter: _ExpandGlyph(MpOverlayColors.onFeed),
              ),
              MpCeilWidth(
                child: Text(
                  'Toàn màn hình',
                  maxLines: 1,
                  style: context.mpText.caption.copyWith(
                    fontWeight: FontWeight.w700,
                    height: kTextHeightNone,
                    color: MpOverlayColors.onFeed,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ExpandGlyph extends CustomPainter {
  const _ExpandGlyph(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final k = size.width / 14;
    final path = Path();
    for (final corner in const [
      [0.0, 5.0, 0.0, 0.0, 5.0, 0.0],
      [9.0, 0.0, 14.0, 0.0, 14.0, 5.0],
      [14.0, 9.0, 14.0, 14.0, 9.0, 14.0],
      [5.0, 14.0, 0.0, 14.0, 0.0, 9.0],
    ]) {
      path
        ..moveTo(corner[0] * k, corner[1] * k)
        ..lineTo(corner[2] * k, corner[3] * k)
        ..lineTo(corner[4] * k, corner[5] * k);
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.8
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );
  }

  @override
  bool shouldRepaint(_ExpandGlyph old) => old.color != color;
}

typedef WatchStatusRow = ({
  Color dot,
  String title,
  String? value,
  Color? valueColor,
  String? description,
  bool bold,
});

class WatchStatusCard extends StatelessWidget {
  const WatchStatusCard({
    super.key,
    required this.rows,
    this.link,
    this.onLink,
    this.summary,
  });

  final List<WatchStatusRow> rows;
  final String? link;
  final VoidCallback? onLink;
  final String? summary;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final natural = t.body.copyWith(height: kTextHeightNone);
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 6, 14, 10),
      decoration: BoxDecoration(
        color: c.bgCard,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final row in rows)
            MergeSemantics(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 7),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  spacing: 10,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Container(
                        width: 10,
                        height: 10,
                        decoration: BoxDecoration(
                          color: row.dot,
                          borderRadius: BorderRadius.circular(5),
                        ),
                      ),
                    ),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        spacing: 2,
                        children: [
                          Row(
                            spacing: 10,
                            children: [
                              Expanded(
                                child: Text(
                                  row.title,
                                  style: natural.copyWith(
                                    fontWeight: row.bold
                                        ? FontWeight.w700
                                        : FontWeight.w500,
                                    color: c.textPrimary,
                                  ),
                                ),
                              ),
                              if (row.value case final value?)
                                Text(
                                  value,
                                  style: t.mono.copyWith(
                                    fontWeight: FontWeight.w600,
                                    height: kTextHeightNone,
                                    color: row.valueColor ?? c.textSecondary,
                                  ),
                                ),
                            ],
                          ),
                          if (row.description case final description?)
                            Text(
                              description,
                              style: t.body.copyWith(
                                fontSize: 13,
                                height: 1.4,
                                fontWeight: FontWeight.w500,
                                color: c.textSecondary,
                              ),
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          if (link case final link?)
            Align(
              alignment: Alignment.centerLeft,
              child: Semantics(
                button: true,
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: onLink,
                  child: Padding(
                    padding: const EdgeInsets.only(left: 20, top: 6),
                    child: Text(
                      link,
                      style: natural.copyWith(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: c.textSecondary,
                        decoration: TextDecoration.underline,
                        decorationColor: c.textSecondary,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          if (summary case final summary?)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: c.statusOkSoft,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Row(
                  spacing: 8,
                  children: [
                    MpDuotoneIcon(
                      MpIcons.check,
                      outline: c.statusOk,
                      accent: c.statusOk,
                      size: 18,
                    ),
                    Expanded(
                      child: Text(
                        summary,
                        style: natural.copyWith(
                          fontWeight: FontWeight.w700,
                          color: c.statusOk,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class WatchNote extends StatelessWidget {
  const WatchNote({super.key, required this.icon, required this.text});

  final String icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Row(
      spacing: 8,
      children: [
        MpDuotoneIcon(
          icon,
          outline: c.brandAccentFg,
          accent: c.brandAccentFg,
          size: 16,
        ),
        Expanded(
          child: Text(
            text,
            style: context.mpText.caption.copyWith(
              fontWeight: FontWeight.w500,
              color: c.textSecondary,
            ),
          ),
        ),
      ],
    );
  }
}

String formatOffset(Duration d) => d == Duration.zero
    ? '${formatStepSeconds(d)} s'
    : '+${formatStepSeconds(d)} s';
