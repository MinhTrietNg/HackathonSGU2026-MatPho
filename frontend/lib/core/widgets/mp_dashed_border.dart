import 'dart:ui' show PathMetric;

import 'package:flutter/widgets.dart';

class MpDashedBorder extends StatelessWidget {
  const MpDashedBorder({
    super.key,
    required this.color,
    required this.radius,
    this.width = 1,
    required this.child,
  });

  final Color color;
  final double radius;
  final double width;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      foregroundPainter: _DashedRRectPainter(
        color: color,
        radius: radius,
        width: width,
      ),
      child: child,
    );
  }
}

class _DashedRRectPainter extends CustomPainter {
  const _DashedRRectPainter({
    required this.color,
    required this.radius,
    required this.width,
  });

  final Color color;
  final double radius;
  final double width;

  double get _dash => 4 * width;
  double get _gap => 8 / 3 * width;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = (Offset.zero & size).deflate(width / 2);
    final r = (radius - width / 2).clamp(0.0, rect.shortestSide / 2);
    final path = Path()
      ..addRRect(RRect.fromRectAndRadius(rect, Radius.circular(r)));
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = width;
    for (final PathMetric metric in path.computeMetrics()) {
      final count = (metric.length / (_dash + _gap)).round().clamp(1, 1 << 20);
      final period = metric.length / count;
      final dash = period * _dash / (_dash + _gap);
      for (var i = 0; i < count; i++) {
        final start = i * period;
        canvas.drawPath(metric.extractPath(start, start + dash), paint);
      }
    }
  }

  @override
  bool shouldRepaint(_DashedRRectPainter old) =>
      old.color != color || old.radius != radius || old.width != width;
}
