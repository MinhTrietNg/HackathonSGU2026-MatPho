import 'package:flutter/material.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_badge.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../data/errors.dart';
import '../../data/models/fire_event.dart';

class HistoryStatusBadge extends StatelessWidget {
  const HistoryStatusBadge(this.status, {super.key});

  final EventStatus status;

  @override
  Widget build(BuildContext context) {
    final (label, tone) = switch (status) {
      EventStatus.fire => ('Cháy', MpBadgeTone.fire),
      EventStatus.dismissed => ('Không cháy', MpBadgeTone.ok),
      EventStatus.unverified => ('Chưa chắc chắn', MpBadgeTone.warn),
      EventStatus.falseAlarm => ('Báo nhầm', MpBadgeTone.neutral),
    };
    return MpBadge(label: label, tone: tone);
  }
}

String historyFeedAsset(FireEvent event) => switch (event.sign) {
  DetectedSign.fire => MpIllustrations.feedFire,
  DetectedSign.smoke => MpIllustrations.feedSmoke,
  null => MpIllustrations.feed,
};

class HistoryLoadError extends StatelessWidget {
  const HistoryLoadError({
    super.key,
    required this.error,
    required this.onRetry,
    this.busy = false,
  });

  final Object error;
  final VoidCallback onRetry;
  final bool busy;

  static const _artSize = Size(260, 260 * 180 / 280);

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final (art, body) = switch (error) {
      NetworkException() => (
        MpIllustrations.offline,
        'Kiểm tra kết nối rồi thử lại.',
      ),
      _ => (MpIllustrations.serverError, 'Báo cháy vẫn hoạt động bình thường.'),
    };
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 14,
        children: [
          const Spacer(),
          Center(child: MpIllustration(art, size: _artSize)),
          Column(
            spacing: 8,
            children: [
              Text(
                'Không tải được',
                textAlign: TextAlign.center,
                style: t.title.copyWith(
                  fontWeight: FontWeight.w800,
                  color: c.textPrimary,
                ),
              ),
              Text(
                body,
                textAlign: TextAlign.center,
                style: t.body.copyWith(
                  fontWeight: FontWeight.w500,
                  color: c.textSecondary,
                ),
              ),
            ],
          ),
          const Spacer(),
          MpButton(label: 'Thử lại', onPressed: onRetry, busy: busy),
        ],
      ),
    );
  }
}
