library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/mp_mock_os_colors.dart';
import '../../core/theme/theme.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_fill_scroll_view.dart';
import 'alert_actions.dart';
import 'alert_routes.dart';

class DialerScreen extends StatelessWidget {
  const DialerScreen({super.key, required this.eventId});

  final String eventId;

  static const _keys = [
    ('1', null),
    ('2', 'ABC'),
    ('3', 'DEF'),
    ('4', 'GHI'),
    ('5', 'JKL'),
    ('6', 'MNO'),
    ('7', 'PQRS'),
    ('8', 'TUV'),
    ('9', 'WXYZ'),
    ('*', null),
    ('0', '+'),
    ('#', null),
  ];

  static const _key = 76.0;
  static const _gap = 22.0;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final natural = t.body.copyWith(height: kTextHeightNone);
    return Scaffold(
      body: SafeArea(
        child: MpFillScrollView(
          child: Column(
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: Padding(
                  padding: const EdgeInsets.only(left: 15, top: 3),
                  child: _BackLink(
                    onTap: () => popOrGo(context, AppRoutes.alert(eventId)),
                  ),
                ),
              ),
              const SizedBox(height: 78),
              SizedBox(
                height: 60,
                child: Text(
                  '114',
                  style: natural.copyWith(
                    fontSize: 44,
                    fontWeight: FontWeight.w500,
                    color: c.textPrimary,
                  ),
                ),
              ),
              const SizedBox(height: 4),
              SizedBox(
                height: 20,
                child: Text(
                  'Cứu hỏa · Cứu nạn cứu hộ',
                  style: natural.copyWith(
                    fontWeight: FontWeight.w500,
                    color: c.textSecondary,
                  ),
                ),
              ),
              const SizedBox(height: 28),
              ClipRect(
                child: SizedBox(
                  width: 3 * _key + 2 * _gap,
                  height: 368,
                  child: Wrap(
                    spacing: _gap,
                    runSpacing: _gap,
                    clipBehavior: Clip.hardEdge,
                    children: [
                      for (final (digit, letters) in _keys)
                        _Key(digit: digit, letters: letters),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 20),
              Semantics(
                button: true,
                label: 'Gọi 114',
                excludeSemantics: true,
                child: GestureDetector(
                  onTap: () =>
                      context.pushReplacement(AlertPaths.call(eventId)),
                  child: Container(
                    width: _key,
                    height: _key,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: MpMockOsColors.dialerCall,
                      shape: BoxShape.circle,
                    ),
                    child: MpDuotoneIcon(
                      MpIcons.call,
                      outline: c.onStatusFromLight,
                      accent: c.onStatusFromLight,
                      size: 32,
                    ),
                  ),
                ),
              ),
              const Spacer(),
            ],
          ),
        ),
      ),
    );
  }
}

class _BackLink extends StatelessWidget {
  const _BackLink({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Semantics(
      button: true,
      label: 'Quay lại Mắt Phố',
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.only(right: 8, top: 6, bottom: 6),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            spacing: 4,
            children: [
              MpDuotoneIcon(
                MpIcons.back,
                outline: c.textPrimary,
                accent: c.textPrimary,
                size: 14,
              ),
              Text(
                'Mắt Phố',
                style: context.mpText.body.copyWith(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  height: kTextHeightNone,
                  color: c.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Key extends StatelessWidget {
  const _Key({required this.digit, this.letters});

  final String digit;
  final String? letters;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return Container(
      width: DialerScreen._key,
      height: DialerScreen._key,
      decoration: BoxDecoration(color: c.bgRaised, shape: BoxShape.circle),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            digit,
            style: t.body.copyWith(
              fontSize: 30,
              height: 36 / 30,
              color: c.textPrimary,
            ),
          ),
          if (letters case final letters?)
            Text(
              letters,
              style: t.body.copyWith(
                fontSize: 10,
                fontWeight: FontWeight.w600,
                height: kTextHeightNone,
                letterSpacing: 1.2,
                color: c.textPrimary,
              ),
            ),
        ],
      ),
    );
  }
}
