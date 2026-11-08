library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/time_format.dart';
import '../../core/widgets/mp_badge.dart';
import '../../core/widgets/mp_banner.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_feed_tag.dart' show formatFeedTime;
import '../../core/widgets/mp_fill_scroll_view.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../core/widgets/mp_info_card.dart';
import '../../data/models/fire_event.dart';
import '../../data/providers.dart';
import '../../data/services/notification_service.dart';
import '../auth/auth_session.dart' show SignedIn, authSessionProvider;
import 'alert_actions.dart';
import 'alert_controller.dart';
import 'alert_dialogs.dart';
import 'alert_widgets.dart';

class AlertScreen extends ConsumerStatefulWidget {
  const AlertScreen({super.key, required this.eventId});

  final String eventId;

  @override
  ConsumerState<AlertScreen> createState() => _AlertScreenState();
}

class _AlertScreenState extends ConsumerState<AlertScreen> {
  late final NotificationService _notifications;

  @override
  void initState() {
    super.initState();
    _notifications = ref.read(notificationServiceProvider);
    hideMpAlertBanner();
  }

  // The siren rings while F2/F4 is open; leaving it means the alert was seen.
  @override
  void dispose() {
    unawaited(_notifications.clearFireAlert(widget.eventId));
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final alert = ref.watch(alertProvider(widget.eventId));
    final state = alert.value;
    if (state != null) return _AlertBody(eventId: widget.eventId, state: state);
    return alert.hasError ? const _AlertLoadFailed() : const Scaffold();
  }
}

