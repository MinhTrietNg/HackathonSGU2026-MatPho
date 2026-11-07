import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_ceil_width.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_feed_placeholder.dart';
import '../../core/widgets/mp_feed_tag.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../core/widgets/mp_still.dart';

class AlertGlow extends StatelessWidget {
  const AlertGlow({super.key, required this.top});

  final double top;

  static const _size = Size(520, 300);

  static const _sigma = 40.0;
  static const _bleed = 2 * _sigma;

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: -82 - _bleed,
      top: top - _bleed,
      child: IgnorePointer(
        child: ImageFiltered(
          imageFilter: ImageFilter.blur(sigmaX: _sigma, sigmaY: _sigma),
          child: Padding(
            padding: const EdgeInsets.all(_bleed),
            child: Opacity(
              opacity: 0.7,
              child: Container(
                width: _size.width,
                height: _size.height,
                decoration: ShapeDecoration(
                  color: context.mpColors.alertGlow,
                  shape: const OvalBorder(),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class AlertEvidence extends StatelessWidget {
  const AlertEvidence({
    super.key,
    this.asset,
    this.height,
    required this.artSize,
    this.tag,
    this.onTap,
    this.still,
    this.stillUrl,
    this.video,
  });

  // Null: no drawn scene, a neutral placeholder instead.
  final String? asset;

  final double? height;
  final Size artSize;

  final String? still;

  final String? stillUrl;

  final Widget? video;
  final String? tag;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) =>
      MpDarkIsland(child: Builder(builder: _buildEvidence));

  Widget _buildEvidence(BuildContext context) {
    final c = context.mpColors;
    final local = switch ((still, asset)) {
      (final still?, _) => MpStill(still),
      (null, final asset?) => OverflowBox(
        maxWidth: double.infinity,
        maxHeight: double.infinity,
        child: MpIllustration(asset, size: artSize, animated: true),
      ),
      (null, null) => const MpFeedPlaceholder(caption: 'Chưa có ảnh'),
    };
    final box = Container(
      height: height,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: c.bgSurface,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Stack(
        children: [
          Positioned.fill(
            child:
                video ??
                switch (stillUrl) {
                  final url? => EvidenceNetworkImage(url, fallback: local),
                  null => local,
                },
          ),
          if (tag case final tag?)
            Positioned(left: 10, bottom: 10, child: MpFeedTag(tag)),
        ],
      ),
    );
    return GestureDetector(
      onTap: onTap,
      child: height == null
          ? AspectRatio(aspectRatio: MpStill.aspectRatio, child: box)
          : box,
    );
  }
}

class EvidenceNetworkImage extends StatelessWidget {
  const EvidenceNetworkImage(this.url, {super.key, required this.fallback});

  final String url;
  final Widget fallback;

  @override
  Widget build(BuildContext context) => Image.network(
    url,
    fit: BoxFit.cover,
    width: double.infinity,
    height: double.infinity,
    gaplessPlayback: true,
    excludeFromSemantics: true,
    frameBuilder: (context, child, frame, _) =>
        frame == null ? fallback : child,
    errorBuilder: (context, error, stack) => fallback,
  );
}

class AlertDuotoneSecondaryButton extends StatefulWidget {
  const AlertDuotoneSecondaryButton({
    super.key,
    required this.label,
    required this.icon,
    required this.onPressed,
  });

  final String label;
  final String icon;
  final VoidCallback onPressed;

  @override
  State<AlertDuotoneSecondaryButton> createState() =>
      _AlertDuotoneSecondaryButtonState();
}

class _AlertDuotoneSecondaryButtonState
    extends State<AlertDuotoneSecondaryButton> {
  static const _edge = 4.0;
  static const _height = 52.0;
  static const _radius = BorderRadius.all(Radius.circular(14));

  bool _down = false;

  void _setDown(bool value) {
    if (_down != value) setState(() => _down = value);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final face = EdgeInsets.only(
      top: _down ? _edge : 0,
      bottom: _down ? 0 : _edge,
    );
    return Semantics(
      button: true,
      label: widget.label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: (_) => _setDown(true),
        onTapUp: (_) => _setDown(false),
        onTapCancel: () => _setDown(false),
        onTap: widget.onPressed,
        child: SizedBox(
          height: _height,
          child: Stack(
            children: [
              Positioned.fill(
                top: _edge,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: c.buttonEdgeSecondary,
                    borderRadius: _radius,
                  ),
                ),
              ),
              Positioned.fill(
                top: face.top,
                bottom: face.bottom,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: c.buttonFaceSecondary,
                    borderRadius: _radius,
                  ),
                ),
              ),
              Positioned.fill(
                top: face.top,
                bottom: face.bottom,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  spacing: 8,
                  children: [
                    MpDuotoneIcon(
                      widget.icon,
                      outline: c.textPrimary,
                      accent: c.brandAccent,
                      size: 20,
                    ),
                    MpCeilWidth(
                      child: Text(
                        widget.label,
                        maxLines: 1,
                        style: context.mpText.label.copyWith(
                          fontSize: 16,
                          color: c.textPrimary,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
