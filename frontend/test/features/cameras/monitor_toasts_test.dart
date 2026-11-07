import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/features/cameras/monitor_toasts.dart';

Future<void> _pumpCaller(
  WidgetTester tester,
  void Function(BuildContext context) show,
) async {
  addTearDown(hideMpToast);
  await tester.pumpWidget(
    ProviderScope(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(const FakeScenario.test()),
      ]),
      child: MaterialApp(
        theme: AppTheme.dark(),
        home: Builder(
          builder: (home) => Scaffold(
            body: TextButton(
              onPressed: () => Navigator.of(home).push(
                MaterialPageRoute<void>(
                  builder: (alert) => Scaffold(
                    body: TextButton(
                      onPressed: () {
                        show(alert);
                        Navigator.of(alert).pop();
                      },
                      child: const Text('act'),
                    ),
                  ),
                ),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('act'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('I16: "Đã xử lý · Hầm xe" with Hoàn tác', (tester) async {
    var undone = 0;
    await _pumpCaller(
      tester,
      (context) => showResolvedToast(context, onUndo: () => undone++),
    );
    expect(find.text('Đã xử lý · Hầm xe'), findsOneWidget);
    expect(find.text('act'), findsNothing);

    await tester.tap(find.text('Hoàn tác'));
    await tester.pumpAndSettle();
    expect(undone, 1);
    expect(find.text('Đã xử lý · Hầm xe'), findsNothing);
  });

  testWidgets('I16 without undo has no action', (tester) async {
    await _pumpCaller(tester, (context) => showResolvedToast(context));
    expect(find.text('Đã xử lý · Hầm xe'), findsOneWidget);
    expect(find.text('Hoàn tác'), findsNothing);
    await tester.pump(MpToast.undoDuration);
    await tester.pumpAndSettle();
  });

  testWidgets('I10: "Đã báo nhầm · Hầm xe", Hoàn tác for 5 s', (tester) async {
    var undone = 0;
    await _pumpCaller(
      tester,
      (context) => showFalseAlarmToast(context, onUndo: () => undone++),
    );
    expect(find.text('Đã báo nhầm · Hầm xe'), findsOneWidget);
    expect(find.text('Hoàn tác'), findsOneWidget);

    await tester.pump(MpToast.undoDuration);
    await tester.pumpAndSettle();
    expect(find.text('Đã báo nhầm · Hầm xe'), findsNothing);
    expect(undone, 0);
  });
}
