import 'package:flutter/material.dart';

import '../theme/theme.dart';
import 'mp_ceil_width.dart';
import 'mp_duotone_icon.dart';

enum MpButtonKind {
  primary,
  secondary,
  ghost,
  quiet,
  danger,
  amber,
  report,
  resolve,
}

enum MpButtonSize {
  m(46, 14, FontWeight.w700, 20),

  l(52, 16, FontWeight.w700, 20),

  xl(60, 22, FontWeight.w800, 24);

  const MpButtonSize(this.height, this.fontSize, this.fontWeight, this.icon);

  final double height;
  final double fontSize;
  final FontWeight fontWeight;
  final double icon;
}

class MpButton extends StatefulWidget {
  const MpButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.kind = MpButtonKind.primary,
    this.size = MpButtonSize.l,
    this.icon,
    this.expand = true,
    this.pressed,
    this.busy = false,
  });

  final String label;
  final VoidCallback? onPressed;
  final MpButtonKind kind;
  final MpButtonSize size;

  final String? icon;

  final bool expand;

  final bool? pressed;

  // Work in flight: no taps, a spinner in place of the label.
  final bool busy;

  @override
  State<MpButton> createState() => _MpButtonState();
}

class _MpButtonState extends State<MpButton> {
  static const _edge = 4.0;
  static const _radius = BorderRadius.all(Radius.circular(14));

  bool _down = false;

  bool get _enabled => widget.onPressed != null && !widget.busy;

  void _setDown(bool value) {
    if (_down != value && _enabled) setState(() => _down = value);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final style = _style(c);
    final pressed = widget.pressed ?? _down;
    final raised = style.edge != null;
    final size = widget.size;

    final fg = style.fg;
    final label = context.mpText.label.copyWith(
      fontSize: size.fontSize,
      fontWeight: size.fontWeight,
      color: fg,
    );
    Widget content = Row(
      mainAxisSize: widget.expand ? MainAxisSize.max : MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      spacing: 8,
      children: [
        if (widget.icon != null)
          MpDuotoneIcon(
            widget.icon!,
            outline: style.icon ?? fg,
            accent: style.icon ?? fg,
            size: size.icon,
          ),
        Flexible(
          child: MpCeilWidth(
            child: Text(
              widget.label,
              style: label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
      ],
    );
    if (!raised && pressed) content = Opacity(opacity: 0.6, child: content);
    if (widget.busy) {
      content = Stack(
        alignment: Alignment.center,
        children: [
          Visibility.maintain(visible: false, child: content),
          SizedBox.square(
            dimension: size.icon,
            child: CircularProgressIndicator(strokeWidth: 2.5, color: fg),
          ),
        ],
      );
    }

    final faceInset = raised
        ? EdgeInsets.only(top: pressed ? _edge : 0, bottom: pressed ? 0 : _edge)
        : EdgeInsets.zero;

    final button = SizedBox(
      height: size.height,
      child: Stack(
        children: [
          if (raised)
            Positioned.fill(
              top: _edge,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: style.edge,
                  borderRadius: _radius,
                ),
              ),
            ),
          Positioned.fill(
            top: faceInset.top,
            bottom: faceInset.bottom,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: style.face,
                borderRadius: _radius,
                border: style.line == null
                    ? null
                    : Border.all(color: style.line!),
              ),
            ),
          ),
          Padding(
            padding: faceInset.add(const EdgeInsets.symmetric(horizontal: 18)),
            child: Center(widthFactor: 1, child: content),
          ),
        ],
      ),
    );

    return Semantics(
      button: true,
      enabled: _enabled,
      label: widget.label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: (_) => _setDown(true),
        onTapUp: (_) => _setDown(false),
        onTapCancel: () => _setDown(false),
        onTap: _enabled ? widget.onPressed : null,
        child: Opacity(
          opacity: widget.onPressed != null ? 1 : 0.4,
          child: button,
        ),
      ),
    );
  }

  _ButtonStyle _style(MpColors c) => switch (widget.kind) {
    MpButtonKind.primary => _ButtonStyle(
      face: c.brandAccent,
      edge: c.buttonEdgePrimary,
      fg: c.brandOnAccent,
    ),
    MpButtonKind.secondary => _ButtonStyle(
      face: c.buttonFaceSecondary,
      edge: c.buttonEdgeSecondary,
      fg: c.textPrimary,
    ),
    MpButtonKind.ghost => _ButtonStyle(fg: c.brandAccentFg),
    MpButtonKind.quiet => _ButtonStyle(face: c.bgCard, fg: c.textPrimary),
    MpButtonKind.danger => _ButtonStyle(
      face: c.statusFire,
      edge: c.buttonEdgeDanger,
      fg: c.onStatusFromLight,
    ),
    MpButtonKind.amber => _ButtonStyle(
      face: c.statusWarn,
      edge: c.buttonEdgeAmber,
      fg: c.onStatusFromDark,
    ),
    MpButtonKind.report => _ButtonStyle(
      face: c.actionReportBg,
      edge: c.buttonEdgeReport,
      line: c.actionReportLine,
      fg: c.actionReportFg,
    ),
    MpButtonKind.resolve => _ButtonStyle(
      face: c.actionResolveBg,
      edge: c.buttonEdgeResolve,
      line: c.actionResolveLine,
      fg: c.actionResolveFg,
      icon: c.actionResolveIcon,
    ),
  };
}

class _ButtonStyle {
  const _ButtonStyle({
    required this.fg,
    this.face,
    this.edge,
    this.line,
    this.icon,
  });

  final Color fg;
  final Color? icon;
  final Color? face;
  final Color? edge;
  final Color? line;
}
