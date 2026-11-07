import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/widgets/mp_tab_bar.dart';

import '../helpers/golden.dart';

void main() {
  for (final (i, code) in const ['TB1', 'TB2', 'TB3'].indexed) {
    testWidgets('mp/TabBar $code', (tester) async {
      await pumpGoldenComponent(
        tester,
        MpTabBar(currentIndex: i, onTap: (_) {}),
        size: const Size(360, MpTabBar.height),
      );
      await expectLater(
        goldenFinder,
        matchesGoldenFile('../goldens/kit/$code.png'),
      );
    });
  }
}
