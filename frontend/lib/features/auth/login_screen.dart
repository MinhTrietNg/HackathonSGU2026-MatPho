library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/widgets/mp_banner.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_login_form.dart';
import '../../core/widgets/mp_page.dart';
import '../../data/errors.dart';
import '../../data/models/user.dart';
import 'auth_routes.dart';
import 'auth_widgets.dart';
import 'login_controller.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({
    super.key,
    this.initialPhone,
    this.initialPassword,
    this.idleLoop = true,
  });

  final String? initialPhone;
  final String? initialPassword;

  final bool idleLoop;

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  late final _phone = TextEditingController(text: widget.initialPhone);
  late final _password = TextEditingController(text: widget.initialPassword);

  String? _phoneInvalid;
  String? _passwordInvalid;

  @override
  void dispose() {
    _phone.dispose();
    _password.dispose();
    super.dispose();
  }

  void _submit() {
    FocusScope.of(context).unfocus();
    final phone = _phone.text;
    final password = _password.text;
    setState(() {
      _phoneInvalid = isValidVnPhone(phone)
          ? null
          : 'Số điện thoại cần đủ 10 số';
      _passwordInvalid = password.length >= minPasswordLength
          ? null
          : 'Mật khẩu cần ít nhất 8 ký tự';
    });
    if (_phoneInvalid != null || _passwordInvalid != null) return;
    ref
        .read(loginControllerProvider.notifier)
        .submit(phone: phone, password: password);
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(loginControllerProvider, (_, next) {
      switch (next) {
        case AsyncData(value: LoginNext.notificationPermission):
          context.go(AuthRoutes.notificationPermission);
        case AsyncData(value: LoginNext.monitor):
          context.go(AppRoutes.monitor);
        default:
      }
    });
    final login = ref.watch(loginControllerProvider);
    final error = login.error;

    return MpPage(
      children: [
        MpLoginForm(
          phoneController: _phone,
          passwordController: _password,
          idleLoop: widget.idleLoop,
          phoneError: _phoneInvalid,
          passwordError:
              _passwordInvalid ??
              (error is WrongPasswordException ? 'Mật khẩu không đúng' : null),
          banner: _banner(error),
          onForgotPassword: () => context.push(AuthRoutes.forgotPassword),
          onSubmitted: _submit,
        ),
        const Spacer(),
        MpButton(
          label: 'Đăng nhập',
          onPressed: login.isLoading ? null : _submit,
        ),
        AuthFooterLink(
          prompt: 'Chưa có tài khoản?',
          action: 'Đăng ký',
          onTap: () => context.push(AuthRoutes.register),
        ),
      ],
    );
  }

  Widget? _banner(Object? error) => switch (error) {
    WrongPasswordException(:final attemptsLeft) => MpBanner(
      tone: MpBannerTone.fire,
      icon: MpIcons.alert,
      title: 'Sai mật khẩu',
      body: attemptsLeft == null
          ? 'Sai tiếp sẽ khoá 15 phút.'
          : 'Còn $attemptsLeft lần thử. Sai tiếp sẽ khoá 15 phút.',
      outlined: false,
    ),
    AccountLockedException(:final until) => MpBanner(
      tone: MpBannerTone.fire,
      icon: MpIcons.lock,
      title: 'Tạm khoá đăng nhập',
      body:
          'Sai 5 lần. Thử lại lúc ${_clock(until)} '
          'hoặc chọn "Quên mật khẩu?".',
      outlined: false,
    ),
    _ => authFailureBanner(error),
  };

  static String _clock(DateTime t) =>
      '${t.hour.toString().padLeft(2, '0')}:'
      '${t.minute.toString().padLeft(2, '0')}';
}
