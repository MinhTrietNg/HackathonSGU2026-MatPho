import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/theme/theme.dart';
import '../../data/models/fire_event.dart';
import '../alert/alert_widgets.dart' show EvidenceNetworkImage;

class EvidenceSlideshow extends StatefulWidget {
  const EvidenceSlideshow({
    super.key,
    required this.snapshots,
    this.sign,
    this.confidence,
  });

  final List<EvidenceSnapshot> snapshots;

  final DetectedSign? sign;
  final double? confidence;

  static const frameDuration = Duration(milliseconds: 600);

  @override
  State<EvidenceSlideshow> createState() => _EvidenceSlideshowState();
}

class _EvidenceSlideshowState extends State<EvidenceSlideshow> {
  Timer? _timer;
  var _index = 0;

  @override
  void initState() {
    super.initState();
    _restart();
  }

  @override
  void didUpdateWidget(EvidenceSlideshow oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.snapshots.length != widget.snapshots.length) _restart();
  }

  void _restart() {
    _timer?.cancel();
    _timer = null;
    _index = 0;
    if (widget.snapshots.length < 2) return;
    _timer = Timer.periodic(EvidenceSlideshow.frameDuration, (_) {
      if (mounted) {
        setState(() => _index = (_index + 1) % widget.snapshots.length);
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.snapshots.isEmpty) return const SizedBox.expand();
    final snapshot = widget.snapshots[_index];
    return Stack(
      fit: StackFit.expand,
      children: [
        EvidenceNetworkImage(snapshot.url, fallback: const SizedBox.expand()),
        if (snapshot.box case final box?)
          EvidenceBoxOverlay(
            box: box,
            sign: widget.sign,
            confidence: widget.confidence,
          ),
      ],
    );
  }
}

class EvidenceBoxOverlay extends StatelessWidget {
  const EvidenceBoxOverlay({
    super.key,
    required this.box,
    this.sign,
    this.confidence,
  });

  final EvidenceBox box;
  final DetectedSign? sign;
  final double? confidence;

  static const rectKey = ValueKey('evidence-box');

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final color = sign == DetectedSign.smoke ? c.statusWarn : c.statusFire;
    final label = _label();
    return LayoutBuilder(
      builder: (context, constraints) {
        final w = constraints.maxWidth;
        final h = constraints.maxHeight;
        final rect = Rect.fromLTRB(
          box.left * w,
          box.top * h,
          box.right * w,
          box.bottom * h,
        );
        return Stack(
          children: [
            Positioned.fromRect(
              rect: rect,
              child: IgnorePointer(
                child: DecoratedBox(
                  key: rectKey,
                  decoration: BoxDecoration(
                    border: Border.all(color: color, width: 2),
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ),
            ),
            if (label != null)
              Positioned(
                left: rect.left,
                top: rect.top >= 18 ? rect.top - 18 : rect.top,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 5),
                  height: 18,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: color,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    label,
                    style: context.mpText.mono.copyWith(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: c.onStatusFromLight,
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }

  String? _label() {
    final sign = this.sign;
    if (sign == null) return null;
    final name = sign == DetectedSign.fire ? 'CHÁY' : 'KHÓI?';
    final confidence = this.confidence;
    if (confidence == null) return name;
    return '$name · ${confidence.toStringAsFixed(2).replaceAll('.', ',')}';
  }
}
