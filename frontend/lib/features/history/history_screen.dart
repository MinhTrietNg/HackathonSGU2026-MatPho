library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/time_format.dart';
import '../../core/widgets/mp_chip.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../core/widgets/mp_list_card.dart';
import '../../core/widgets/mp_section_label.dart';
import '../../core/widgets/mp_still.dart';
import '../../data/models/fire_event.dart';
import '../../data/providers.dart';
import '../alert/alert_widgets.dart' show EvidenceNetworkImage;
import 'history_state.dart';
import 'history_widgets.dart';

class HistoryScreen extends ConsumerStatefulWidget {
  const HistoryScreen({super.key});

  @override
  ConsumerState<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends ConsumerState<HistoryScreen> {
  bool? _active;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final active = TickerMode.valuesOf(context).enabled;
    if (_active == false && active) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) ref.invalidate(historyListProvider);
      });
    }
    _active = active;
  }

  @override
  Widget build(BuildContext context) {
    final filter = ref.watch(historyFilterProvider);
    final events = ref.watch(historyListProvider(filter));
    final rows = events.value;

    final Widget body;
    if (rows != null) {
      body = rows.isEmpty && filter == HistoryFilter.all
          ? const _EmptyBody()
          : _ListBody(filter: filter, events: rows);
    } else if (events.hasError && !events.isLoading) {
      body = HistoryLoadError(
        error: events.error!,
        onRetry: () => ref.invalidate(historyListProvider(filter)),
      );
    } else {
      body = _ListBody(filter: filter, events: null);
    }
    final isList = body is _ListBody;

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(20, 8, 20, isList ? 12 : 14),
              child: const MpHeader.title(title: 'Lịch sử'),
            ),
            Expanded(child: body),
          ],
        ),
      ),
    );
  }
}

class _ListBody extends ConsumerWidget {
  const _ListBody({required this.filter, required this.events});

  final HistoryFilter filter;

  final List<FireEvent>? events;

  static const _chips = [
    (HistoryFilter.all, 'Tất cả'),
    (HistoryFilter.fire, 'Cháy'),
    (HistoryFilter.dismissed, 'Không cháy'),
    (HistoryFilter.falseAlarm, 'Báo nhầm'),
  ];

  static const _skeletonTitleWidths = [150.0, 140.0, 130.0, 120.0, 110.0];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.mpColors;
    final events = this.events;
    final chips = Row(
      spacing: 6,
      children: [
        for (final (value, label) in _chips)
          MpChip(
            label: label,
            style: MpChipStyle.filled,
            selected: value == filter,
            onTap: () => ref.read(historyFilterProvider.notifier).select(value),
          ),
      ],
    );

    final children = <Widget>[chips];
    if (events == null) {
      children.addAll(_skeletonTitleWidths.map(_SkeletonRow.new));
    } else {
      final now = ref.watch(clockProvider)();
      String? section;
      for (final event in events) {
        final label = _sectionLabel(event.detectedAt, now);
        if (label != section) {
          if (section != null) children.add(const SizedBox(height: 4));
          children.add(MpSectionLabel(label));
          section = label;
        }
        children.add(_EventRow(event));
      }
      final days = historyRetention.inDays;
      children
        ..add(const SizedBox(height: 4))
        ..add(
          Text(
            filter == HistoryFilter.all
                ? 'Đã hiện hết · $days ngày gần nhất'
                : 'Đang lọc “${_label(filter)}” · $days ngày gần nhất',
            textAlign: TextAlign.center,
            style: context.mpText.caption.copyWith(
              fontWeight: FontWeight.w500,
              color: c.textSecondary,
            ),
          ),
        );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 12,
        children: children,
      ),
    );
  }

  static String _label(HistoryFilter filter) =>
      _chips.firstWhere((chip) => chip.$1 == filter).$2;

  static String _sectionLabel(DateTime at, DateTime now) {
    final day = DateTime(at.year, at.month, at.day);
    final today = DateTime(now.year, now.month, now.day);
    final daysAgo = today.difference(day).inHours ~/ 24;
    if (daysAgo <= 0) return 'HÔM NAY';
    if (daysAgo == 1) return 'HÔM QUA';
    String two(int v) => v.toString().padLeft(2, '0');
    return '${two(at.day)}/${two(at.month)}';
  }
}

class _EventRow extends ConsumerWidget {
  const _EventRow(this.event);

  final FireEvent event;

  static const _artSize = Size(75, 75 * 180 / 280);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final still = ref.watch(
      eventStillProvider((cameraId: event.cameraId, sign: event.sign)),
    );
    final local = still != null
        ? MpStill(still, size: MpListCard.thumbnailSize)
        : MpIllustration(
            historyFeedAsset(event),
            size: _artSize,
            animated: true,
          );
    return MpListCard(
      thumbnail: switch (event.stillUrl) {
        final url? => SizedBox.fromSize(
          size: MpListCard.thumbnailSize,
          child: EvidenceNetworkImage(url, fallback: local),
        ),
        null => local,
      },
      title: event.summary,
      subtitle: [
        event.locationName,
        formatClock(event.detectedAt, seconds: false),
        if (event.called114) 'đã gọi 114',
      ].join(' · '),
      badge: HistoryStatusBadge(event.status),
      trailing: const MpChevron(),
      onTap: () => context.push(AppRoutes.historyDetail(event.id)),
    );
  }
}

class _SkeletonRow extends StatelessWidget {
  const _SkeletonRow(this.titleWidth);

  final double titleWidth;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    Widget block(double width, double height) => Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: c.bgRaised,
        borderRadius: BorderRadius.circular(height / 2),
      ),
    );
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: c.bgCard,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        spacing: 12,
        children: [
          Container(
            width: MpListCard.thumbnailSize.width,
            height: MpListCard.thumbnailSize.height,
            decoration: BoxDecoration(
              color: c.bgRaised,
              borderRadius: BorderRadius.circular(10),
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            spacing: 8,
            children: [block(titleWidth, 12), block(100, 10)],
          ),
        ],
      ),
    );
  }
}

class _EmptyBody extends StatelessWidget {
  const _EmptyBody();

  static const _artSize = Size(260, 260 * 180 / 280);

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 14,
        children: [
          const Spacer(),
          const Center(
            child: MpIllustration(MpIllustrations.emptyHistory, size: _artSize),
          ),
          Column(
            spacing: 8,
            children: [
              Text(
                'Chưa có gì xảy ra',
                textAlign: TextAlign.center,
                style: t.title.copyWith(
                  fontWeight: FontWeight.w800,
                  color: c.textPrimary,
                ),
              ),
              Text(
                'Các lần báo cháy sẽ hiện ở đây.',
                textAlign: TextAlign.center,
                style: t.body.copyWith(
                  fontWeight: FontWeight.w500,
                  color: c.textSecondary,
                ),
              ),
            ],
          ),
          const Spacer(),
        ],
      ),
    );
  }
}
