import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../gallery/entries/row_g.dart';

import '../../helpers/golden.dart';

void main() {
  for (final entry in rowGEntries) {
    testWidgets('golden ${entry.code}', (tester) async {
      await pumpGoldenScreen(tester, Builder(builder: entry.builder));
      await tester.runAsync(() => Future<void>.delayed(Duration.zero));
      await tester.pumpAndSettle();
      await expectLater(
        goldenFinder,
        matchesGoldenFile('../../goldens/g/${entry.code}.png'),
      );
    });
  }
}
