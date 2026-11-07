import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/theme/theme.dart';

import '../helpers/fake_status_bar.dart';
import '../helpers/golden.dart';

void main() {
  testWidgets('mp/StatusBar', (tester) async {
    await pumpGoldenComponent(
      tester,
      Builder(
        builder: (context) => ColoredBox(
          color: context.mpColors.bgBase,
          child: const FakeStatusBar(),
        ),
      ),
      size: const Size(360, FakeStatusBar.height),
    );
    await expectLater(
      goldenFinder,
      matchesGoldenFile('../goldens/kit/status_bar.png'),
    );
  });
}
