import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import '../../gallery/entries/row_i.dart';

import '../../helpers/golden.dart';

void main() {
  for (final entry in rowIEntries) {
    testWidgets('golden ${entry.code}', (tester) async {
      addTearDown(hideMpToast);
      await pumpGoldenScreen(tester, Builder(builder: entry.builder));
      await tester.runAsync(() => Future<void>.delayed(Duration.zero));
      await tester.pumpAndSettle();
      await expectLater(
        goldenFinder,
        matchesGoldenFile('../../goldens/i/${entry.code}.png'),
      );
    });
  }
}
