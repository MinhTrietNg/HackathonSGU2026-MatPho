import 'package:flutter_test/flutter_test.dart';
import '../../gallery/entries/rows_abc.dart';

import '../../helpers/golden.dart';

void main() {
  for (final frame in authFrames) {
    testWidgets('auth ${frame.code} · ${frame.title}', (tester) async {
      await pumpGoldenScreen(tester, AuthFramePreview(frame));
      await expectLater(
        goldenFinder,
        matchesGoldenFile(
          '../../goldens/${frame.code[0].toLowerCase()}/${frame.code}.png',
        ),
      );
    });
  }
}
