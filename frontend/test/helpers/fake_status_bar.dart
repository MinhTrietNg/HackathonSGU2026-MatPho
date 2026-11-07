import 'package:flutter/material.dart';
import 'package:mat_pho/core/theme/theme.dart';

class FakeStatusBar extends StatelessWidget {
  const FakeStatusBar({super.key});

  static const height = 40.0;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final right = t.mono.copyWith(
      fontWeight: FontWeight.w600,
      color: c.textSecondary,
    );
    const gap = SizedBox(width: 2 * 0.6 * 12);
    return SizedBox(
      height: height,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('21:47', style: t.label.copyWith(color: c.textPrimary)),
            Row(
              children: [
                Text('4G', style: right),
                gap,
                for (var i = 0; i < 3; i++)
                  SizedBox(
                    width: 12,
                    height: 12 * 1.4,
                    child: Stack(
                      children: [
                        Positioned(
                          left: 4,
                          top: 4.4,
                          width: 3.5,
                          height: 12,
                          child: ColoredBox(color: c.textSecondary),
                        ),
                      ],
                    ),
                  ),
                gap,
                Text('82%', style: right),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
