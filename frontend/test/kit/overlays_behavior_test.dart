import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/widgets/mp_banner.dart';
import 'package:mat_pho/core/widgets/mp_dialog.dart';
import 'package:mat_pho/core/widgets/mp_sheet.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';

import '../helpers/golden.dart';

Future<BuildContext> _pumpHost(WidgetTester tester) async {
  late BuildContext host;
  await pumpGoldenScreen(
    tester,
    Builder(
      builder: (context) {
        host = context;
        return const Scaffold();
      },
    ),
  );
  return host;
}

void main() {
  testWidgets('sheet moves in for 280 ms and closes from the scrim', (
    tester,
  ) async {
    final host = await _pumpHost(tester);
    var closed = false;
    showMpSheet<void>(
      host,
      builder: (_) => const MpSheet(title: 'Tiêu đề', children: []),
    ).then((_) => closed = true);

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 140));
    final midway = tester.getTopLeft(find.byType(MpSheet)).dy;
    await tester.pump(const Duration(milliseconds: 140));
    final open = tester.getTopLeft(find.byType(MpSheet)).dy;
    expect(midway, greaterThan(open));
    await tester.pump(const Duration(milliseconds: 50));
    expect(tester.getTopLeft(find.byType(MpSheet)).dy, open);
    expect(tester.getBottomLeft(find.byType(MpSheet)).dy, 778 + 1);

    await tester.tapAt(const Offset(180, 100));
    await tester.pump();
    await tester.pump(MpSheet.exitDuration + const Duration(milliseconds: 16));
    await tester.pump();
    expect(find.byType(MpSheet), findsNothing);
    expect(closed, isTrue);
  });

  testWidgets('dialog dissolves in 200 ms / out 150 ms and names its route', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    final host = await _pumpHost(tester);
    showMpDialog<void>(
      host,
      builder: (_) => const MpDialog(title: 'Đăng xuất?', body: 'Nội dung'),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    FadeTransition fade() => tester.widget<FadeTransition>(
      find
          .ancestor(
            of: find.byType(MpDialog),
            matching: find.byType(FadeTransition),
          )
          .first,
    );
    expect(fade().opacity.value, inExclusiveRange(0, 1));
    await tester.pump(const Duration(milliseconds: 100));
    expect(fade().opacity.value, 1);
    expect(
      tester.getSemantics(find.byType(MpDialog)),
      matchesSemantics(
        label: 'Đăng xuất?',
        scopesRoute: true,
        namesRoute: true,
      ),
    );
    expect(tester.getSize(find.byType(MpDialog)).width, MpDialog.width);
    expect(tester.getCenter(find.byType(MpDialog)).dx, 180);

    await tester.tapAt(const Offset(180, 60));
    await tester.pump();
    await tester.pump(MpDialog.exitDuration + const Duration(milliseconds: 16));
    await tester.pump();
    expect(find.byType(MpDialog), findsNothing);
    handle.dispose();
  });

  testWidgets('undo toast is a live region and leaves after 5 s', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    final host = await _pumpHost(tester);
    showMpToast(host, const MpToast(title: 'Đã báo nhầm · Hầm xe'));
    await tester.pump();
    await tester.pump(MpToast.enterDuration);
    expect(
      tester.getSemantics(find.byType(MpToast)),
      matchesSemantics(isLiveRegion: true, label: 'Đã báo nhầm · Hầm xe'),
    );
    final rect = tester.getRect(find.byType(MpToast));
    expect(rect.bottom, 1 + 778 - MpToast.defaultBottom);
    expect(rect.width, MpToast.maxWidth);
    expect(rect.center.dx, 180);

    await tester.pump(
      MpToast.undoDuration - MpToast.enterDuration - const Duration(seconds: 1),
    );
    expect(find.byType(MpToast), findsOneWidget);
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(MpToast.exitDuration + const Duration(milliseconds: 16));
    await tester.pump();
    expect(find.byType(MpToast), findsNothing);
    handle.dispose();
  });

  testWidgets('toast action runs and dismisses; a new toast replaces it', (
    tester,
  ) async {
    final host = await _pumpHost(tester);
    var undone = 0;
    showMpToast(
      host,
      MpToast(title: 'A', actionLabel: 'Hoàn tác', onAction: () => undone++),
      duration: MpToast.dismissedDuration,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hoàn tác'));
    await tester.pumpAndSettle();
    expect(undone, 1);
    expect(find.byType(MpToast), findsNothing);

    showMpToast(host, const MpToast(title: 'B'), duration: null);
    await tester.pumpAndSettle();
    showMpToast(host, const MpToast(title: 'C'), duration: null);
    await tester.pumpAndSettle();
    expect(find.text('B'), findsNothing);
    expect(find.text('C'), findsOneWidget);
    hideMpToast();
    await tester.pumpAndSettle();
    expect(find.byType(MpToast), findsNothing);
  });

  testWidgets('a toast dismissed twice (timer + hide) is removed once', (
    tester,
  ) async {
    final host = await _pumpHost(tester);
    showMpToast(host, const MpToast(title: 'A'));
    await tester.pumpAndSettle();
    hideMpToast();
    await tester.pump(MpToast.undoDuration);
    hideMpToast();
    await tester.pumpAndSettle();
    expect(find.byType(MpToast), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a toast that never reached the overlay is not removed later', (
    tester,
  ) async {
    late BuildContext orphan;
    await tester.pumpWidget(
      Builder(
        builder: (context) {
          orphan = context;
          return const SizedBox();
        },
      ),
    );
    expect(
      () => showMpToast(orphan, const MpToast(title: 'A')),
      throwsFlutterError,
    );
    hideMpToast();
    await tester.pump();

    final host = await _pumpHost(tester);
    showMpToast(host, const MpToast(title: 'B'), duration: null);
    await tester.pumpAndSettle();
    expect(find.text('B'), findsOneWidget);
    hideMpToast();
    await tester.pumpAndSettle();
    expect(find.byType(MpToast), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('alert banner slides down in 240 ms and leaves when tapped', (
    tester,
  ) async {
    final host = await _pumpHost(tester);
    var opened = 0;
    showMpAlertBanner(
      host,
      MpAlertBanner(title: 'Cháy · Hầm xe', onTap: () => opened++),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 120));
    final midway = tester.getTopLeft(find.byType(MpAlertBanner)).dy;
    await tester.pump(const Duration(milliseconds: 120));
    final rest = tester.getTopLeft(find.byType(MpAlertBanner));
    expect(midway, lessThan(rest.dy));
    expect(rest, const Offset(1 + 20, 1 + 40 + 12));

    await tester.tap(find.byType(MpAlertBanner));
    await tester.pumpAndSettle();
    expect(opened, 1);
    expect(find.byType(MpAlertBanner), findsNothing);
  });
}
