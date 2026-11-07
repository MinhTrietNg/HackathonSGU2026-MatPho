import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/theme.dart';
import 'mp_illustration.dart';

bool mpIllustrationMotionEnabled = true;

enum MpEase {
  linear(Curves.linear),
  easeOut(Curves.easeOut),
  easeInOut(Curves.easeInOut),

  popIn(Cubic(0.45, 1.45, 0.8, 1)),

  stepEnd(Threshold(1));

  const MpEase(this.curve);

  final Curve curve;
}

@immutable
class MpKeyframe {
  const MpKeyframe(this.at, this.value, [this.ease = MpEase.linear]);

  final double at;
  final double value;
  final MpEase ease;
}

@immutable
class MpTrack {
  const MpTrack(this.keys) : _constant = null;

  const MpTrack.constant(double value) : keys = const [], _constant = value;

  final List<MpKeyframe> keys;
  final double? _constant;

  double valueAt(double t) {
    if (_constant case final c?) return c;
    if (t <= keys.first.at) return keys.first.value;
    for (var i = 0; i < keys.length - 1; i++) {
      final a = keys[i];
      final b = keys[i + 1];
      if (t < b.at) {
        final local = (t - a.at) / (b.at - a.at);
        return ui.lerpDouble(a.value, b.value, a.ease.curve.transform(local))!;
      }
    }
    return keys.last.value;
  }
}

@immutable
class MpLayerMotion {
  const MpLayerMotion({
    this.opacity,
    this.scaleX,
    this.scaleY,
    this.translateX,
    this.translateY,
    this.rotate,
    this.trim,
  });

  final MpTrack? opacity, scaleX, scaleY, translateX, translateY;

  final MpTrack? rotate;

  final MpTrack? trim;
}

enum MpReveal { ltr, rtl, ttb, btt }

sealed class MpArtNode {
  const MpArtNode();
}

class MpArtPart extends MpArtNode {
  const MpArtPart(this.asset);

  final String asset;
}

class MpArtLayer extends MpArtNode {
  const MpArtLayer(
    this.name, {
    this.box,
    this.opacity = 1,
    this.reveal,
    this.opening = const MpLayerMotion(),
    this.loop = const MpLayerMotion(),
    required this.children,
  });

  final String name;

  final Rect? box;

  final double opacity;

  final MpReveal? reveal;

  final MpLayerMotion opening, loop;
  final List<MpArtNode> children;
}

enum MpMotionPhase { opening, loop }

@immutable
class MpIllustrationMotion {
  const MpIllustrationMotion({
    required this.asset,
    required this.duration,
    required this.parts,
    this.themed = true,
  });

  final String asset;
  final Duration duration;
  final List<MpArtNode> parts;

  final bool themed;

  (MpMotionPhase, double) phaseAt(Duration elapsed) {
    final t = elapsed.inMicroseconds / duration.inMicroseconds;
    if (t < 1) return (MpMotionPhase.opening, t);
    return (MpMotionPhase.loop, t - t.floorToDouble());
  }
}

@immutable
class MpLayerPose {
  const MpLayerPose({
    this.opacity = 1,
    this.scaleX = 1,
    this.scaleY = 1,
    this.translateX = 0,
    this.translateY = 0,
    this.rotate = 0,
    this.trim = 1,
  });

  factory MpLayerPose.of(MpArtLayer layer, MpMotionPhase phase, double t) {
    final m = phase == MpMotionPhase.opening ? layer.opening : layer.loop;
    double v(MpTrack? track, double rest) => track?.valueAt(t) ?? rest;
    return MpLayerPose(
      opacity: v(m.opacity, layer.opacity).clamp(0, 1),
      scaleX: v(m.scaleX, 1),
      scaleY: v(m.scaleY, 1),
      translateX: v(m.translateX, 0),
      translateY: v(m.translateY, 0),
      rotate: v(m.rotate, 0),
      trim: v(m.trim, 1).clamp(0, 1),
    );
  }

  final double opacity, scaleX, scaleY, translateX, translateY, rotate, trim;

  Matrix4 transform(Offset origin) => Matrix4.identity()
    ..translateByDouble(origin.dx + translateX, origin.dy + translateY, 0, 1)
    ..scaleByDouble(scaleX, scaleY, 1, 1)
    ..rotateZ(rotate)
    ..translateByDouble(-origin.dx, -origin.dy, 0, 1);
}

class MpAnimatedIllustration extends StatefulWidget {
  const MpAnimatedIllustration({
    super.key,
    required this.motion,
    required this.size,
    required this.still,
    this.backdrop = true,
  });

