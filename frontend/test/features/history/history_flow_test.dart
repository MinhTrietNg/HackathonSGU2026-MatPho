import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/time_format.dart';
import 'package:mat_pho/core/widgets/mp_button.dart';
import 'package:mat_pho/data/errors.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/models/fire_event.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/repositories/history_repository.dart';
import 'package:mat_pho/features/history/history_routes.dart';
import 'package:mat_pho/features/history/history_screen.dart';
import 'package:mat_pho/features/history/history_state.dart';

class _ScriptedRepository implements HistoryRepository {
  _ScriptedRepository(this.onList, {this.onDetail});

  final Future<List<FireEvent>> Function(int call) onList;
  final Future<FireEvent> Function(int call)? onDetail;
  var calls = 0;
  var detailCalls = 0;

  @override
  Future<List<FireEvent>> list({HistoryFilter filter = HistoryFilter.all}) =>
      onList(calls++);

  @override
  Future<FireEvent> detail(String eventId) async =>
      await onDetail?.call(detailCalls++) ??
      FakeData.history().firstWhere((e) => e.id == eventId);
}

Future<GoRouter> _pump(
  WidgetTester tester, {
  Set<FakeCase> cases = const {},
  List<Override> overrides = const [],
  String initialLocation = AppRoutes.history,
}) async {
  tester.view
    ..physicalSize = const Size(360, 780)
    ..devicePixelRatio = 1;
  addTearDown(tester.view.reset);

  final router = GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: initialLocation,
    routes: [
      GoRoute(
        path: AppRoutes.history,
        builder: (_, _) => const HistoryScreen(),
        routes: historySubRoutes,
      ),
    ],
  );
  addTearDown(router.dispose);

  await tester.pumpWidget(
    ProviderScope(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(FakeScenario.test(cases: cases)),
        ...overrides,
      ]),
      child: MaterialApp.router(theme: AppTheme.dark(), routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
  return router;
}

Future<void> _settle(WidgetTester tester) async {
  await tester.pumpAndSettle();
  await tester.pump();
  await tester.pumpAndSettle();
}

const _rows = [
  'Lửa ở xe máy',
  'Đèn xe chiếu lên tường',
  'Khói mờ ở lối xuống',
  'Hơi nước từ ống xả',
];

