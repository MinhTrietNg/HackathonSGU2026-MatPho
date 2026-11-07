import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/theme/theme.dart';

import 'fake_status_bar.dart';

const kFigmaFrameSize = Size(360, 780);

const kGoldenPixelRatio = 2.0;

final goldenFinder = find.byType(ProviderScope);

Future<void> pumpGoldenScreen(
  WidgetTester tester,
  Widget screen, {
  List<Override> overrides = const [],
  ThemeData? theme,
}) async {
  await _pump(
    tester,
    size: kFigmaFrameSize,
    overrides: overrides,
    theme: theme,
    builder: (child) => _FigmaFrame(child: child),
    child: screen,
  );
}

Future<void> pumpGoldenComponent(
  WidgetTester tester,
  Widget component, {
  required Size size,
  List<Override> overrides = const [],
  ThemeData? theme,
}) async {
  await _pump(
    tester,
    size: size,
    overrides: overrides,
    theme: theme,
    builder: (child) => Material(type: MaterialType.transparency, child: child),
    child: component,
  );
}

Future<void> _pump(
  WidgetTester tester, {
  required Size size,
  required List<Override> overrides,
  required ThemeData? theme,
  required Widget Function(Widget child) builder,
  required Widget child,
}) async {
  tester.view
    ..physicalSize = size * kGoldenPixelRatio
    ..devicePixelRatio = kGoldenPixelRatio;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(
    ProviderScope(
      overrides: overrides,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: theme ?? AppTheme.dark(),
        locale: const Locale('vi'),
        supportedLocales: const [Locale('vi')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        builder: (context, navigator) => builder(navigator!),
        home: child,
      ),
    ),
  );
  await tester.runAsync(() => Future<void>.delayed(Duration.zero));
  await tester.pumpAndSettle();
}

class _FigmaFrame extends StatelessWidget {
  const _FigmaFrame({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final content = Size(kFigmaFrameSize.width - 2, kFigmaFrameSize.height - 2);
    const padding = EdgeInsets.only(top: FakeStatusBar.height);
    return Container(
      decoration: BoxDecoration(
        color: c.bgBase,
        border: Border.all(color: c.lineSubtle),
        borderRadius: BorderRadius.circular(36),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(35),
        child: MediaQuery(
          data: MediaQuery.of(context).copyWith(
            size: content,
            padding: padding,
            viewPadding: padding,
            viewInsets: EdgeInsets.zero,
          ),
          child: Material(
            type: MaterialType.transparency,
            child: Stack(
              children: [
                Positioned.fill(child: child),
                const Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  child: FakeStatusBar(),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
