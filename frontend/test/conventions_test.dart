import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('no color literals outside lib/core/theme', () {
    final hex = RegExp(
      r'Color\(\s*0x|#[0-9a-fA-F]{6}\b|Color\.fromARGB|Color\.fromRGBO',
    );
    final offenders = <String>[];
    for (final file in Directory('lib').listSync(recursive: true)) {
      final path = file.path.replaceAll(r'\', '/');
      if (file is! File || !path.endsWith('.dart')) continue;
      if (path.startsWith('lib/core/theme/')) continue;
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        if (hex.hasMatch(lines[i])) offenders.add('$path:${i + 1}');
      }
    }
    expect(offenders, isEmpty);
  });
}
