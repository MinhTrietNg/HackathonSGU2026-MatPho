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
import '../../data/errors.dart';
import '../../data/models/user.dart';
import '../auth/auth_routes.dart';
import '../auth/auth_widgets.dart';
import 'settings_state.dart';

class ChangePasswordScreen extends ConsumerStatefulWidget {
  const ChangePasswordScreen({
    super.key,
    this.initialCurrent,
    this.initialNew,
    this.initialConfirmation,
    this.previewFocused = false,
  });

  final String? initialCurrent;
  final String? initialNew;
  final String? initialConfirmation;

  final bool previewFocused;

  @override
  ConsumerState<ChangePasswordScreen> createState() =>
      _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends ConsumerState<ChangePasswordScreen> {
  late final _current = TextEditingController(text: widget.initialCurrent);
  late final _new = TextEditingController(text: widget.initialNew);
  late final _confirmation = TextEditingController(
    text: widget.initialConfirmation,
  );
  final _newFocus = FocusNode();
  final _confirmationFocus = FocusNode();

  @override
  void dispose() {
    _current.dispose();
    _new.dispose();
    _confirmation.dispose();
    _newFocus.dispose();
    _confirmationFocus.dispose();
    super.dispose();
  }

  bool get _valid =>
      _current.text.isNotEmpty &&
      checkNewPassword(_new.text, _confirmation.text).allMet;

  void _submit() {
    FocusScope.of(context).unfocus();
    ref
        .read(changePasswordProvider.notifier)
        .submit(currentPassword: _current.text, newPassword: _new.text);
  }

  void _edited(String _) {
    ref.read(changePasswordProvider.notifier).reset();
    setState(() {});
  }

  void _back() =>
      context.canPop() ? context.pop() : context.go(AppRoutes.settings);

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    ref.listen(changePasswordProvider, (_, next) {
      if (next case AsyncData(value: true)) {
        showMpToast(
          context,
          MpToast(
            icon: MpDuotoneIcon(
              MpIcons.check,
              outline: c.statusOk,
              accent: c.statusOk,
              size: 18,
            ),
            title: 'Đã đổi mật khẩu.',
          ),
          duration: const Duration(seconds: 4),
        );
        _back();
      }
    });
    final request = ref.watch(changePasswordProvider);
    final error = request.error;

    return MpPage(
      header: MpHeader.back(title: 'Đổi mật khẩu', onBack: _back),
      headerBottom: 14,
      gap: 14,
      children: [
        ?authFailureBanner(error),
        MpTextField(
          label: 'Mật khẩu hiện tại',
          icon: MpIcons.lock,
          controller: _current,
          obscure: true,
          revealToggle: false,
          errorText: error is WrongPasswordException ? 'Sai mật khẩu' : null,
          textInputAction: TextInputAction.next,
          autofillHints: const [AutofillHints.password],
          onChanged: _edited,
          onSubmitted: (_) => _newFocus.requestFocus(),
        ),
        MpTextField(
          label: 'Mật khẩu mới',
          icon: MpIcons.key,
          controller: _new,
          focusNode: _newFocus,
          obscure: true,
          textInputAction: TextInputAction.next,
          autofillHints: const [AutofillHints.newPassword],
          onChanged: _edited,
          onSubmitted: (_) => _confirmationFocus.requestFocus(),
          state: widget.previewFocused ? MpFieldState.focused : null,
        ),
        MpTextField(
          label: 'Nhập lại mật khẩu mới',
          icon: MpIcons.key,
          controller: _confirmation,
          focusNode: _confirmationFocus,
          obscure: true,
          revealToggle: false,
          textInputAction: TextInputAction.done,
          autofillHints: const [AutofillHints.newPassword],
          onChanged: _edited,
          onSubmitted: (_) => _valid ? _submit() : null,
        ),
        Align(
          alignment: Alignment.centerRight,
          child: Semantics(
            button: true,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => context.push(AuthRoutes.forgotPassword),
              child: Text(
                'Quên mật khẩu?',
                style: context.mpText.label.copyWith(color: c.brandAccentFg),
              ),
            ),
          ),
        ),
        const Spacer(),
        MpButton(
          label: 'Lưu',
          onPressed: _valid && !request.isLoading ? _submit : null,
        ),
      ],
    );
  }
}
