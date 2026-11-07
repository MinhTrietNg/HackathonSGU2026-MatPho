import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_banner.dart';
import 'package:mat_pho/core/widgets/mp_tab_bar.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import '../gallery/entries/kit_controls.dart';
import '../gallery/entries/kit_overlays.dart';
import '../gallery/gallery_registry.dart';
import '../gallery/kit_sheets.dart';

import '../helpers/golden.dart';

void main() {
  final theme = AppTheme.light();

  for (final group in galleryGroups) {
    final kit = group.name == 'Kit';
    for (final entry in group.entries) {
      if (kit && _skipped.contains(entry.code)) continue;
      final row = kit ? 'kit' : entry.code[0].toLowerCase();
      final components = kit ? _kitComponents[entry.code] : null;

      if (components != null) {
        for (final (name, widget, size) in components) {
          testWidgets('light $row/$name', (tester) async {
            await pumpGoldenComponent(tester, widget, size: size, theme: theme);
            await expectLater(
              goldenFinder,
              matchesGoldenFile('../goldens/light/$row/$name.png'),
            );
          });
        }
        continue;
      }

      testWidgets('light $row/${entry.code}', (tester) async {
        addTearDown(hideMpToast);
        addTearDown(hideMpAlertBanner);
        await pumpGoldenScreen(
          tester,
          Builder(builder: entry.builder),
          theme: theme,
        );
        for (var i = 0; i < 2; i++) {
          await tester.runAsync(() => Future<void>.delayed(Duration.zero));
          await tester.pumpAndSettle();
        }
        await expectLater(
          goldenFinder,
          matchesGoldenFile('../goldens/light/$row/${entry.code}.png'),
        );
      });
    }
  }
}

const _skipped = {'BR'};

final _kitComponents = <String, List<(String, Widget, Size)>>{
  for (final (i, code) in const ['TB1', 'TB2', 'TB3'].indexed)
    code: [
      (
        code,
        MpTabBar(currentIndex: i, onTap: (_) {}),
        const Size(360, MpTabBar.height),
      ),
    ],
  'IC': [
    ('IC', const IconSheet(), IconSheet.size),
    ('IC_idle', const IconSheet(active: false), IconSheet.size),
  ],
  'IL': [('IL', const IllustrationSheet(), IllustrationSheet.size)],
  for (final board in kitControlBoards)
    board.code: [
      (
        board.code,
        SizedBox.fromSize(
          size: board.size,
          child: Builder(builder: board.builder),
        ),
        board.size,
      ),
    ],
  for (final board in kitBannerBoards)
    board.code: [
      (
        board.code,
        Align(
          alignment: Alignment.topLeft,
          child: SizedBox(
            width: board.size.width,
            child: Builder(builder: board.builder),
          ),
        ),
        board.size,
      ),
    ],
};
