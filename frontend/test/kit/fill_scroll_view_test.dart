import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/app.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_fill_scroll_view.dart';
import 'package:mat_pho/core/widgets/mp_page.dart';

Future<void> _pump(WidgetTester tester, Widget home, {bool stock = false}) =>
    tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.dark(),
        scrollBehavior: stock ? null : MatPhoApp.scrollBehavior,
        home: home,
      ),
    );

Future<Offset> _dragDown(WidgetTester tester, String text) async {
  final before = tester.getTopLeft(find.text(text));
  final gesture = await tester.startGesture(tester.getCenter(find.text(text)));
  await gesture.moveBy(const Offset(0, 200));
  await tester.pump();
  final moved = tester.getTopLeft(find.text(text)) - before;
  await gesture.up();
  await tester.pumpAndSettle();
  return moved;
}

void main() {
  const fullPage = MpPage(
    children: [Text('Đăng nhập'), Spacer(), Text('cuối')],
  );

  testWidgets('the stock Android behavior stretches a page that fits', (
    tester,
  ) async {
    expect(defaultTargetPlatform, TargetPlatform.android);
    await _pump(tester, fullPage, stock: true);
    expect(find.byType(StretchingOverscrollIndicator), findsOneWidget);
  });

  testWidgets('a full page that fits does not stretch when dragged', (
    tester,
  ) async {
    await _pump(tester, fullPage);
    expect(find.byType(MpFillScrollView), findsOneWidget);
    expect(find.byType(StretchingOverscrollIndicator), findsNothing);
    expect(find.byType(GlowingOverscrollIndicator), findsNothing);
    expect(await _dragDown(tester, 'Đăng nhập'), Offset.zero);
  });

  testWidgets('a plain list (e.g. H1) does not stretch at its ends either', (
    tester,
  ) async {
    await _pump(
      tester,
      Scaffold(
        body: ListView(
          children: [for (var i = 0; i < 40; i++) Text('hàng $i')],
        ),
      ),
    );
    expect(find.byType(StretchingOverscrollIndicator), findsNothing);
    expect(find.byType(GlowingOverscrollIndicator), findsNothing);
    expect(await _dragDown(tester, 'hàng 0'), Offset.zero);
  });

  testWidgets('content that does not fit (keyboard open) still scrolls', (
    tester,
  ) async {
    await _pump(
      tester,
      const Scaffold(
        body: MpFillScrollView(
          child: Column(
            children: [Text('đầu'), SizedBox(height: 2000), Text('cuối')],
          ),
        ),
      ),
    );
    await tester.drag(find.text('đầu'), const Offset(0, -300));
    await tester.pumpAndSettle();
    final scrollable = tester.state<ScrollableState>(find.byType(Scrollable));
    expect(scrollable.position.pixels, greaterThan(0));
  });
}
