import 'dart:async';

import 'package:flutter/material.dart';

import 'package:mat_pho/core/widgets/mp_tab_bar.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/models/fire_event.dart';
import 'package:mat_pho/features/history/history_detail_screen.dart';
import 'package:mat_pho/features/history/history_screen.dart';
import 'package:mat_pho/features/history/history_state.dart';
import '../gallery_registry.dart';
import '../gallery_scope.dart';

final rowGEntries = <GalleryEntry>[
  GalleryEntry(
    code: 'G1',
    title: 'Danh sách',
    builder: (_) => const GalleryScope(child: _TabFrame(HistoryScreen())),
  ),
  for (final (code, title, filter) in const [
    ('G1-FIRE', 'Lọc · Cháy', HistoryFilter.fire),
    ('G1-SAFE', 'Lọc · Không cháy', HistoryFilter.dismissed),
    ('G1-FALSE', 'Lọc · Báo nhầm', HistoryFilter.falseAlarm),
  ])
    GalleryEntry(
      code: code,
      title: title,
      builder: (_) => GalleryScope(
        overrides: [
          historyFilterProvider.overrideWith(
            () => HistoryFilterNotifier(filter),
          ),
        ],
        child: const _TabFrame(HistoryScreen()),
      ),
    ),
  GalleryEntry(
    code: 'G2',
    title: 'Đang tải',
    builder: (_) => GalleryScope(
      overrides: [
        historyListProvider.overrideWith(
          (ref, filter) => Completer<List<FireEvent>>().future,
        ),
      ],
      child: const _TabFrame(HistoryScreen()),
    ),
  ),
  GalleryEntry(
    code: 'G3',
    title: 'Chưa có sự kiện',
    builder: (_) => const GalleryScope(
      cases: {FakeCase.historyEmpty},
      child: _TabFrame(HistoryScreen()),
    ),
  ),
  GalleryEntry(
    code: 'G4',
    title: 'Chi tiết · cảnh báo',
    builder: (_) =>
        const GalleryScope(child: HistoryDetailScreen(eventId: 'evt-fire')),
  ),
  GalleryEntry(
    code: 'G5',
    title: 'Chi tiết · đã bác bỏ',
    builder: (_) => const GalleryScope(
      child: HistoryDetailScreen(eventId: 'evt-dismissed'),
    ),
  ),
  GalleryEntry(
    code: 'G8',
    title: 'Lỗi tải lịch sử',
    builder: (_) => const GalleryScope(
      cases: {FakeCase.historyServerError},
      child: _TabFrame(HistoryScreen()),
    ),
  ),
  GalleryEntry(
    code: 'G8-NET',
    title: 'Lỗi tải lịch sử · mất mạng (không có frame riêng)',
    builder: (_) => const GalleryScope(
      cases: {FakeCase.historyNetworkError},
      child: _TabFrame(HistoryScreen()),
    ),
  ),
];

class _TabFrame extends StatelessWidget {
  const _TabFrame(this.child);

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: child,
      bottomNavigationBar: MpTabBar(currentIndex: 1, onTap: (_) {}),
    );
  }
}
