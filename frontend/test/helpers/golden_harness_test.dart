import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'golden.dart';

void main() {
  testWidgets('screen harness mirrors a Figma frame', (tester) async {
    late MediaQueryData data;
    await pumpGoldenScreen(
      tester,
      Builder(
        builder: (context) {
          data = MediaQuery.of(context);
          return const SizedBox.expand();
        },
      ),
    );
    expect(data.size, const Size(358, 778));
    expect(data.padding, const EdgeInsets.only(top: 40));
    expect(find.text('21:47'), findsOneWidget);
  });
}
