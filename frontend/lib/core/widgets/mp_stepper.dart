import 'package:flutter/material.dart';

import '../theme/theme.dart';

class MpStepper extends StatelessWidget {
  const MpStepper({super.key, required this.current, this.count = 3})
    : assert(current >= 1 && current <= count);

  final int current;
  final int count;

  static const _circle = 28.0;
  static const _ring = 4.0;
  static const _line = Size(40, 2);

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final number = context.mpText.label;
    return Semantics(
      label: 'Bước $current trên $count',
      excludeSemantics: true,
      child: Padding(
        padding: const EdgeInsets.all(_ring),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          spacing: 6,
          children: [
            for (var step = 1; step <= count; step++) ...[
              if (step > 1)
                Container(
                  width: _line.width,
                  height: _line.height,
                  decoration: BoxDecoration(
                    color: step <= current ? c.brandAccent : c.bgRaised,
                    borderRadius: BorderRadius.circular(1),
                  ),
                ),
              Container(
                width: _circle,
                height: _circle,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: step <= current ? c.brandAccent : c.bgRaised,
                  shape: BoxShape.circle,
                  border: step == current
                      ? Border.all(
                          color: c.brandAccentSoft,
                          width: _ring,
                          strokeAlign: BorderSide.strokeAlignOutside,
                        )
                      : null,
                ),
                child: Text(
                  '$step',
                  style: number.copyWith(
                    color: step <= current ? c.brandOnAccent : c.textSecondary,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
