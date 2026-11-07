import 'package:flutter/material.dart';

import '../theme/mp_overlay_colors.dart';
import '../theme/theme.dart';
import 'mp_button.dart';

class MpDialog extends StatelessWidget {
  const MpDialog({
    super.key,
    this.illustration,
    required this.title,
    this.body,
    this.actions = const [],
  });

  final Widget? illustration;
  final String title;
  final String? body;
  final List<Widget> actions;

  static const illustrationSize = Size(200, 200 * 180 / 280);

  static const width = 318.0;

  static const enterDuration = Duration(milliseconds: 200);

  static const exitDuration = Duration(milliseconds: 150);

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return Semantics(
      scopesRoute: true,
      namesRoute: true,
      explicitChildNodes: true,
      label: title,
      child: Container(
        constraints: const BoxConstraints(maxWidth: width),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: c.bgSurface,
          borderRadius: BorderRadius.circular(24),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: 12,
          children: [
            if (illustration case final illustration?)
              Center(child: illustration),
            Semantics(
              header: true,
              child: Text(
                title,
                textAlign: TextAlign.center,
                style: t.title.copyWith(
                  fontWeight: FontWeight.w800,
                  color: c.textPrimary,
                ),
              ),
            ),
            if (body case final body?)
              Text(
                body,
                textAlign: TextAlign.center,
                style: t.body.copyWith(
                  fontWeight: FontWeight.w500,
                  color: c.textSecondary,
                ),
              ),
            ...actions,
          ],
        ),
      ),
    );
  }
}

class MpConfirmDialog extends StatelessWidget {
  const MpConfirmDialog({
    super.key,
    required this.illustration,
    required this.title,
    required this.body,
    required this.confirmLabel,
    this.confirmKind = MpButtonKind.danger,
    required this.cancelLabel,
  });

  final Widget illustration;
  final String title;
  final String body;
  final String confirmLabel;
  final MpButtonKind confirmKind;
  final String cancelLabel;

  @override
  Widget build(BuildContext context) {
    return MpDialog(
      illustration: illustration,
      title: title,
      body: body,
      actions: [
        MpButton(
          label: confirmLabel,
          kind: confirmKind,
          onPressed: () => Navigator.of(context).pop(true),
        ),
        MpButton(
          label: cancelLabel,
          kind: MpButtonKind.ghost,
          size: MpButtonSize.m,
          onPressed: () => Navigator.of(context).pop(false),
        ),
      ],
    );
  }
}

Future<bool> showMpConfirm(BuildContext context, MpConfirmDialog dialog) async {
  final result = await showMpDialog<bool>(context, builder: (_) => dialog);
  return result ?? false;
}

Future<T?> showMpDialog<T>(
  BuildContext context, {
  required WidgetBuilder builder,
}) {
  final navigator = Navigator.of(context, rootNavigator: true);
  return navigator.push(
    _MpDialogRoute<T>(
      builder: builder,
      capturedThemes: InheritedTheme.capture(
        from: context,
        to: navigator.context,
      ),
      barrierLabel: MaterialLocalizations.of(context).modalBarrierDismissLabel,
    ),
  );
}

class _MpDialogRoute<T> extends PopupRoute<T> {
  _MpDialogRoute({
    required this.builder,
    required this.capturedThemes,
    required this.barrierLabel,
  });

  final WidgetBuilder builder;
  final CapturedThemes capturedThemes;

  @override
  final String barrierLabel;

  @override
  Color get barrierColor =>
      MpOverlayColors.scrim.withValues(alpha: MpOverlayColors.scrimOpacity);

  @override
  bool get barrierDismissible => true;

  @override
  Curve get barrierCurve => Curves.easeOut;

  @override
  Duration get transitionDuration => MpDialog.enterDuration;

  @override
  Duration get reverseTransitionDuration => MpDialog.exitDuration;

  @override
  Widget buildPage(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
  ) {
    return capturedThemes.wrap(
      Material(
        type: MaterialType.transparency,
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
            child: Builder(builder: builder),
          ),
        ),
      ),
    );
  }

  @override
  Widget buildTransitions(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    return FadeTransition(
      opacity: animation.drive(CurveTween(curve: Curves.easeOut)),
      child: child,
    );
  }
}
