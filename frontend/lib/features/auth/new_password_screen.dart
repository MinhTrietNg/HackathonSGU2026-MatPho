library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_text_field.dart';
import '../../core/widgets/mp_toast.dart';
import '../../data/models/user.dart';
import 'auth_session.dart';
import 'auth_widgets.dart';
import 'password_reset_controllers.dart';

class NewPasswordScreen extends ConsumerStatefulWidget {
  const NewPasswordScreen({
    super.key,
    required this.resetToken,
    this.initialPassword,
    this.initialConfirmation,
    this.previewFocused = false,
  });

  final String resetToken;
  final String? initialPassword;
  final String? initialConfirmation;

  final bool previewFocused;

  @override
  ConsumerState<NewPasswordScreen> createState() => _NewPasswordScreenState();
}

class _NewPasswordScreenState extends ConsumerState<NewPasswordScreen> {
  late final _password = TextEditingController(text: widget.initialPassword);
  late final _confirmation = TextEditingController(
    text: widget.initialConfirmation,
  );
  final _confirmationFocus = FocusNode();

  @override
  void dispose() {
    _password.dispose();
    _confirmation.dispose();
    _confirmationFocus.dispose();
    super.dispose();
  }

  void _submit() {
    FocusScope.of(context).unfocus();
    ref
        .read(newPasswordControllerProvider.notifier)
        .submit(resetToken: widget.resetToken, newPassword: _password.text);
  }

  void _back() =>
      context.canPop() ? context.pop() : context.go(AppRoutes.login);

  @override
  Widget build(BuildContext context) {
    ref.listen(newPasswordControllerProvider, (_, next) {
      if (next case AsyncData(value: true)) {
        final signedIn = ref.read(authSessionProvider) is SignedIn;
        showMpToast(
          context,
          MpToast(
            icon: MpDuotoneIcon(
              MpIcons.check,
              outline: context.mpColors.statusOk,
              accent: context.mpColors.statusOk,
              size: 18,
            ),
            title: 'Đã đổi mật khẩu. Máy khác đã đăng xuất.',
          ),
          duration: const Duration(seconds: 4),
          bottom: signedIn ? MpToast.defaultBottom : 121,
        );
        context.go(signedIn ? AppRoutes.settings : AppRoutes.login);
      }
    });
    final request = ref.watch(newPasswordControllerProvider);
    final checks = checkNewPassword(_password.text, _confirmation.text);

    return MpPage(
      header: MpHeader.back(title: 'Đặt mật khẩu mới', onBack: _back),
      headerBottom: 14,
      gap: 14,
      children: [
        ?authFailureBanner(request.error),
        MpTextField(
          label: 'Mật khẩu mới',
          icon: MpIcons.key,
          controller: _password,
          obscure: true,
          textInputAction: TextInputAction.next,
          autofillHints: const [AutofillHints.newPassword],
          onChanged: (_) => setState(() {}),
          onSubmitted: (_) => _confirmationFocus.requestFocus(),
          state: widget.previewFocused ? MpFieldState.focused : null,
        ),
        MpTextField(
          label: 'Nhập lại mật khẩu',
          icon: MpIcons.key,
          controller: _confirmation,
          focusNode: _confirmationFocus,
          obscure: true,
          revealToggle: false,
          textInputAction: TextInputAction.done,
          autofillHints: const [AutofillHints.newPassword],
          onChanged: (_) => setState(() {}),
          onSubmitted: (_) => checks.allMet ? _submit() : null,
        ),
        _Checklist(checks),
        const Spacer(),
        MpButton(
          label: 'Đặt lại mật khẩu',
          onPressed: checks.allMet && !request.isLoading ? _submit : null,
        ),
      ],
    );
  }
}

class _Checklist extends StatelessWidget {
  const _Checklist(this.checks);

  final PasswordChecks checks;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    Widget row(bool met, String rule) => Semantics(
      checked: met,
      label: rule,
      excludeSemantics: true,
      child: Row(
        spacing: 10,
        children: [
          Container(
            width: 20,
            height: 20,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: met ? c.statusOkSoft : c.bgRaised,
              shape: BoxShape.circle,
            ),
            child: MpDuotoneIcon(
              met ? MpIcons.check : MpIcons.close,
              outline: met ? c.statusOk : c.textMuted,
              accent: met ? c.statusOk : c.textMuted,
              size: 14,
            ),
          ),
          Expanded(
            child: Text(
              rule,
              style: t.body.copyWith(
                fontWeight: FontWeight.w500,
                color: met ? c.textPrimary : c.textSecondary,
              ),
            ),
          ),
        ],
      ),
    );

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: c.bgSurface,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        spacing: 10,
        children: [
          row(checks.minLength, 'Ít nhất 8 ký tự'),
          row(checks.lettersAndDigits, 'Có cả chữ và số'),
          row(checks.match, 'Hai mật khẩu khớp nhau'),
        ],
      ),
    );
  }
}
