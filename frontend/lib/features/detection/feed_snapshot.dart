library;

import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:video_player/video_player.dart';

const feedThumbnailWidth = 320.0;

// The feed on screen to capture. Not a GlobalKey: during a layout switch two
// feeds are briefly mounted; the newest one wins.
final class FeedSnapshotTarget {
  RenderRepaintBoundary? boundary;
}

class FeedSnapshotBoundary extends SingleChildRenderObjectWidget {
  const FeedSnapshotBoundary({super.key, required this.target, super.child});

  final FeedSnapshotTarget target;

  @override
  RenderRepaintBoundary createRenderObject(BuildContext context) =>
      _RenderFeedSnapshotBoundary(target);
}

class _RenderFeedSnapshotBoundary extends RenderRepaintBoundary {
  _RenderFeedSnapshotBoundary(this.target);

  final FeedSnapshotTarget target;

  @override
  void attach(PipelineOwner owner) {
    super.attach(owner);
    target.boundary = this;
  }

  @override
  void detach() {
    if (target.boundary == this) target.boundary = null;
    super.detach();
  }
}

// Playback has moved past the start: the texture holds a decoded frame, not
// the black buffer shown while the stream connects.
bool feedShowsFrame(VideoPlayerValue value) =>
    value.isInitialized &&
    !value.hasError &&
    !value.size.isEmpty &&
    value.position > Duration.zero;

const _litLuma = 32;
const _minLitShare = 0.02;

// Near-black: at most 2% of the sampled pixels are brighter than a dim gray.
// A platform texture that can't be read back captures as all black.
bool isNearBlack(ByteData rgba, {int step = 7}) {
  final pixels = rgba.lengthInBytes ~/ 4;
  var sampled = 0;
  var lit = 0;
  for (var i = 0; i < pixels; i += step) {
    final o = i * 4;
    final luma =
        (299 * rgba.getUint8(o) +
            587 * rgba.getUint8(o + 1) +
            114 * rgba.getUint8(o + 2)) ~/
        1000;
    sampled++;
    if (luma > _litLuma) lit++;
  }
  return lit <= sampled * _minLitShare;
}

// ≈320×180 PNG of what [boundary] shows, or null for a near-black frame.
Future<Uint8List?> snapshotFeed(RenderRepaintBoundary boundary) async {
  if (boundary.size.isEmpty) return null;
  final image = await boundary.toImage(
    pixelRatio: feedThumbnailWidth / boundary.size.width,
  );
  try {
    final rgba = await image.toByteData();
    if (rgba == null || isNearBlack(rgba)) return null;
    final png = await image.toByteData(format: ui.ImageByteFormat.png);
    return png?.buffer.asUint8List(png.offsetInBytes, png.lengthInBytes);
  } finally {
    image.dispose();
  }
}
