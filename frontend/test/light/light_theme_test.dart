import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/app.dart';
import 'package:mat_pho/core/theme/appearance.dart';
import 'package:mat_pho/core/theme/theme.dart';
import '../fakes/fake_overrides.dart';
import '../fakes/fake_scenario.dart';

void main() {
  test('AppTheme.light carries the Light tokens and dark status bar icons', () {
    final theme = AppTheme.light();
    expect(theme.brightness, Brightness.light);
    expect(theme.extension<MpColors>(), same(MpColors.light));
    expect(theme.scaffoldBackgroundColor, MpColors.light.bgBase);
    expect(
      AppTheme.systemOverlayStyle(theme).statusBarIconBrightness,
      Brightness.dark,
    );
    expect(
      AppTheme.systemOverlayStyle(AppTheme.dark()).statusBarIconBrightness,
      Brightness.light,
    );
  });

  testWidgets('MpDarkIsland keeps the Dark tokens under the Light theme', (
    tester,
  ) async {
    late MpColors outside, inside;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Builder(
          builder: (context) {
            outside = context.mpColors;
            return MpDarkIsland(
              child: Builder(
                builder: (context) {
                  inside = context.mpColors;
                  return const SizedBox();
                },
              ),
            );
          },
        ),
      ),
    );
    expect(outside, same(MpColors.light));
    expect(inside, same(MpColors.dark));
  });

  testWidgets('H1 "Giao diện sáng" switches the app theme', (tester) async {
    final container = ProviderContainer(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(FakeScenario.test()),
      ]),
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(container: container, child: const MatPhoApp()),
    );
    ThemeMode mode() =>
        tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode!;

    expect(mode(), ThemeMode.dark);
    container.read(lightAppearanceProvider.notifier).set(true);
    await tester.pump();
    expect(mode(), ThemeMode.light);

    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
  });
}