void main() {
  testWidgets('G1 lists the last 30 days by day, newest first', (tester) async {
    await _pump(tester);

    for (final title in _rows) {
      expect(find.text(title), findsOneWidget);
    }
    final tops = [for (final t in _rows) tester.getTopLeft(find.text(t)).dy];
    expect(tops, orderedEquals([...tops]..sort()));

    expect(find.text('HÔM NAY'), findsOneWidget);
    expect(find.text('HÔM QUA'), findsOneWidget);
    final yesterday = tester.getTopLeft(find.text('HÔM QUA')).dy;
    expect(tops[1], lessThan(yesterday));
    expect(tops[2], greaterThan(yesterday));

    expect(find.text('Hầm xe · 21:47 · đã gọi 114'), findsOneWidget);
    expect(find.text('Hầm xe · 21:40'), findsOneWidget);
    expect(find.text('Cháy'), findsNWidgets(2));
    expect(find.text('Không cháy'), findsNWidgets(2));
    expect(find.text('Chưa chắc chắn'), findsOneWidget);
    expect(find.text('Báo nhầm'), findsNWidgets(2));
    expect(find.text('Đã hiện hết · 30 ngày gần nhất'), findsOneWidget);
  });

  testWidgets('filter chips narrow the list and say what is filtered', (
    tester,
  ) async {
    await _pump(tester);

    await tester.tap(find.text('Không cháy').first);
    await _settle(tester);
    expect(find.text('Đèn xe chiếu lên tường'), findsOneWidget);
    expect(find.text('Lửa ở xe máy'), findsNothing);
    expect(find.text('Hơi nước từ ống xả'), findsNothing);
    expect(
      find.text('Đang lọc “Không cháy” · 30 ngày gần nhất'),
      findsOneWidget,
    );

    await tester.tap(find.text('Báo nhầm').first);
    await _settle(tester);
    expect(find.text('Hơi nước từ ống xả'), findsOneWidget);
    expect(find.text('HÔM QUA'), findsOneWidget);
    expect(find.text('HÔM NAY'), findsNothing);

    await tester.tap(find.text('Cháy').first);
    await _settle(tester);
    expect(find.text('Lửa ở xe máy'), findsOneWidget);
    expect(find.text('Đang lọc “Cháy” · 30 ngày gần nhất'), findsOneWidget);

    await tester.tap(find.text('Tất cả'));
    await _settle(tester);
    for (final title in _rows) {
      expect(find.text(title), findsOneWidget);
    }
  });

  testWidgets('a row opens its detail without the tab bar, back returns', (
    tester,
  ) async {
    final router = await _pump(tester);

    await tester.tap(find.text('Đèn xe chiếu lên tường'));
    await _settle(tester);
    expect(router.state.uri.path, AppRoutes.historyDetail('evt-dismissed'));
    expect(find.byType(HistoryScreen), findsNothing);
    expect(find.text('Chi tiết'), findsOneWidget);
    expect(find.text('HẦM XE · 23/10/2025 21:40:12'), findsOneWidget);
    expect(find.text('23/10 · 21:40:12'), findsOneWidget);
    expect(
      find.text('AI kiểm tra lại 2 lần, không thấy khói hay lửa.'),
      findsOneWidget,
    );
    expect(find.text('Xác nhận không cháy'), findsOneWidget);
    expect(find.text('+4,6 s'), findsOneWidget);
    expect(find.text('Không báo'), findsOneWidget);
    expect(find.text('—'), findsOneWidget);
    expect(find.byType(MpButton), findsNothing);
    expect(find.textContaining('Báo sau'), findsNothing);

    await tester.tap(find.bySemanticsLabel('Quay lại'));
    await _settle(tester);
    expect(router.state.uri.path, AppRoutes.history);
    expect(find.text('Lửa ở xe máy'), findsOneWidget);
  });

  testWidgets('G4 times every step and proves the under-10 s goal', (
    tester,
  ) async {
    await _pump(tester, initialLocation: AppRoutes.historyDetail('evt-fire'));

    expect(find.text('HẦM XE · 23/10/2025 21:47:31'), findsOneWidget);
    expect(find.text('23/10 · 21:47:31'), findsOneWidget);
    const steps = [
      ('Máy phát hiện', '0,0 s'),
      ('Gửi ảnh', '+0,4 s'),
      ('Xác nhận cháy', '+5,1 s'),
      ('Báo tới điện thoại', '+6,8 s'),
    ];
    for (final (label, value) in steps) {
      expect(find.text(label), findsOneWidget);
      expect(find.text(value), findsOneWidget);
    }
    expect(find.text('Báo sau 6,8 giây'), findsOneWidget);
    expect(find.text('Bạn bấm gọi 114'), findsNothing);
    expect(find.text('Lửa và khói ở xe máy bên trái'), findsNothing);
  });

  testWidgets('G3 when nothing happened: reassuring, no chips', (tester) async {
    await _pump(tester, cases: {FakeCase.historyEmpty});

    expect(find.text('Chưa có gì xảy ra'), findsOneWidget);
    expect(find.text('Các lần báo cháy sẽ hiện ở đây.'), findsOneWidget);
    expect(find.text('Tất cả'), findsNothing);
    expect(find.text('Thử lại'), findsNothing);
  });

  testWidgets('G2 skeleton keeps the layout, G8 after 8 s without answer', (
    tester,
  ) async {
    final hanging = Completer<List<FireEvent>>();
    await _pump(
      tester,
      overrides: [
        historyRepositoryProvider.overrideWithValue(
          _ScriptedRepository((_) => hanging.future),
        ),
      ],
    );

    expect(find.text('Tất cả'), findsOneWidget);
    expect(find.text('Lửa ở xe máy'), findsNothing);
    expect(find.text('Không tải được'), findsNothing);

    await tester.pump(historyLoadTimeout - const Duration(seconds: 1));
    expect(find.text('Không tải được'), findsNothing);

    await tester.pump(const Duration(seconds: 1));
    await _settle(tester);
    expect(find.text('Không tải được'), findsOneWidget);
    expect(find.text('Báo cháy vẫn hoạt động bình thường.'), findsOneWidget);
    expect(find.text('Tất cả'), findsNothing);
  });

  testWidgets('G8 tells a lost connection from a server error', (tester) async {
    await _pump(tester, cases: {FakeCase.historyNetworkError});
    expect(find.text('Không tải được'), findsOneWidget);
    expect(find.text('Kiểm tra kết nối rồi thử lại.'), findsOneWidget);
    expect(find.text('Báo cháy vẫn hoạt động bình thường.'), findsNothing);
  });

  testWidgets('G8 server variant', (tester) async {
    await _pump(tester, cases: {FakeCase.historyServerError});
    expect(find.text('Không tải được'), findsOneWidget);
    expect(find.text('Báo cháy vẫn hoạt động bình thường.'), findsOneWidget);
    expect(find.text('Kiểm tra kết nối rồi thử lại.'), findsNothing);
  });

  testWidgets('"Thử lại" keeps G8 on screen while it reloads, then G1', (
    tester,
  ) async {
    final retries = <Completer<List<FireEvent>>>[];
    final repository = _ScriptedRepository((call) {
      if (call == 0) return Future.error(const NetworkException());
      final retry = Completer<List<FireEvent>>();
      retries.add(retry);
      return retry.future;
    });
    await _pump(
      tester,
      overrides: [historyRepositoryProvider.overrideWithValue(repository)],
    );
    expect(find.text('Không tải được'), findsOneWidget);
    final button = find.byType(MpButton);
    bool busy() => tester.widget<MpButton>(button).busy;
    expect(busy(), isFalse);

    await tester.tap(button);
    await tester.pump();
    expect(repository.calls, 2);
    expect(find.text('Không tải được'), findsOneWidget);
    expect(find.text('Tất cả'), findsNothing);
    expect(busy(), isTrue);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.tap(button, warnIfMissed: false);
    await tester.pump();
    expect(repository.calls, 2);

    retries[0].completeError(const NetworkException());
    await tester.pump();
    await tester.pump();
    expect(find.text('Không tải được'), findsOneWidget);
    expect(find.text('Kiểm tra kết nối rồi thử lại.'), findsOneWidget);
    expect(busy(), isFalse);
    expect(find.byType(CircularProgressIndicator), findsNothing);

    await tester.tap(button);
    await tester.pump();
    expect(repository.calls, 3);
    expect(find.text('Không tải được'), findsOneWidget);
    expect(busy(), isTrue);

    retries[1].complete(FakeData.history());
    await _settle(tester);
    expect(find.text('Không tải được'), findsNothing);
    expect(find.text('Lửa ở xe máy'), findsOneWidget);
  });

  testWidgets('"Thử lại" on the detail keeps G8 on screen while it reloads', (
    tester,
  ) async {
    final retry = Completer<FireEvent>();
    final repository = _ScriptedRepository(
      (_) => Future.value(FakeData.history()),
      onDetail: (call) =>
          call == 0 ? Future.error(const ServerException()) : retry.future,
    );
    await _pump(
      tester,
      initialLocation: AppRoutes.historyDetail('evt-fire'),
      overrides: [historyRepositoryProvider.overrideWithValue(repository)],
    );
    expect(find.text('Không tải được'), findsOneWidget);

    await tester.tap(find.byType(MpButton));
    await tester.pump();
    expect(repository.detailCalls, 2);
    expect(find.text('Không tải được'), findsOneWidget);
    expect(tester.widget<MpButton>(find.byType(MpButton)).busy, isTrue);

    retry.complete(FakeData.history().firstWhere((e) => e.id == 'evt-fire'));
    await _settle(tester);
    expect(find.text('Không tải được'), findsNothing);
    expect(find.text('23/10 · 21:47:31'), findsOneWidget);
  });

  testWidgets('a reload keeps the rows on screen until it answers', (
    tester,
  ) async {
    final second = Completer<List<FireEvent>>();
    final repository = _ScriptedRepository(
      (call) => call == 0 ? Future.value(FakeData.history()) : second.future,
    );
    await _pump(
      tester,
      overrides: [historyRepositoryProvider.overrideWithValue(repository)],
    );
    expect(find.text('Lửa ở xe máy'), findsOneWidget);

    ProviderScope.containerOf(
      tester.element(find.byType(HistoryScreen)),
    ).invalidate(historyListProvider);
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(repository.calls, 2);
    for (final title in _rows) {
      expect(find.text(title), findsOneWidget);
    }
    expect(find.text('Đã hiện hết · 30 ngày gần nhất'), findsOneWidget);

    second.complete(FakeData.history().take(1).toList());
    await _settle(tester);
    expect(find.text('Lửa ở xe máy'), findsOneWidget);
    expect(find.text('Hơi nước từ ống xả'), findsNothing);
  });

  testWidgets('a filter not loaded yet keeps the last list until it answers', (
    tester,
  ) async {
    final filtered = Completer<List<FireEvent>>();
    final repository = _ScriptedRepository(
      (call) => call == 0 ? Future.value(FakeData.history()) : filtered.future,
    );
    await _pump(
      tester,
      overrides: [historyRepositoryProvider.overrideWithValue(repository)],
    );

    await tester.tap(find.text('Không cháy').first);
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(repository.calls, 2);
    expect(find.text('Lửa ở xe máy'), findsOneWidget);
    expect(find.text('Đã hiện hết · 30 ngày gần nhất'), findsOneWidget);

    filtered.complete([
      for (final e in FakeData.history())
        if (e.status == EventStatus.dismissed) e,
    ]);
    await _settle(tester);
    expect(find.text('Lửa ở xe máy'), findsNothing);
    expect(find.text('Đèn xe chiếu lên tường'), findsOneWidget);
    expect(
      find.text('Đang lọc “Không cháy” · 30 ngày gần nhất'),
      findsOneWidget,
    );
  });

  testWidgets('a failed reload keeps the rows already on the device', (
    tester,
  ) async {
    final repository = _ScriptedRepository(
      (call) => call == 0
          ? Future.value(FakeData.history())
          : Future.error(const ServerException()),
    );
    await _pump(
      tester,
      overrides: [historyRepositoryProvider.overrideWithValue(repository)],
    );
    expect(find.text('Lửa ở xe máy'), findsOneWidget);

    ProviderScope.containerOf(
      tester.element(find.byType(HistoryScreen)),
    ).invalidate(historyListProvider);
    await _settle(tester);
    expect(repository.calls, 2);
    expect(find.text('Lửa ở xe máy'), findsOneWidget);
    expect(find.text('Không tải được'), findsNothing);
  });

  testWidgets('coming back to the tab reloads in place', (tester) async {
    final repository = _ScriptedRepository(
      (_) => Future.value(FakeData.history()),
    );
    final active = ValueNotifier(true);
    addTearDown(active.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: fakeOverrides([
          historyRepositoryProvider.overrideWithValue(repository),
        ]),
        child: MaterialApp(
          theme: AppTheme.dark(),
          home: ValueListenableBuilder(
            valueListenable: active,
            builder: (_, enabled, _) =>
                TickerMode(enabled: enabled, child: const HistoryScreen()),
          ),
        ),
      ),
    );
    await _settle(tester);
    expect(repository.calls, 1);

    active.value = false;
    await _settle(tester);
    expect(repository.calls, 1);

    active.value = true;
    await _settle(tester);
    expect(repository.calls, 2);
    expect(find.text('Lửa ở xe máy'), findsOneWidget);
  });

  test('step offsets: one decimal under 10 s, whole seconds above', () {
    expect(formatStepSeconds(Duration.zero), '0,0');
    expect(formatStepSeconds(const Duration(milliseconds: 400)), '0,4');
    expect(formatStepSeconds(const Duration(milliseconds: 6800)), '6,8');
    expect(formatStepSeconds(const Duration(seconds: 31)), '31');
  });
}
