import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'gallery/gallery_registry.dart';

import 'helpers/golden.dart';

void main() {
  test('gallery codes are unique', () {
    final codes = [
      for (final g in galleryGroups) ...g.entries.map((e) => e.code),
    ];
    expect(codes.toSet().length, codes.length);
  });

  for (final group in galleryGroups) {
    for (final entry in group.entries) {
      testWidgets('gallery ${group.name}/${entry.code} builds', (tester) async {
        await pumpGoldenScreen(tester, Builder(builder: entry.builder));
        expect(tester.takeException(), isNull);
      });
    }
  }
}
