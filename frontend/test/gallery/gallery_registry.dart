import 'package:flutter/material.dart';

import 'package:mat_pho/core/widgets/mp_tab_bar.dart';
import 'entries/kit_controls.dart';
import 'entries/kit_overlays.dart';
import 'kit_sheets.dart';

class GalleryEntry {
  const GalleryEntry({
    required this.code,
    required this.title,
    required this.builder,
  });

  final String code;

  final String title;

  final WidgetBuilder builder;
}

class GalleryGroup {
  const GalleryGroup(this.name, this.entries);

  final String name;
  final List<GalleryEntry> entries;
}

final galleryGroups = <GalleryGroup>[
  GalleryGroup('Kit', [
    for (final (i, label) in const ['Theo dõi', 'Lịch sử', 'Cài đặt'].indexed)
      GalleryEntry(
        code: 'TB${i + 1}',
        title: 'mp/TabBar · Active=$label',
        builder: (_) => _BottomPreview(MpTabBar(currentIndex: i, onTap: _noop)),
      ),
    GalleryEntry(
      code: 'IC',
      title: 'icon/* · active + idle',
      builder: (_) =>
          const _SheetPreview([IconSheet(), IconSheet(active: false)]),
    ),
    GalleryEntry(
      code: 'IL',
      title: 'ill/*',
      builder: (_) => const _SheetPreview([IllustrationSheet()]),
    ),
    GalleryEntry(
      code: 'BR',
      title: 'mp/logo-mark · mp/app-icon · mp/logo-lockup',
      builder: (_) => const _SheetPreview([BrandSheet()]),
    ),
    ...kitControlsEntries,
    ...kitOverlaysEntries,
  ]),
];

GalleryEntry? findGalleryEntry(String code) {
  for (final group in galleryGroups) {
    for (final entry in group.entries) {
      if (entry.code == code) return entry;
    }
  }
  return null;
}

void _noop(int _) {}

class _BottomPreview extends StatelessWidget {
  const _BottomPreview(this.child);

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Align(alignment: Alignment.bottomCenter, child: child),
    );
  }
}

class _SheetPreview extends StatelessWidget {
  const _SheetPreview(this.sheets);

  final List<Widget> sheets;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              spacing: 20,
              children: sheets,
            ),
          ),
        ),
      ),
    );
  }
}
