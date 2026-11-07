library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/widgets/mp_animated_illustrations.dart';
import '../../core/widgets/mp_banner.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_ceil_width.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_page.dart';
import '../../data/errors.dart';
import '../../data/models/user.dart';
import '../../data/providers.dart';
import 'auth_routes.dart';
import 'auth_session.dart';
import 'auth_widgets.dart';
import 'otp_controller.dart';
import 'permission_controller.dart';

class OtpScreen extends ConsumerStatefulWidget {
  const OtpScreen({super.key, required this.challenge, this.initialCode = ''});

  final OtpChallenge challenge;

  final String initialCode;

  @override
  ConsumerState<OtpScreen> createState() => _OtpScreenState();
}

class _OtpScreenState extends ConsumerState<OtpScreen> {
  late final _code = TextEditingController(text: widget.initialCode);
  final _focus = FocusNode();
  late final Timer _ticker;
  DateTime _now = DateTime(0);

  bool _editedSinceError = false;

  @override
  void initState() {
    super.initState();
    _now = ref.read(clockProvider)();
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
    _focus.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _ticker.cancel();
    _code.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _tick() {
    final now = ref.read(clockProvider)();
    if (now.difference(_now).inSeconds != 0) setState(() => _now = now);
  }

  OtpController get _controller =>
      ref.read(otpControllerProvider(widget.challenge).notifier);

  void _onChanged(String code) {
    setState(() => _editedSinceError = true);
    if (code.length == otpLength) _verify(code);
  }

  void _verify(String code) {
    setState(() => _editedSinceError = false);
    _controller.verify(code);
  }

  void _confirm() {
    if (_code.text.length == otpLength) {
      _verify(_code.text);
    } else {
      _focus.requestFocus();
    }
  }

  void _back() =>
      context.canPop() ? context.pop() : context.go(AppRoutes.login);

  void _onState(OtpState? previous, OtpState next) {
    if (previous != null && previous.challenge != next.challenge) {
      _code.clear();
      _editedSinceError = false;
      _focus.requestFocus();
    }
    switch (next.verify) {
      case AsyncData(value: RegistrationCompleted()):
        continueAfterRegistration(context, ref);
      case AsyncData(value: PasswordResetAuthorized(:final resetToken)):
        context.pushReplacement(AuthRoutes.newPassword, extra: resetToken);
      default:
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = otpControllerProvider(widget.challenge);
    ref.listen(provider, _onState);
    final state = ref.watch(provider);
    final error = state.verify.error;
    final rejected = switch (error) {
      OtpWrongException() ||
      OtpExpiredException() ||
      OtpLockedException() => true,
      _ => false,
    };
    final lockedUntil = error is OtpLockedException ? error.retryAt : null;
    final locked = lockedUntil != null && _now.isBefore(lockedUntil);
    final resendIn = state.challenge.resendAvailableAt.difference(_now);
    final canResend =
        !locked &&
        !state.resend.isLoading &&
        (error is OtpExpiredException || resendIn <= Duration.zero);
    final banner =
        authFailureBanner(state.resend.error) ?? authFailureBanner(error);

    final boxes = _OtpBoxes(
      controller: _code,
      focusNode: _focus,
      autofocus: !rejected,
      enabled: !locked && !state.verify.isLoading,
      error: rejected && !_editedSinceError,
      onChanged: _onChanged,
    );

    return MpPage(
      header: MpHeader.back(title: 'Nhập mã xác nhận', onBack: _back),
      children: rejected
          ? [
              const MpBanner(
                tone: MpBannerTone.warn,
                icon: MpIcons.alert,
                title: 'Mã sai hoặc hết hạn',
                body: 'Xem lại tin nhắn mới nhất.',
              ),
              ?banner,
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: AuthHeadline(title: 'Nhập mã 6 số'),
              ),
              boxes,
              _ErrorLine(switch (error) {
                OtpWrongException(:final attemptsLeft) =>
                  'Còn $attemptsLeft lần thử',
                OtpLockedException() when locked =>
                  'Sai 3 lần. Thử lại sau '
                      '${formatCountdown(lockedUntil.difference(_now))}',
                OtpLockedException() => 'Nhập lại mã',
                _ => 'Mã đã hết hạn',
              }),
              const Spacer(),
              MpButton(
                label: canResend || locked
                    ? 'Gửi lại mã'
                    : 'Gửi lại mã sau ${formatCountdown(resendIn)}',
                icon: MpIcons.sms,
                kind: MpButtonKind.secondary,
                onPressed: canResend ? _controller.resend : null,
              ),
            ]
          : [
              ?banner,
              Center(
                child: MpOtpIllustration(size: Size(220, 220 * 180 / 280)),
              ),
              AuthHeadline(
                title: 'Nhập mã 6 số',
                subtitle: 'Mã đã gửi tới ${maskPhone(state.challenge.phone)}.',
              ),
              boxes,
              _ResendRow(
                remaining: canResend ? null : resendIn,
                onResend: _controller.resend,
              ),
              const Spacer(),
              MpButton(
                label: 'Xác nhận',
                onPressed: state.verify.isLoading ? null : _confirm,
              ),
            ],
    );
  }
}

class _OtpBoxes extends StatelessWidget {
  const _OtpBoxes({
    required this.controller,
    required this.focusNode,
    required this.autofocus,
    required this.enabled,
    required this.error,
    required this.onChanged,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool autofocus;
  final bool enabled;
  final bool error;
  final ValueChanged<String> onChanged;

  static const _box = Size(44, 54);

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final digit = context.mpText.title.copyWith(fontWeight: FontWeight.w800);
    final code = controller.text;
    final active = focusNode.hasFocus && !error
        ? code.length.clamp(0, otpLength - 1)
        : -1;

    return Center(
      child: Stack(
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            spacing: 8,
            children: [
              for (var i = 0; i < otpLength; i++)
                Container(
                  width: _box.width,
                  height: _box.height,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: c.bgCard,
                    borderRadius: BorderRadius.circular(12),
                    border: error
                        ? Border.all(color: c.statusFire, width: 1.5)
                        : i == active
                        ? Border.all(color: c.brandAccent, width: 1.5)
                        : Border.all(color: c.lineSubtle),
                  ),
                  child: i < code.length
                      ? Text(
                          code[i],
                          style: digit.copyWith(
                            color: error ? c.statusFire : c.textPrimary,
                          ),
                        )
                      : null,
                ),
            ],
          ),
          Positioned.fill(
            child: Semantics(
              label: 'Mã xác nhận 6 số',
              child: TextField(
                controller: controller,
                focusNode: focusNode,
                autofocus: autofocus,
                readOnly: !enabled,
                keyboardType: TextInputType.number,
                autofillHints: const [AutofillHints.oneTimeCode],
                inputFormatters: [
                  FilteringTextInputFormatter.digitsOnly,
                  LengthLimitingTextInputFormatter(otpLength),
                ],
                onChanged: onChanged,
                showCursor: false,
                enableInteractiveSelection: false,
                style: const TextStyle(color: Colors.transparent),
                decoration: const InputDecoration.collapsed(hintText: null),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ResendRow extends StatelessWidget {
  const _ResendRow({required this.remaining, required this.onResend});

  final Duration? remaining;
  final VoidCallback onResend;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final label = t.body.copyWith(fontWeight: FontWeight.w500);
    final remaining = this.remaining;
    if (remaining == null) {
      return Center(
        child: Semantics(
          button: true,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onResend,
            child: Text(
              'Gửi lại mã',
              style: label.copyWith(
                fontWeight: FontWeight.w700,
                color: c.brandAccentFg,
              ),
            ),
          ),
        ),
      );
    }
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: 4,
      children: [
        MpCeilWidth(
          child: Text(
            'Gửi lại mã sau',
            style: label.copyWith(color: c.textSecondary),
          ),
        ),
        MpCeilWidth(
          child: Text(
            formatCountdown(remaining),
            style: t.mono.copyWith(
              fontWeight: FontWeight.w600,
              color: c.brandAccentFg,
            ),
          ),
        ),
      ],
    );
  }
}

class _ErrorLine extends StatelessWidget {
  const _ErrorLine(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Semantics(
      liveRegion: true,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        spacing: 6,
        children: [
          MpDuotoneIcon(
            MpIcons.alert,
            outline: c.statusFire,
            accent: c.statusFire,
            size: 16,
          ),
          Text(
            message,
            style: context.mpText.caption.copyWith(
              fontWeight: FontWeight.w500,
              color: c.statusFire,
            ),
          ),
        ],
      ),
    );
  }
}
