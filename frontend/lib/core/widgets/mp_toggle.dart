import 'package:flutter/material.dart';

import '../theme/theme.dart';

class MpToggle extends StatelessWidget {
  const MpToggle({
    super.key,
    required this.value,
    required this.onChanged,
    this.semanticLabel,
  });

  final bool value;

  final ValueChanged<bool>? onChanged;

  final String? semanticLabel;

  static const size = Size(44, 26);
  static const _knob = 20.0;
  static const _duration = Duration(milliseconds: 200);
  static const _curve = Curves.easeOut;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Semantics(
      toggled: value,
      enabled: onChanged != null,
      label: semanticLabel,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onChanged == null ? null : () => onChanged!(!value),
        child: AnimatedContainer(
          duration: _duration,
          curve: _curve,
          width: size.width,
          height: size.height,
          padding: const EdgeInsets.all(3),
          decoration: BoxDecoration(
            color: value ? c.brandAccent : c.bgRaised,
            borderRadius: BorderRadius.circular(size.height / 2),
          ),
          child: AnimatedAlign(
            duration: _duration,
            curve: _curve,
            alignment: value ? Alignment.centerRight : Alignment.centerLeft,
            child: AnimatedContainer(
              duration: _duration,
              curve: _curve,
              width: _knob,
              height: _knob,
              decoration: BoxDecoration(
                color: value ? c.brandOnAccent : c.textMuted,
                shape: BoxShape.circle,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
