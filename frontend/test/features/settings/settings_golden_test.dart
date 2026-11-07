import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../gallery/entries/row_h.dart';

import '../../helpers/golden.dart';

void main() {
  for (final entry in rowHEntries) {
    testWidgets('golden ${entry.code}', (tester) async {
      await pumpGoldenScreen(tester, Builder(builder: entry.builder));
      for (var i = 0; i < 2; i++) {
        await tester.runAsync(() => Future<void>.delayed(Duration.zero));
        await tester.pumpAndSettle();
      }
      await expectLater(
        goldenFinder,
        matchesGoldenFile('../../goldens/h/${entry.code}.png'),
      );
    });
  }
}
