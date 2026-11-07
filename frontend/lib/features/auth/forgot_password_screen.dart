library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_text_field.dart';
import '../../data/errors.dart';
import '../../data/models/user.dart';
import 'auth_routes.dart';
import 'auth_widgets.dart';
import 'password_reset_controllers.dart';

class ForgotPasswordScreen extends ConsumerStatefulWidget {
  const ForgotPasswordScreen({
    super.key,
    this.initialPhone,
    this.previewFocused = false,
  });

  final String? initialPhone;

  final bool previewFocused;

  @override
  ConsumerState<ForgotPasswordScreen> createState() =>
      _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends ConsumerState<ForgotPasswordScreen> {
  late final _phone = TextEditingController(text: widget.initialPhone);
  String? _phoneInvalid;

  @override
  void dispose() {
    _phone.dispose();
    super.dispose();
  }

  void _submit() {
    FocusScope.of(context).unfocus();
    final valid = isValidVnPhone(_phone.text);
    setState(() => _phoneInvalid = valid ? null : 'Số điện thoại cần đủ 10 số');
    if (!valid) return;
    ref.read(forgotPasswordControllerProvider.notifier).submit(_phone.text);
  }

  void _back() =>
      context.canPop() ? context.pop() : context.go(AppRoutes.login);

  @override
  Widget build(BuildContext context) {
    ref.listen(forgotPasswordControllerProvider, (_, next) {
      if (next case AsyncData(value: final challenge?)) {
        ref.read(forgotPasswordControllerProvider.notifier).reset();
        context.push(AuthRoutes.otp, extra: challenge);
      }
    });
    final request = ref.watch(forgotPasswordControllerProvider);
    final error = request.error;
    final phoneError =
        _phoneInvalid ??
        (error is PhoneNotRegisteredException ? 'Số này chưa đăng ký' : null);

    return MpPage(
      header: MpHeader.back(title: 'Quên mật khẩu', onBack: _back),
      children: [
        ?authFailureBanner(error),
        Center(
          child: MpIllustration(
            MpIllustrations.reset,
            size: Size(240, 240 * 180 / 280),
          ),
        ),
        const AuthHeadline(
          title: 'Lấy lại mật khẩu',
          subtitle: 'Nhập số điện thoại để nhận mã.',
        ),
        MpTextField(
          label: 'Số điện thoại',
          icon: MpIcons.phone,
          controller: _phone,
          errorText: phoneError,
          keyboardType: TextInputType.phone,
          textInputAction: TextInputAction.done,
          inputFormatters: [
            FilteringTextInputFormatter.allow(RegExp('[0-9 ]')),
          ],
          autofillHints: const [AutofillHints.telephoneNumber],
          onChanged: (_) {
            ref.read(forgotPasswordControllerProvider.notifier).reset();
            if (_phoneInvalid != null) setState(() => _phoneInvalid = null);
          },
          onSubmitted: (_) => _submit(),
          state: widget.previewFocused && phoneError == null
              ? MpFieldState.focused
              : null,
        ),
        const Spacer(),
        MpButton(
          label: 'Gửi mã OTP',
          icon: MpIcons.sms,
          onPressed: request.isLoading ? null : _submit,
        ),
      ],
    );
  }
}
