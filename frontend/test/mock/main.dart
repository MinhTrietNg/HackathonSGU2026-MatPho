import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mat_pho/app.dart';

import '../fakes/fake_overrides.dart';
import '../fakes/fake_scenario.dart';

// Chạy app bằng backend giả trong RAM, không Firebase, không gọi mạng:
//   flutter run -t test/mock/main.dart
//   flutter run -t test/mock/main.dart --dart-define=MOCK_CASES=noCameras,historyEmpty
// MOCK_CASES là tên các FakeCase, cách nhau bằng dấu phẩy. Mặc định: signedOut.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  runApp(
    ProviderScope(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(
          FakeScenario(cases: mockCases()),
        ),
      ]),
      child: const MatPhoApp(),
    ),
  );
}

Set<FakeCase> mockCases([
  String raw = const String.fromEnvironment(
    'MOCK_CASES',
    defaultValue: 'signedOut',
  ),
]) {
  final byName = {for (final c in FakeCase.values) c.name: c};
  return {
    for (final name in raw.split(',').map((s) => s.trim()))
      if (name.isNotEmpty)
        byName[name] ??
            (throw ArgumentError.value(
              name,
              'MOCK_CASES',
              'Không có FakeCase này',
            )),
  };
}