  final MpIllustrationMotion motion;
  final Size size;
  final Widget still;

  final bool backdrop;

  @override
  State<MpAnimatedIllustration> createState() => _MpAnimatedIllustrationState();
}

class _MpAnimatedIllustrationState extends State<MpAnimatedIllustration>
    with SingleTickerProviderStateMixin {
  late final Ticker _ticker = createTicker(_tick);
  final _elapsed = ValueNotifier(Duration.zero);

  void _tick(Duration elapsed) => _elapsed.value = elapsed;

  bool get _playing =>
      mpIllustrationMotionEnabled && !MediaQuery.disableAnimationsOf(context);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_playing) {
      if (!_ticker.isActive) _ticker.start();
    } else if (_ticker.isActive) {
      _ticker.stop();
      _elapsed.value = Duration.zero;
    }
  }

  @override
  void didUpdateWidget(MpAnimatedIllustration old) {
    super.didUpdateWidget(old);
    if (old.motion != widget.motion && _ticker.isActive) {
      _ticker
        ..stop()
        ..start();
    }
  }

  @override
  void dispose() {
    _ticker.dispose();
    _elapsed.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_playing) return widget.still;
    final motion = widget.motion;
    final mapper = motion.themed
        ? MpIllustration.colorMapper(
            motion.asset,
            context.mpColors,
            backdrop: widget.backdrop,
          )
        : null;
    final artboard = MpIllustration.figmaSize;
    return SizedBox.fromSize(
      size: widget.size,
      child: FittedBox(
        child: SizedBox.fromSize(
          size: artboard,
          child: RepaintBoundary(
            child: ClipRect(
              child: _Nodes(
                nodes: motion.parts,
                motion: motion,
                elapsed: _elapsed,
                mapper: mapper,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Nodes extends StatelessWidget {
  const _Nodes({
    required this.nodes,
    required this.motion,
    required this.elapsed,
    required this.mapper,
  });

  final List<MpArtNode> nodes;
  final MpIllustrationMotion motion;
  final ValueListenable<Duration> elapsed;
  final ColorMapper? mapper;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        for (final node in nodes)
          switch (node) {
            MpArtPart(:final asset) => SvgPicture.asset(
              asset,
              width: MpIllustration.figmaSize.width,
              height: MpIllustration.figmaSize.height,
              excludeFromSemantics: true,
              clipBehavior: Clip.none,
              colorMapper: mapper,
            ),
            MpArtLayer() => _Layer(
              layer: node,
              motion: motion,
              elapsed: elapsed,
              child: _Nodes(
                nodes: node.children,
                motion: motion,
                elapsed: elapsed,
                mapper: mapper,
              ),
            ),
          },
      ],
    );
  }
}

class _Layer extends StatelessWidget {
  const _Layer({
    required this.layer,
    required this.motion,
    required this.elapsed,
    required this.child,
  });

  final MpArtLayer layer;
  final MpIllustrationMotion motion;
  final ValueListenable<Duration> elapsed;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder(
      valueListenable: elapsed,
      child: child,
      builder: (context, elapsed, child) {
        final (phase, t) = motion.phaseAt(elapsed);
        final pose = MpLayerPose.of(layer, phase, t);
        Widget result = child!;
        if (layer.reveal case final reveal? when pose.trim < 1) {
          result = ClipRect(
            clipper: _RevealClipper(layer.box!, reveal, pose.trim),
            child: result,
          );
        }
        if (layer.box case final box?) {
          result = Transform(
            transform: pose.transform(box.center),
            child: result,
          );
        }
        return Opacity(opacity: pose.opacity, child: result);
      },
    );
  }
}

class _RevealClipper extends CustomClipper<Rect> {
  const _RevealClipper(this.box, this.reveal, this.fraction);

  final Rect box;
  final MpReveal reveal;
  final double fraction;

  @override
  Rect getClip(Size size) {
    final r = box.inflate(4);
    final w = r.width * fraction;
    final h = r.height * fraction;
    return switch (reveal) {
      MpReveal.ltr => Rect.fromLTWH(r.left, r.top, w, r.height),
      MpReveal.rtl => Rect.fromLTWH(r.right - w, r.top, w, r.height),
      MpReveal.ttb => Rect.fromLTWH(r.left, r.top, r.width, h),
      MpReveal.btt => Rect.fromLTWH(r.left, r.bottom - h, r.width, h),
    };
  }

  @override
  bool shouldReclip(_RevealClipper old) =>
      old.fraction != fraction || old.box != box || old.reveal != reveal;
}