class _AlertLoadFailed extends ConsumerWidget {
  const _AlertLoadFailed();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            spacing: 12,
            children: [
              const MpBanner(
                tone: MpBannerTone.warn,
                icon: MpIcons.wifiOff,
                title: 'Không tải được cảnh báo',
                body: 'Kiểm tra kết nối rồi thử lại.',
              ),
              const Spacer(),
              MpButton(
                label: 'Gọi 114',
                kind: MpButtonKind.danger,
                size: MpButtonSize.xl,
                icon: MpIcons.call,
                onPressed: () => callEmergency(context, ref),
              ),
              MpButton(
                label: 'Về Theo dõi',
                kind: MpButtonKind.ghost,
                size: MpButtonSize.m,
                onPressed: () => context.go(AppRoutes.monitor),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AlertBody extends ConsumerWidget {
  const _AlertBody({required this.eventId, required this.state});

  final String eventId;
  final AlertState state;

  bool get _unverified => state.event.status == EventStatus.unverified;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final event = state.event;
    return Scaffold(
      body: Stack(
        children: [
          if (!_unverified) const AlertGlow(top: -172),
          SafeArea(
            child: MpFillScrollView(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  spacing: 12,
                  children: [
                    _Heading(event: event, unverified: _unverified),
                    _evidence(event, ref),
                    if (_unverified)
                      const MpBanner(
                        tone: MpBannerTone.warn,
                        icon: MpIcons.alert,
                        title: 'Chưa kiểm tra lại được',
                        body: 'Xem camera hoặc tới tận nơi kiểm tra.',
                      )
                    else
                      _Details(event: event),
                    const Spacer(),
                    ..._actions(context, ref),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _evidence(FireEvent event, WidgetRef ref) {
    final still = ref.watch(
      eventStillProvider((cameraId: event.cameraId, sign: event.sign)),
    );
    final tag =
        '${event.locationName.toUpperCase()} · '
        '${formatFeedTime(event.detectedAt)}';
    final demoArt = ref.watch(demoSceneArtProvider);
    return _unverified
        ? AlertEvidence(
            asset: demoArt ? MpIllustrations.feedSmoke : null,
            artSize: const Size(336, 216),
            tag: tag,
            still: still,
            stillUrl: event.stillUrl,
          )
        : AlertEvidence(
            asset: demoArt ? MpIllustrations.feedFire : null,
            artSize: const Size(366, 366 * 180 / 280),
            tag: tag,
            still: still,
            stillUrl: event.stillUrl,
          );
  }

  List<Widget> _actions(BuildContext context, WidgetRef ref) {
    final call = MpButton(
      label: 'Gọi 114',
      kind: MpButtonKind.danger,
      size: MpButtonSize.xl,
      icon: MpIcons.call,
      onPressed: () => dial114(context, ref, eventId),
    );
    final home = MpButton(
      label: 'Về Theo dõi',
      kind: MpButtonKind.ghost,
      size: MpButtonSize.m,
      onPressed: () => context.go(AppRoutes.monitor),
    );
    if (state.event.status == EventStatus.falseAlarm) {
      return [
        const MpBanner(
          tone: MpBannerTone.accent,
          icon: MpIcons.flag,
          outlined: false,
          title: 'Đã báo nhầm',
        ),
        call,
        home,
      ];
    }
    if (state.event.resolved) {
      final notifier = ref.read(alertProvider(eventId).notifier);
      final session = ref.watch(authSessionProvider);
      final self = session is SignedIn ? session.user.fullName : null;
      final by = switch (state.event.resolvedByName) {
        final name? when name != self => name,
        _ => null,
      };
      return [
        MpBanner(
          tone: MpBannerTone.ok,
          icon: MpIcons.check,
          outlined: false,
          title: by == null ? 'Bạn đang xử lý' : '$by đang xử lý',
          body: 'Đã ngừng báo cho người khác.',
          actionLabel: state.canUndo ? 'Hoàn tác' : null,
          onAction: notifier.undo,
        ),
        call,
        home,
      ];
    }
    switch (state.closing) {
      case AlertClosing.unknown:
        return [call];
      case AlertClosing.denied:
        return [call, home];
      case AlertClosing.allowed:
    }
    final falseAlarm = MpButton(
      label: 'Báo nhầm',
      kind: MpButtonKind.report,
      icon: MpIcons.flag,
      onPressed: () async {
        if (await confirmFalseAlarm(context) && context.mounted) {
          await closeAlert(context, ref, eventId, AlertOutcome.falseAlarm);
        }
      },
    );
    final second = _unverified
        ? AlertDuotoneSecondaryButton(
            label: 'Xem camera',
            icon: MpIcons.eye,
            onPressed: () => openEventCamera(context, ref, eventId),
          )
        : MpButton(
            label: 'Đã xử lý',
            kind: MpButtonKind.resolve,
            icon: MpIcons.check,
            onPressed: () async {
              if (await confirmResolved(context) && context.mounted) {
                await closeAlert(context, ref, eventId, AlertOutcome.resolved);
              }
            },
          );
    return [
      call,
      Row(
        spacing: 12,
        children: [
          Expanded(child: falseAlarm),
          Expanded(child: second),
        ],
      ),
    ];
  }
}

class _Heading extends StatelessWidget {
  const _Heading({required this.event, required this.unverified});

  final FireEvent event;
  final bool unverified;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final where = event.locationName;
    final title = !unverified
        ? 'Cháy ở $where'
        : event.sign == DetectedSign.fire
        ? 'Có thể có cháy ở $where'
        : 'Có thể có khói ở $where';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: 6,
      children: [
        unverified
            ? const MpBadge(label: 'Chưa chắc chắn', tone: MpBadgeTone.warn)
            : const MpBadge(label: 'Đã xác nhận cháy', tone: MpBadgeTone.fire),
        Semantics(
          header: true,
          child: Text(
            title,
            style: context.mpText.title.copyWith(
              fontWeight: FontWeight.w800,
              color: c.textPrimary,
            ),
          ),
        ),
      ],
    );
  }
}

class _Details extends ConsumerWidget {
  const _Details({required this.event});

  final FireEvent event;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.mpColors;
    final now = ref.watch(clockProvider)();
    final confidence = event.confidence;
    final checks = event.checkCount;
    final detail = event.detail;
    return MpInfoCard(
      rows: [
        (
          label: 'Lúc',
          value:
              '${formatClock(event.detectedAt)} · '
              '${_ago(now.difference(event.detectedAt))}',
          valueColor: null,
        ),
        if (confidence != null)
          (
            label: 'Độ chắc chắn',
            value: [
              '${(confidence * 100).round()}%',
              if (checks != null) 'đã kiểm tra $checks lần',
            ].join(' · '),
            valueColor: c.statusFire,
          ),
        if (detail != null) (label: 'Thấy gì', value: detail, valueColor: null),
      ],
    );
  }

  static String _ago(Duration d) {
    final s = d.inSeconds < 0 ? 0 : d.inSeconds;
    if (s < 60) return '$s giây trước';
    if (s < 3600) return '${s ~/ 60} phút trước';
    return '${s ~/ 3600} giờ trước';
  }
}
