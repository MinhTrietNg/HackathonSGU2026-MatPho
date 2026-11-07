import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../theme/theme.dart';

enum MpEyeLook { idle, left, right, blink, down, closed }

class MpEye extends StatefulWidget {
  const MpEye({super.key, this.look = MpEyeLook.idle, this.idleLoop = true});

  final MpEyeLook look;
  final bool idleLoop;

  static const size = Size(120, 64);

  static const idleLoopSteps = [
    (MpEyeLook.idle, Duration(milliseconds: 300), Duration(milliseconds: 2400)),
    (MpEyeLook.left, Duration(milliseconds: 300), Duration(milliseconds: 700)),
    (MpEyeLook.right, Duration(milliseconds: 450), Duration(milliseconds: 700)),
    (MpEyeLook.idle, Duration(milliseconds: 300), Duration(milliseconds: 500)),
    (MpEyeLook.blink, Duration(milliseconds: 90), Duration.zero),
  ];

  @visibleForTesting
  static MpEyePose debugPoseOf(Element element) =>
      ((element as StatefulElement).state as _MpEyeState)._pose;

  @override
  State<MpEye> createState() => _MpEyeState();
}

class _MpEyeState extends State<MpEye> with SingleTickerProviderStateMixin {
  static const _move = Duration(milliseconds: 300);

  late final AnimationController _ctrl = AnimationController(
    vsync: this,
    duration: _move,
    value: 1,
  )..addStatusListener(_onStatus);
  late MpEyePose _from = MpEyePose.of(widget.look);
  late MpEyePose _to = _from;

  Timer? _hold;

  int _step = 0;
  bool? _reduceMotion;

  MpEyePose get _pose =>
      MpEyePose.lerp(_from, _to, Curves.easeInOut.transform(_ctrl.value));

  bool get _looping =>
      widget.idleLoop &&
      widget.look == MpEyeLook.idle &&
      _reduceMotion == false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final reduce = MediaQuery.disableAnimationsOf(context);
    if (reduce == _reduceMotion) return;
    _reduceMotion = reduce;
    _hold?.cancel();
    _hold = null;
    if (reduce) {
      _from = _to = MpEyePose.of(widget.look);
      _ctrl.value = 1;
    } else {
      _step = 0;
      if (!_ctrl.isAnimating) _onStatus(AnimationStatus.completed);
    }
  }

  @override
  void didUpdateWidget(MpEye old) {
    super.didUpdateWidget(old);
    if (old.look == widget.look && old.idleLoop == widget.idleLoop) return;
    _hold?.cancel();
    _hold = null;
    _step = 0;
    final target = MpEyePose.of(widget.look);
    if (_reduceMotion!) {
      _from = _to = target;
      _ctrl.value = 1;
      return;
    }
    _goTo(target, _move);
  }

  @override
  void dispose() {
    _hold?.cancel();
    _ctrl.dispose();
    super.dispose();
  }

  void _goTo(MpEyePose pose, Duration duration) {
    _from = _pose;
    _to = pose;
    _ctrl.duration = duration;
    _ctrl.forward(from: 0);
  }

  void _onStatus(AnimationStatus status) {
    if (status != AnimationStatus.completed || !_looping) return;
    _hold?.cancel();
    final (_, _, hold) = MpEye.idleLoopSteps[_step];
    if (hold == Duration.zero) {
      _next();
    } else {
      _hold = Timer(hold, _next);
    }
  }

  void _next() {
    _hold = null;
    if (!mounted || !_looping) return;
    _step = (_step + 1) % MpEye.idleLoopSteps.length;
    final (look, move, _) = MpEye.idleLoopSteps[_step];
    _goTo(MpEyePose.of(look), move);
  }

  @override
  Widget build(BuildContext context) {
    final gold = context.mpColors.brandGold;
    return ExcludeSemantics(
      child: AnimatedBuilder(
        animation: _ctrl,
        builder: (context, _) => CustomPaint(
          size: MpEye.size,
          painter: _EyePainter(pose: _pose, gold: gold),
        ),
      ),
    );
  }
}

@immutable
class MpEyePose {
  const MpEyePose({
    this.dx = 0,
    this.dy = 0,
    this.pupilDy = 0,
    this.open = 1,
    this.iris = 1,
    this.lashes = 0,
  });

