import 'package:flutter/material.dart';

import '../theme/mp_overlay_colors.dart';
import '../theme/theme.dart';

class MpSheet extends StatelessWidget {
  const MpSheet({
    super.key,
    this.title,
    this.subtitle,
    required this.children,
    this.spacing = 14,
  });

  final String? title;
  final String? subtitle;
  final List<Widget> children;
  final double spacing;

  static const enterDuration = Duration(milliseconds: 280);

  static const exitDuration = Duration(milliseconds: 220);

  static const _radius = Radius.circular(28);

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final bottom =
        MediaQuery.paddingOf(context).bottom +
        MediaQuery.viewInsetsOf(context).bottom;
    return Container(
      padding: EdgeInsets.fromLTRB(20, 10, 20, 24 + bottom),
      decoration: BoxDecoration(
        color: c.bgSurface,
        borderRadius: const BorderRadius.only(
          topLeft: _radius,
          topRight: _radius,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        spacing: spacing,
        children: [
          Container(
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: c.lineStrong,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Flexible(
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                spacing: spacing,
                children: [
                  if (title case final title?)
                    Semantics(
                      header: true,
                      child: Text(
                        title,
                        style: t.title.copyWith(
                          fontWeight: FontWeight.w800,
                          color: c.textPrimary,
                        ),
                      ),
                    ),
                  if (subtitle case final subtitle?)
                    Text(
                      subtitle,
                      style: t.body.copyWith(
                        fontWeight: FontWeight.w500,
                        color: c.textSecondary,
                      ),
                    ),
                  ...children,
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

Future<T?> showMpSheet<T>(
  BuildContext context, {
  required WidgetBuilder builder,
}) {
  final navigator = Navigator.of(context, rootNavigator: true);
  final l10n = MaterialLocalizations.of(context);
  return navigator.push(
    _MpSheetRoute<T>(
      builder: builder,
      capturedThemes: InheritedTheme.capture(
        from: context,
        to: navigator.context,
      ),
      barrierLabel: l10n.scrimLabel,
      barrierOnTapHint: l10n.scrimOnTapHint(l10n.bottomSheetLabel),
    ),
  );
}

class _MpSheetRoute<T> extends ModalBottomSheetRoute<T> {
  _MpSheetRoute({
    required super.builder,
    super.capturedThemes,
    super.barrierLabel,
    super.barrierOnTapHint,
  }) : super(
         isScrollControlled: true,
         backgroundColor: Colors.transparent,
         elevation: 0,
         modalBarrierColor: MpOverlayColors.scrim.withValues(
           alpha: MpOverlayColors.scrimOpacity,
         ),
         sheetAnimationStyle: const AnimationStyle(
           duration: MpSheet.enterDuration,
           reverseDuration: MpSheet.exitDuration,
           curve: Curves.easeOut,
           reverseCurve: Curves.easeOut,
         ),
       );

  @override
  Curve get barrierCurve => Curves.easeOut;
}
