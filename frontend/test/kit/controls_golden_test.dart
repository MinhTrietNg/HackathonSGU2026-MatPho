import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import '../gallery/entries/kit_controls.dart';

import '../helpers/golden.dart';

void main() {
  for (final board in kitControlBoards) {
    testWidgets('kit controls ${board.code}', (tester) async {
      await pumpGoldenComponent(
        tester,
        SizedBox.fromSize(
          size: board.size,
          child: Builder(builder: board.builder),
        ),
        size: board.size,
      );
      await expectLater(
        goldenFinder,
        matchesGoldenFile('../goldens/kit/${board.code}.png'),
      );
    });
  }
}