  final double dx, dy;

  final double pupilDy;

  final double open;

  final double iris, lashes;

  static MpEyePose of(MpEyeLook look) => switch (look) {
    MpEyeLook.idle => const MpEyePose(),
    MpEyeLook.left => const MpEyePose(dx: -20),
    MpEyeLook.right => const MpEyePose(dx: 20),
    MpEyeLook.blink => const MpEyePose(open: 0, iris: 0),
    MpEyeLook.down => const MpEyePose(dy: 9, pupilDy: 3),
    MpEyeLook.closed => const MpEyePose(open: 0, iris: 0, lashes: 1),
  };

  @override
  bool operator ==(Object other) =>
      other is MpEyePose &&
      other.dx == dx &&
      other.dy == dy &&
      other.pupilDy == pupilDy &&
      other.open == open &&
      other.iris == iris &&
      other.lashes == lashes;

  @override
  int get hashCode => Object.hash(dx, dy, pupilDy, open, iris, lashes);

  @override
  String toString() =>
      'MpEyePose(dx: $dx, dy: $dy, pupilDy: $pupilDy, open: $open, '
      'iris: $iris, lashes: $lashes)';

  static MpEyePose lerp(MpEyePose a, MpEyePose b, double t) => MpEyePose(
    dx: ui.lerpDouble(a.dx, b.dx, t)!,
    dy: ui.lerpDouble(a.dy, b.dy, t)!,
    pupilDy: ui.lerpDouble(a.pupilDy, b.pupilDy, t)!,
    open: ui.lerpDouble(a.open, b.open, t)!,
    iris: ui.lerpDouble(a.iris, b.iris, t)!,
    lashes: ui.lerpDouble(a.lashes, b.lashes, t)!,
  );
}

class _EyePainter extends CustomPainter {
  const _EyePainter({required this.pose, required this.gold});

  final MpEyePose pose;
  final Color gold;

  static const _stroke = 5.5;
  static const _lashStroke = 3.5;

  Path _lid(double open) {
    double y(double shut, double wide) => ui.lerpDouble(shut, wide, open)!;
    final side = y(32, 31.75);
    final top = y(30, -1.25);
    final bottom = y(34, 64.75);
    return Path()
      ..moveTo(8, side)
      ..cubicTo(30, top, 90, top, 112, side)
      ..cubicTo(90, bottom, 30, bottom, 8, side)
      ..close();
  }

  @override
  void paint(Canvas canvas, Size size) {
    canvas.scale(
      size.width / MpEye.size.width,
      size.height / MpEye.size.height,
    );
    final lid = _lid(pose.open);
    final stroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = _stroke
      ..color = gold;

    if (pose.iris > 0) {
      canvas
        ..save()
        ..clipPath(lid);
      final ring = Offset(60.5 + pose.dx, 32.5 + pose.dy);
      final pupil = ring.translate(0, pose.pupilDy);
      canvas
        ..saveLayer(
          null,
          Paint()..color = Colors.black.withValues(alpha: pose.iris),
        )
        ..drawCircle(ring, 20.5, stroke)
        ..drawCircle(
          pupil,
          10.5,
          Paint()
            ..shader = ui.Gradient.linear(
              pupil.translate(-7.5, -7.5),
              pupil.translate(7.5, 7.5),
              const [MpBrandColors.pupilLight, MpBrandColors.pupilDeep],
            ),
        )
        ..drawCircle(
          pupil.translate(-4.9, -4.9),
          3.6,
          Paint()..color = MpBrandColors.glint,
        )
        ..restore()
        ..restore();
    }

    canvas.drawPath(lid, stroke);

    if (pose.lashes > 0) {
      final lash = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = _lashStroke
        ..color = gold.withValues(alpha: gold.a * pose.lashes);
      final drop = 4 * (1 - pose.open);
      for (final (from, to) in const [
        (Offset(30, 30), Offset(26, 39)),
        (Offset(60, 30), Offset(60, 40)),
        (Offset(90, 30), Offset(94, 39)),
      ]) {
        canvas.drawLine(from.translate(0, drop), to.translate(0, drop), lash);
      }
    }
  }

  @override
  bool shouldRepaint(_EyePainter old) => old.pose != pose || old.gold != gold;
}
