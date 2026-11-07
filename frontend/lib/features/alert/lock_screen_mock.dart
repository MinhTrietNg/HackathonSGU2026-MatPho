library;

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../core/theme/theme.dart';
import '../../core/time_format.dart';
import '../../core/widgets/mp_brand.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../data/models/fire_event.dart';
import 'alert_widgets.dart';

class LockScreenMock extends StatelessWidget {
  const LockScreenMock({
    super.key,
    required this.event,
    required this.now,
    this.onCall,
    this.onView,
  });

  final FireEvent event;
  final DateTime now;
  final VoidCallback? onCall;
  final VoidCallback? onView;

  static const _weekdays = [
    'Thứ Hai',
    'Thứ Ba',
    'Thứ Tư',
    'Thứ Năm',
    'Thứ Sáu',
    'Thứ Bảy',
    'Chủ Nhật',
  ];

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final date = '${_weekdays[now.weekday - 1]}, ${now.day} tháng ${now.month}';
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 24, 14, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            spacing: 12,
            children: [
              Padding(
                padding: const EdgeInsets.only(top: 10, bottom: 20),
                child: Column(
                  children: [
                    Text(
                      date,
                      style: t.body.copyWith(
                        fontWeight: FontWeight.w500,
                        color: c.textSecondary,
                      ),
                    ),
                    Text(
                      formatClock(now, seconds: false),
                      style: t.display.copyWith(
                        fontSize: 64,
                        fontWeight: FontWeight.w800,
                        color: c.textPrimary,
                      ),
                    ),
                  ],
                ),
              ),
              _Push(event: event, onCall: onCall, onView: onView),
            ],
          ),
        ),
      ),
    );
  }
}

class _Push extends StatelessWidget {
  const _Push({required this.event, this.onCall, this.onView});

  final FireEvent event;
  final VoidCallback? onCall;
  final VoidCallback? onView;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return GestureDetector(
      onTap: onView,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: c.bgRaised,
          borderRadius: BorderRadius.circular(22),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: 10,
          children: [
            Row(
              spacing: 8,
              children: [
                SvgPicture.asset(MpBrand.appIcon, width: 22, height: 22),
                Expanded(
                  child: Text(
                    'MẮT PHỐ · bây giờ',
                    style: t.caption.copyWith(
                      fontWeight: FontWeight.w500,
                      color: c.textSecondary,
                    ),
                  ),
                ),
              ],
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              spacing: 2,
              children: [
                Text(
                  'Có cháy · ${event.locationName}',
                  style: t.headline.copyWith(
                    fontWeight: FontWeight.w700,
                    color: c.statusFire,
                  ),
                ),
                Text(
                  'Phát hiện lửa lúc '
                  '${formatClock(event.detectedAt, seconds: false)}. '
                  'Chạm để xem ảnh.',
                  style: t.body.copyWith(
                    fontWeight: FontWeight.w500,
                    color: c.textPrimary,
                  ),
                ),
              ],
            ),
            const AlertEvidence(
              asset: MpIllustrations.feedFire,
              height: 150,
              artSize: MpIllustration.figmaSize,
            ),
            Row(
              spacing: 8,
              children: [
                Expanded(
                  child: MpButton(
                    label: 'Gọi 114',
                    kind: MpButtonKind.danger,
                    size: MpButtonSize.m,
                    icon: MpIcons.call,
                    onPressed: onCall ?? () {},
                  ),
                ),
                Expanded(
                  child: MpButton(
                    label: 'Xem',
                    kind: MpButtonKind.quiet,
                    size: MpButtonSize.m,
                    onPressed: onView ?? () {},
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
