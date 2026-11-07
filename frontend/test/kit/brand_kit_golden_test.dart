import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import '../gallery/kit_sheets.dart';

import '../helpers/golden.dart';

void main() {
  final sheets = <(String, Widget, Size)>[
    ('IC', const IconSheet(), IconSheet.size),
    ('IC_idle', const IconSheet(active: false), IconSheet.size),
    ('IL', const IllustrationSheet(), IllustrationSheet.size),
    ('BR', const BrandSheet(), BrandSheet.size),
  ];
  for (final (code, sheet, size) in sheets) {
    testWidgets('brand kit $code', (tester) async {
      await pumpGoldenComponent(tester, sheet, size: size);
      await expectLater(
        goldenFinder,
        matchesGoldenFile('../goldens/kit/$code.png'),
      );
    });
  }
}
