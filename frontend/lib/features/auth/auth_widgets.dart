import 'package:flutter/material.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_banner.dart';
import '../../core/widgets/mp_ceil_width.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_icon_button.dart';
import '../../data/errors.dart';

class AuthLargeBackHeader extends StatelessWidget {
  const AuthLargeBackHeader({
    super.key,
    required this.title,
    required this.onBack,
  });

  final String title;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        spacing: 10,
        children: [
          MpIconButton(
            icon: MpIcons.back,
            semanticLabel: 'Quay lại',
            onPressed: onBack,
          ),
          Expanded(
            child: Semantics(
              header: true,
              child: Text(
                title,
                style: context.mpText.title.copyWith(
                  fontWeight: FontWeight.w800,
                  color: c.textPrimary,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class AuthHeadline extends StatelessWidget {
  const AuthHeadline({
    super.key,
    required this.title,
    this.subtitle,
    this.gap = 6,
  });

  final String title;
  final String? subtitle;
  final double gap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      spacing: gap,
      children: [
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
        if (subtitle case final subtitle?)
          Text(
            subtitle,
            textAlign: TextAlign.center,
            style: t.body.copyWith(
              fontWeight: FontWeight.w500,
              color: c.textSecondary,
            ),
          ),
      ],
    );
  }
}

class AuthFooterLink extends StatelessWidget {
  const AuthFooterLink({
    super.key,
    required this.prompt,
    required this.action,
    required this.onTap,
  });

  final String prompt;
  final String action;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final style = context.mpText.body.copyWith(fontWeight: FontWeight.w500);
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      spacing: 4,
      children: [
        MpCeilWidth(
          child: Text(prompt, style: style.copyWith(color: c.textSecondary)),
        ),
        Semantics(
          link: true,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onTap,
            child: MpCeilWidth(
              child: Text(
                action,
                style: style.copyWith(
                  fontWeight: FontWeight.w700,
                  color: c.brandAccentFg,
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class AuthCheckbox extends StatelessWidget {
  const AuthCheckbox({
    super.key,
    required this.checked,
    required this.label,
    required this.onChanged,
  });

  final bool checked;
  final String label;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Semantics(
      checked: checked,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => onChanged(!checked),
        child: Row(
          spacing: 10,
          children: [
            Container(
              width: 22,
              height: 22,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: checked ? c.brandAccent : c.bgCard,
                borderRadius: BorderRadius.circular(6),
                border: checked
                    ? null
                    : Border.all(color: c.lineStrong, width: 1.5),
              ),
              child: checked
                  ? MpDuotoneIcon(
                      MpIcons.check,
                      outline: c.brandOnAccent,
                      accent: c.brandOnAccent,
                      size: 16,
                    )
                  : null,
            ),
            Expanded(
              child: Text(
                label,
                style: context.mpText.caption.copyWith(
                  fontWeight: FontWeight.w500,
                  color: c.textSecondary,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

Widget? authFailureBanner(Object? error) => switch (error) {
  NetworkException() => const MpBanner(
    tone: MpBannerTone.warn,
    icon: MpIcons.wifiOff,
    title: 'Không có mạng',
    body: 'Kiểm tra kết nối rồi thử lại.',
  ),
  ServerException() => const MpBanner(
    tone: MpBannerTone.warn,
    icon: MpIcons.alert,
    title: 'Máy chủ đang bận',
    body: 'Thử lại sau ít phút.',
  ),
  _ => null,
};
