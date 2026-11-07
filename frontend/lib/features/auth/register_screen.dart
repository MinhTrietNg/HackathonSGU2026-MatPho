library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_text_field.dart';
import '../../data/errors.dart';
import '../../data/models/user.dart';
import 'auth_routes.dart';
import 'auth_widgets.dart';
import 'register_controller.dart';

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({
    super.key,
    this.initialFullName,
    this.initialPhone,
    this.initialPassword,
    this.initialAgreed = false,
  });

  final String? initialFullName;
  final String? initialPhone;
  final String? initialPassword;
  final bool initialAgreed;

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  late final _name = TextEditingController(text: widget.initialFullName);
  late final _phone = TextEditingController(text: widget.initialPhone);
  late final _password = TextEditingController(text: widget.initialPassword);
  final _phoneFocus = FocusNode();
  final _passwordFocus = FocusNode();
  late bool _agreed = widget.initialAgreed;

  String? _nameInvalid;
  String? _phoneInvalid;
  String? _passwordInvalid;

  @override
  void initState() {
    super.initState();
    _phoneFocus.addListener(_onPhoneFocus);
  }

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _password.dispose();
    _phoneFocus.dispose();
    _passwordFocus.dispose();
    super.dispose();
  }

  void _onPhoneFocus() {
    if (_phoneFocus.hasFocus || !isValidVnPhone(_phone.text)) return;
    ref.read(registerControllerProvider.notifier).checkPhone(_phone.text);
  }

  void _submit() {
    FocusScope.of(context).unfocus();
    setState(() {
      _nameInvalid = _name.text.trim().isEmpty ? 'Nhập họ và tên' : null;
      _phoneInvalid = isValidVnPhone(_phone.text)
          ? null
          : 'Số điện thoại cần đủ 10 số';
      _passwordInvalid = _password.text.length >= minPasswordLength
          ? null
          : 'Mật khẩu cần ít nhất 8 ký tự';
    });
    if (_nameInvalid != null ||
        _phoneInvalid != null ||
        _passwordInvalid != null) {
      return;
    }
    ref
        .read(registerControllerProvider.notifier)
        .submit(
          fullName: _name.text.trim(),
          phone: _phone.text,
          password: _password.text,
        );
  }

  void _back() =>
      context.canPop() ? context.pop() : context.go(AppRoutes.login);

  @override
  Widget build(BuildContext context) {
    ref.listen(registerControllerProvider.select((s) => s.submit), (_, next) {
      if (next case AsyncData(value: final challenge?)) {
        ref.read(registerControllerProvider.notifier).challengeShown();
        context.push(AuthRoutes.otp, extra: challenge);
      }
    });
    final state = ref.watch(registerControllerProvider);
    final submitError = state.submit.error;
    final phoneTaken =
        submitError is PhoneAlreadyRegisteredException ||
        state.phoneCheck.error is PhoneAlreadyRegisteredException;

    return MpPage(
      header: AuthLargeBackHeader(title: 'Tạo tài khoản', onBack: _back),
      headerBottom: 14,
      gap: 14,
      children: [
        Text(
          'Chỉ cần số điện thoại.',
          style: context.mpText.body.copyWith(
            fontWeight: FontWeight.w500,
            color: context.mpColors.textSecondary,
          ),
        ),
        ?authFailureBanner(submitError),
        MpTextField(
          label: 'Họ và tên',
          icon: MpIcons.user,
          controller: _name,
          errorText: _nameInvalid,
          keyboardType: TextInputType.name,
          textInputAction: TextInputAction.next,
          autofillHints: const [AutofillHints.name],
          onSubmitted: (_) => _phoneFocus.requestFocus(),
        ),
        MpTextField(
          label: 'Số điện thoại',
          icon: MpIcons.phone,
          controller: _phone,
          focusNode: _phoneFocus,
          errorText:
              _phoneInvalid ?? (phoneTaken ? 'Số này đã có tài khoản' : null),
          keyboardType: TextInputType.phone,
          textInputAction: TextInputAction.next,
          inputFormatters: [
            FilteringTextInputFormatter.allow(RegExp('[0-9 ]')),
          ],
          autofillHints: const [AutofillHints.telephoneNumber],
          onChanged: (_) {
            ref.read(registerControllerProvider.notifier).phoneChanged();
            if (_phoneInvalid != null) setState(() => _phoneInvalid = null);
          },
          onSubmitted: (_) => _passwordFocus.requestFocus(),
        ),
        MpTextField(
          label: 'Mật khẩu',
          icon: MpIcons.lock,
          controller: _password,
          focusNode: _passwordFocus,
          errorText: _passwordInvalid,
          obscure: true,
          textInputAction: TextInputAction.done,
          autofillHints: const [AutofillHints.newPassword],
          onSubmitted: (_) => _agreed ? _submit() : null,
        ),
        AuthCheckbox(
          checked: _agreed,
          label: 'Tôi đồng ý với Điều khoản & Chính sách quyền riêng tư',
          onChanged: (value) => setState(() => _agreed = value),
        ),
        const Spacer(),
        MpButton(
          label: 'Gửi mã OTP',
          icon: MpIcons.sms,
          onPressed: _agreed && !state.submit.isLoading && !phoneTaken
              ? _submit
              : null,
        ),
        AuthFooterLink(
          prompt: 'Đã có tài khoản?',
          action: 'Đăng nhập',
          onTap: _back,
        ),
      ],
    );
  }
}
