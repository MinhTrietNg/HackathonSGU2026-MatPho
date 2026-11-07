import 'package:flutter_test/flutter_test.dart';
import '../../gallery/entries/row_e.dart';

import '../../helpers/golden.dart';

void main() {
  for (final demo in watchDemos) {
    testWidgets('watch ${demo.code}', (tester) async {
      await pumpGoldenScreen(tester, WatchPreview(demo));
      await expectLater(
        goldenFinder,
        matchesGoldenFile('../../goldens/e/${demo.code}.png'),
      );
    });
  }
}
