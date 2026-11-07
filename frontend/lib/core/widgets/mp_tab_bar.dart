import 'package:flutter/material.dart';

import '../theme/theme.dart';
import 'mp_duotone_icon.dart';

class MpTabBar extends StatelessWidget {
  const MpTabBar({super.key, required this.currentIndex, required this.onTap});

  final int currentIndex;
  final ValueChanged<int> onTap;

  static const height = 76.0;

  static const _tabs = [
    (label: 'Theo dõi', icon: MpIcons.eye),
    (label: 'Lịch sử', icon: MpIcons.history),
    (label: 'Cài đặt', icon: MpIcons.settings),
  ];
  static const _pill = Size(56, 32);
  static const _duration = Duration(milliseconds: 320);
  static const _curve = Curves.easeOutExpo;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final activeLabel = t.label.copyWith(color: c.brandAccentFg);
    final idleLabel = t.caption.copyWith(
      fontWeight: FontWeight.w500,
      color: c.textMuted,
    );

    final bottomInset = MediaQuery.paddingOf(context).bottom;
    return Container(
      height: height + bottomInset,
      padding: EdgeInsets.only(top: 10, bottom: bottomInset),
      decoration: BoxDecoration(
        color: c.bgSurface,
        border: Border(top: BorderSide(color: c.lineSubtle)),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final tabWidth = constraints.maxWidth / _tabs.length;
          return Stack(
            children: [
              AnimatedPositioned(
                duration: _duration,
                curve: _curve,
                left: tabWidth * currentIndex + (tabWidth - _pill.width) / 2,
                top: 0,
                width: _pill.width,
                height: _pill.height,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: c.brandAccentSoft,
                    borderRadius: BorderRadius.circular(_pill.height / 2),
                  ),
                ),
              ),
              Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (var i = 0; i < _tabs.length; i++)
                    Expanded(
                      child: _Tab(
                        label: _tabs[i].label,
                        icon: _tabs[i].icon,
                        active: i == currentIndex,
                        iconStroke: i == currentIndex
                            ? c.textPrimary
                            : c.textMuted,
                        iconFill: i == currentIndex
                            ? c.brandAccentFg
                            : c.textMuted,
                        labelStyle: i == currentIndex ? activeLabel : idleLabel,
                        onTap: () => onTap(i),
                      ),
                    ),
                ],
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Tab extends StatelessWidget {
  const _Tab({
    required this.label,
    required this.icon,
    required this.active,
    required this.iconStroke,
    required this.iconFill,
    required this.labelStyle,
    required this.onTap,
  });

  final String label;
  final String icon;
  final bool active;
  final Color iconStroke;
  final Color iconFill;
  final TextStyle labelStyle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: active,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Column(
          children: [
            SizedBox.fromSize(
              size: MpTabBar._pill,
              child: Center(
                child: MpDuotoneIcon(
                  icon,
                  outline: iconStroke,
                  accent: iconFill,
                ),
              ),
            ),
            const SizedBox(height: 4),
            AnimatedDefaultTextStyle(
              duration: MpTabBar._duration,
              curve: MpTabBar._curve,
              style: labelStyle,
              child: Text(label, maxLines: 1, softWrap: false),
            ),
          ],
        ),
      ),
    );
  }
}
