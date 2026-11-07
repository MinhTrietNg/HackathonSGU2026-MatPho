library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/theme.dart';
import '../../core/time_format.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_feed_tag.dart';
import '../../core/widgets/mp_header.dart';
import '../../data/models/fire_event.dart';
import '../../data/providers.dart';
import '../alert/alert_widgets.dart' show AlertEvidence;
import 'evidence_slideshow.dart';
import 'history_state.dart';
import 'history_widgets.dart';

class HistoryDetailScreen extends ConsumerWidget {
  const HistoryDetailScreen({super.key, required this.eventId});

  final String eventId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final event = ref.watch(historyDetailProvider(eventId));
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
              child: MpHeader.back(
                title: 'Chi tiết',
                onBack: () => Navigator.of(context).maybePop(),
              ),
            ),
            Expanded(
              child: switch (event) {
                AsyncValue(value: final event?) => _Details(event),
                AsyncValue(error: final error?, isLoading: false) =>
                  HistoryLoadError(
                    error: error,
                    onRetry: () =>
                        ref.invalidate(historyDetailProvider(eventId)),
                  ),
                _ => const SizedBox.shrink(),
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _Details extends ConsumerWidget {
  const _Details(this.event);

  final FireEvent event;

  static const _artSize = Size(366, 366 * 180 / 280);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.mpColors;
    final at = event.detectedAt;
    final tag =
        '${event.locationName.toUpperCase()} · ${formatFeedTime(event.detectedAt)}';
    final tagOnTop = event.sign == null;
    String two(int v) => v.toString().padLeft(2, '0');
    final still = ref.watch(
      eventStillProvider((cameraId: event.cameraId, sign: event.sign)),
    );
    final Widget? moving = event.snapshots.isNotEmpty
        ? EvidenceSlideshow(
            snapshots: event.snapshots,
            sign: event.sign,
            confidence: event.confidence,
          )
        : null;

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 12,
        children: [
          MpDarkIsland(
            child: Stack(
              children: [
                AlertEvidence(
                  asset: historyFeedAsset(event),
                  artSize: _artSize,
                  tag: tagOnTop ? null : tag,
                  still: still,
                  stillUrl: event.stillUrl,
                  video: moving,
                ),
                if (tagOnTop)
                  Positioned(left: 10, top: 10, child: MpFeedTag(tag)),
              ],
            ),
          ),
          Row(
            spacing: 8,
            children: [
              HistoryStatusBadge(event.status),
              Text(
                '${two(at.day)}/${two(at.month)} · ${formatClock(at)}',
                style: context.mpText.mono.copyWith(
                  fontWeight: FontWeight.w600,
                  color: c.textSecondary,
                ),
              ),
            ],
          ),
          if (event.status == EventStatus.dismissed && event.detail != null)
            _ReasonCard(title: event.summary, body: event.detail!),
          if (event.timeline.isNotEmpty) _Timeline(event),
        ],
      ),
    );
  }
}

class _ReasonCard extends StatelessWidget {
  const _ReasonCard({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: c.bgCard,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: 12,
        children: [
          MpDuotoneIcon(
            MpIcons.ai,
            outline: c.brandAccent,
            accent: c.brandAccent,
            size: 22,
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              spacing: 4,
              children: [
                Text(
                  title,
                  style: t.body.copyWith(
                    fontWeight: FontWeight.w700,
                    color: c.textPrimary,
                  ),
                ),
                Text(
                  body,
                  style: t.caption.copyWith(
                    fontWeight: FontWeight.w500,
                    color: c.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Timeline extends StatelessWidget {
  const _Timeline(this.event);

  final FireEvent event;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final latency = event.notifyLatency;
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 6, 14, 10),
      decoration: BoxDecoration(
        color: c.bgCard,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final step in event.timeline) _StepRow(step),
          if (latency != null) _LatencyNote(latency),
        ],
      ),
    );
  }
}

class _StepRow extends StatelessWidget {
  const _StepRow(this.step);

  final TimelineStep step;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final (label, dot) = switch (step.kind) {
      TimelineStepKind.detected => ('Máy phát hiện', c.statusWarn),
      TimelineStepKind.imageSent => ('Gửi ảnh', c.brandAccent),
      TimelineStepKind.confirmedFire => ('Xác nhận cháy', c.brandAccent),
      TimelineStepKind.confirmedNotFire => (
        'Xác nhận không cháy',
        c.brandAccent,
      ),
      TimelineStepKind.notified => ('Báo tới điện thoại', c.statusFire),
      TimelineStepKind.notNotified => ('Không báo', c.textMuted),
    };
    final offset = step.offset;
    final value = switch (offset) {
      null => '—',
      Duration.zero => '${formatStepSeconds(offset)} s',
      _ => '+${formatStepSeconds(offset)} s',
    };
    return MergeSemantics(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Row(
          spacing: 10,
          children: [
            Container(
              width: 10,
              height: 10,
              decoration: BoxDecoration(
                color: dot,
                borderRadius: BorderRadius.circular(5),
              ),
            ),
            Expanded(
              child: Text(
                label,
                style: t.body.copyWith(
                  fontWeight: FontWeight.w500,
                  color: c.textPrimary,
                ),
              ),
            ),
            Text(
              value,
              style: t.mono.copyWith(
                fontWeight: FontWeight.w600,
                color: c.textSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LatencyNote extends StatelessWidget {
  const _LatencyNote(this.latency);

  final Duration latency;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final onTime = latency <= alertLatencyGoal;
    final (bg, fg, icon) = onTime
        ? (c.statusOkSoft, c.statusOk, MpIcons.check)
        : (c.statusWarnSoft, c.statusWarn, MpIcons.alert);
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        spacing: 8,
        children: [
          MpDuotoneIcon(icon, outline: fg, accent: fg, size: 18),
          Expanded(
            child: Text(
              'Báo sau ${formatStepSeconds(latency)} giây',
              style: context.mpText.body.copyWith(
                fontWeight: FontWeight.w700,
                color: fg,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
