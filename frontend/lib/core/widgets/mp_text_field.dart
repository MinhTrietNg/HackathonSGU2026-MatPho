import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/theme.dart';
import 'mp_ceil_width.dart';
import 'mp_duotone_icon.dart';

enum MpFieldState { idle, focused, error }

class MpTextField extends StatefulWidget {
  const MpTextField({
    super.key,
    required this.label,
    required this.icon,
    this.controller,
    this.focusNode,
    this.hintText,
    this.errorText,
    this.obscure = false,
    this.revealToggle = true,
    this.keyboardType,
    this.textInputAction,
    this.inputFormatters,
    this.autofillHints,
    this.onChanged,
    this.onSubmitted,
    this.enabled = true,
    this.state,
  });

  final String label;

  final String icon;
  final TextEditingController? controller;
  final FocusNode? focusNode;

  final String? hintText;
  final String? errorText;

  final bool obscure;

  final bool revealToggle;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;
  final List<TextInputFormatter>? inputFormatters;
  final Iterable<String>? autofillHints;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;
  final bool enabled;

  final MpFieldState? state;

  @override
  State<MpTextField> createState() => _MpTextFieldState();
}

class _MpTextFieldState extends State<MpTextField> {
  FocusNode? _ownFocus;
  bool _revealed = false;

  FocusNode get _focus => widget.focusNode ?? (_ownFocus ??= FocusNode());

  @override
  void initState() {
    super.initState();
    _focus.addListener(_onFocus);
  }

  @override
  void didUpdateWidget(MpTextField old) {
    super.didUpdateWidget(old);
    if (old.focusNode != widget.focusNode) {
      (old.focusNode ?? _ownFocus)?.removeListener(_onFocus);
      _focus.addListener(_onFocus);
    }
  }

  @override
  void dispose() {
    _focus.removeListener(_onFocus);
    _ownFocus?.dispose();
    super.dispose();
  }

  void _onFocus() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final state =
        widget.state ??
        (widget.errorText != null
            ? MpFieldState.error
            : _focus.hasFocus
            ? MpFieldState.focused
            : MpFieldState.idle);
    final (border, borderWidth) = switch (state) {
      MpFieldState.idle => (c.lineSubtle, 1.0),
      MpFieldState.focused => (c.brandAccent, 1.5),
      MpFieldState.error => (c.statusFire, 1.5),
    };
    final value = t.body.copyWith(
      fontWeight: FontWeight.w500,
      color: c.textPrimary,
    );
    final action = t.label.copyWith(color: c.brandAccentFg);

    final box = Container(
      height: 52,
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: BoxDecoration(
        color: c.bgCard,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: border, width: borderWidth),
      ),
      child: Row(
        spacing: 10,
        children: [
          MpDuotoneIcon(
            widget.icon,
            outline: c.textMuted,
            accent: c.textMuted,
            size: 20,
          ),
          Expanded(
            child: Semantics(
              label: widget.label,
              child: TextField(
                controller: widget.controller,
                focusNode: _focus,
                enabled: widget.enabled,
                obscureText: widget.obscure && !_revealed,
                obscuringCharacter: '•',
                keyboardType: widget.keyboardType,
                textInputAction: widget.textInputAction,
                inputFormatters: widget.inputFormatters,
                autofillHints: widget.autofillHints,
                onChanged: widget.onChanged,
                onSubmitted: widget.onSubmitted,
                style: value,
                cursorColor: c.brandAccent,
                decoration: InputDecoration.collapsed(
                  hintText: widget.hintText,
                  hintStyle: value.copyWith(color: c.textMuted),
                ),
              ),
            ),
          ),
          if (widget.obscure && widget.revealToggle)
            Semantics(
              button: true,
              label: _revealed ? 'Ẩn mật khẩu' : 'Hiện mật khẩu',
              excludeSemantics: true,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => setState(() => _revealed = !_revealed),
                child: MpCeilWidth(
                  child: Text(_revealed ? 'Ẩn' : 'Hiện', style: action),
                ),
              ),
            ),
        ],
      ),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: 6,
      children: [
        Text(widget.label, style: t.label.copyWith(color: c.textSecondary)),
        box,
        if (widget.errorText != null)
          Semantics(
            liveRegion: true,
            child: Row(
              spacing: 6,
              children: [
                MpDuotoneIcon(
                  MpIcons.alert,
                  outline: c.statusFire,
                  accent: c.statusFire,
                  size: 16,
                ),
                Expanded(
                  child: Text(
                    widget.errorText!,
                    style: t.caption.copyWith(
                      fontWeight: FontWeight.w500,
                      color: c.statusFire,
                    ),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
