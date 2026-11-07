import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import '../../gallery/entries/row_j.dart';

import '../../helpers/golden.dart';

void main() {
  for (final entry in rowJEntries) {
    testWidgets('golden ${entry.code}', (tester) async {
      addTearDown(hideMpToast);
      await pumpGoldenScreen(tester, Builder(builder: entry.builder));
      for (var i = 0; i < 2; i++) {
        await tester.runAsync(() => Future<void>.delayed(Duration.zero));
        await tester.pumpAndSettle();
      }
      await expectLater(
        goldenFinder,
        matchesGoldenFile('../../goldens/j/${entry.code}.png'),
      );
    });
  }
}
