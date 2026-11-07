import 'package:flutter/widgets.dart';

class MpStill extends StatelessWidget {
  MpStill(String asset, {super.key, this.size})
    : image = AssetImage(asset),
      fallback = null;

  // [fallback] stands in while [image] loads and if it fails (a network URL).
  const MpStill.image(this.image, {super.key, this.size, this.fallback});

  static const aspectRatio = 16 / 9;

  final ImageProvider image;

  final Size? size;

  final Widget? fallback;

  @override
  Widget build(BuildContext context) {
    final fallback = this.fallback;
    return Image(
      image: image,
      width: size?.width,
      height: size?.height,
      fit: BoxFit.cover,
      gaplessPlayback: true,
      excludeFromSemantics: true,
      frameBuilder: fallback == null
          ? null
          : (context, child, frame, _) => frame == null ? fallback : child,
      errorBuilder: fallback == null
          ? null
          : (context, error, stack) => fallback,
    );
  }
}
