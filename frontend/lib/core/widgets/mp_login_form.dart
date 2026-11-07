import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/theme.dart';
import 'mp_ceil_width.dart';
import 'mp_duotone_icon.dart';
import 'mp_eye.dart';
import 'mp_text_field.dart';

enum MpLoginFocus { none, phone, password }

class MpLoginForm extends StatefulWidget {
  const MpLoginForm({
    super.key,
    this.phoneController,
    this.passwordController,
    this.phoneError,
    this.passwordError,
    this.banner,
    this.onForgotPassword,
    this.onSubmitted,
    this.focus,
    this.idleLoop = true,
  });

  final TextEditingController? phoneController;
  final TextEditingController? passwordController;
  final String? phoneError;
  final String? passwordError;
  final Widget? banner;
  final VoidCallback? onForgotPassword;

  final VoidCallback? onSubmitted;

  final MpLoginFocus? focus;
  final bool idleLoop;

  @override
  State<MpLoginForm> createState() => _MpLoginFormState();
}

class _MpLoginFormState extends State<MpLoginForm> {
  final _phoneFocus = FocusNode();
  final _passwordFocus = FocusNode();

  @override
  void initState() {
    super.initState();
    _phoneFocus.addListener(_onFocus);
    _passwordFocus.addListener(_onFocus);
  }

  @override
  void dispose() {
    _phoneFocus.dispose();
    _passwordFocus.dispose();
    super.dispose();
  }

  void _onFocus() => setState(() {});

  MpFieldState? _state(MpLoginFocus field, String? error) {
    if (widget.focus == null) return null;
    if (error != null) return MpFieldState.error;
    return widget.focus == field ? MpFieldState.focused : MpFieldState.idle;
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final focus =
        widget.focus ??
        (_phoneFocus.hasFocus
            ? MpLoginFocus.phone
            : _passwordFocus.hasFocus
            ? MpLoginFocus.password
            : MpLoginFocus.none);
    final look = switch (focus) {
      MpLoginFocus.none => MpEyeLook.idle,
      MpLoginFocus.phone => MpEyeLook.down,
      MpLoginFocus.password => MpEyeLook.closed,
    };

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      spacing: 16,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 16),
          child: Column(
            spacing: 14,
            children: [
              MpEye(look: look, idleLoop: widget.idleLoop),
              Text(
                'MẮT PHỐ',
                textAlign: TextAlign.center,
                style: t.display.copyWith(
                  fontSize: 32,
                  fontWeight: FontWeight.w800,
                  height: 1.3,
                  letterSpacing: 1.28,
                  color: c.textPrimary,
                ),
              ),
            ],
          ),
        ),
        ?widget.banner,
        MpTextField(
          label: 'Số điện thoại',
          icon: MpIcons.phone,
          controller: widget.phoneController,
          focusNode: _phoneFocus,
          errorText: widget.phoneError,
          keyboardType: TextInputType.phone,
          textInputAction: TextInputAction.next,
          inputFormatters: [
            FilteringTextInputFormatter.allow(RegExp('[0-9 ]')),
          ],
          autofillHints: const [AutofillHints.telephoneNumber],
          onSubmitted: (_) => _passwordFocus.requestFocus(),
          state: _state(MpLoginFocus.phone, widget.phoneError),
        ),
        MpTextField(
          label: 'Mật khẩu',
          icon: MpIcons.lock,
          controller: widget.passwordController,
          focusNode: _passwordFocus,
          errorText: widget.passwordError,
          obscure: true,
          textInputAction: TextInputAction.done,
          autofillHints: const [AutofillHints.password],
          onSubmitted: (_) => widget.onSubmitted?.call(),
          state: _state(MpLoginFocus.password, widget.passwordError),
        ),
        Align(
          alignment: Alignment.centerRight,
          child: Semantics(
            link: true,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: widget.onForgotPassword,
              child: MpCeilWidth(
                child: Text(
                  'Quên mật khẩu?',
                  style: t.label.copyWith(color: c.brandAccentFg),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
