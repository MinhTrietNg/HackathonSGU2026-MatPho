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
                AsyncValue(:final error?, :final isLoading) => HistoryLoadError(
                  error: error,
                  busy: isLoading,
                  onRetry: () => ref.invalidate(historyDetailProvider(eventId)),
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
                  asset: ref.watch(demoSceneArtProvider)
                      ? historyFeedAsset(event)
                      : null,
                  artSize: _artSize,
                  still: still,
                  stillUrl: event.stillUrl,
                  video: moving,
                ),
                // Time top left, place top right; a long place name is
                // cut, never pushed into the time.
                Positioned(
                  left: 10,
                  top: 10,
                  right: 10,
                  child: Row(
                    spacing: 12,
                    children: [
                      MpFeedTag(formatFeedTime(at)),
                      Expanded(
                        child: Align(
                          alignment: Alignment.centerRight,
                          child: MpFeedTag(event.locationName.toUpperCase()),
                        ),
                      ),
                    ],
                  ),
                ),
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
