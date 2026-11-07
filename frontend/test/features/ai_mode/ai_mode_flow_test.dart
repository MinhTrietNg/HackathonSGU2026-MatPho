import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_button.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/features/ai_mode/ai_mode_routes.dart';
import 'package:mat_pho/features/ai_mode/ai_mode_state.dart';
import 'package:mat_pho/features/ai_mode/ai_mode_widgets.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/groups/current_group.dart';
import 'package:mat_pho/features/settings/settings_routes.dart';
import 'package:mat_pho/features/settings/settings_screen.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_scenario.dart';

class _SignedIn extends AuthSessionNotifier {
  @override
  AuthSession build() => const SignedIn(FakeData.user);
}

class _Selected extends CurrentGroup {
  _Selected(this.groupId);

  final String groupId;

  @override
  String? build() => groupId;
}

Future<ProviderContainer> _pump(
  WidgetTester tester, {
  String initial = AiModeRoutes.cameras,
  String? groupId,
  Set<FakeCase> cases = const {},
}) async {
  tester.view
    ..physicalSize = const Size(360, 780) * 2
    ..devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  addTearDown(hideMpToast);
  final container = ProviderContainer(
    overrides: fakeOverrides([
      fakeScenarioProvider.overrideWithValue(FakeScenario.test(cases: cases)),
      authSessionProvider.overrideWith(_SignedIn.new),
      if (groupId != null)
        currentGroupIdProvider.overrideWith(() => _Selected(groupId)),
    ]),
  );
  addTearDown(container.dispose);
  final router = GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: initial,
    routes: [
      GoRoute(
        path: AppRoutes.settings,
        builder: (_, _) => const SettingsScreen(),
        routes: [...settingsSubRoutes, ...aiModeSubRoutes],
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: MaterialApp.router(
        theme: AppTheme.dark(),
        locale: const Locale('vi'),
        supportedLocales: const [Locale('vi')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        routerConfig: router,
      ),
    ),
  );
  await _settle(tester);
  return container;
}

Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 3; i++) {
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
  }
}

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await _settle(tester);
}

Finder _button(String label) => find.widgetWithText(MpButton, label);

bool _enabled(WidgetTester tester, String label) =>
    tester.widget<MpButton>(_button(label)).onPressed != null;

Finder _day(String label) =>
    find.byWidgetPredicate((w) => w is AiDayChip && w.label == label);

Finder _field(String label) => find.descendant(
  of: find.bySemanticsLabel(label),
  matching: find.byType(TextField),
);

TextField _textField(WidgetTester tester, String label, {int at = 0}) =>
    tester.widget<TextField>(_field(label).at(at));

String _time(WidgetTester tester, String label) =>
    '${_text(tester, '$label, giờ')}:${_text(tester, '$label, phút')}';

bool _focused(WidgetTester tester, String label) =>
    _textField(tester, label).focusNode!.hasFocus;

String _text(WidgetTester tester, String label) =>
    _textField(tester, label).controller!.text;

bool _dayOn(WidgetTester tester, String label) =>
    tester.widget<AiDayChip>(_day(label)).on;

CameraAi _aiOf(ProviderContainer container, String cameraId) => container
    .read(fakeWorldProvider)
    .cameras
    .firstWhere((c) => c.id == cameraId)
    .ai;

const _always = 'AI luôn bật · báo cháy 24/7';
const _cooking = 'Nghỉ AI 17:00–19:30 · mỗi ngày';

void main() {
  testWidgets('H1 › "AI nhận diện cháy" opens the camera list (H7)', (
    tester,
  ) async {
    await _pump(tester, initial: AppRoutes.settings);
    expect(find.text('Bật/tắt theo từng camera'), findsOneWidget);

    await _tap(tester, find.text('AI nhận diện cháy'));
    expect(find.text('camera đã kết nối'), findsOneWidget);
  });

  group('H7–H9 · AI theo camera', () {
    testWidgets('owner: each camera shows its AI mode and opens H10', (
      tester,
    ) async {
      await _pump(tester, groupId: FakeData.home.id);
      expect(find.text('3'), findsOneWidget);
      expect(find.text('Nhà mình · bạn là chủ nhóm'), findsOneWidget);
      expect(find.text('CAMERA · 3'), findsOneWidget);
      expect(find.text(_always), findsNWidgets(2));
      expect(find.text(_cooking), findsOneWidget);
      expect(find.text('Chỉ chủ nhóm được đổi cài đặt AI'), findsNothing);

      await _tap(tester, find.text('Bếp'));
      expect(find.text('NHÀ MÌNH · AI NHẬN DIỆN CHÁY'), findsOneWidget);
    });

    testWidgets('the chips switch groups; a member sees a lock, no link', (
      tester,
    ) async {
      await _pump(tester, groupId: FakeData.home.id);
      await _tap(tester, find.text('Văn phòng công ty'));

      expect(
        find.text('Văn phòng công ty · bạn là thành viên'),
        findsOneWidget,
      );
      expect(find.text('Chỉ chủ nhóm được đổi cài đặt AI'), findsOneWidget);
      expect(find.text('Muốn đổi, nhắn Anh Long (chủ nhóm).'), findsOneWidget);
      expect(find.text('Chạm vào camera', findRichText: true), findsNothing);

      await _tap(tester, find.text('Kho hàng'));
      expect(find.text('Muốn đổi, nhắn Anh Long (chủ nhóm).'), findsOneWidget);
      expect(find.text('Luôn bật AI'), findsNothing);
    });

    testWidgets('the current group is picked first', (tester) async {
      await _pump(tester, groupId: FakeData.skyGarden.id);
      expect(
        find.text('Chung cư Sky Garden · bạn là chủ nhóm'),
        findsOneWidget,
      );
      expect(find.text('Khu sạc xe'), findsOneWidget);
    });
  });

  group('H10–H15 · chế độ AI của một camera', () {
    testWidgets('a scheduled camera shows its window and every day on', (
      tester,
    ) async {
      await _pump(tester, initial: AiModeRoutes.camera('cam-kitchen'));
      expect(find.text('Bếp'), findsOneWidget);
      expect(_time(tester, 'Từ'), '17:00');
      expect(_time(tester, 'Đến'), '19:30');
      for (final day in weekdayLabels.values) {
        expect(_dayOn(tester, day), isTrue, reason: day);
      }
      expect(find.text('KHUNG GIỜ 1'), findsNothing);
      expect(find.text(aiOffWarning), findsNothing);
    });

    testWidgets('"Tắt hẳn AI" warns, saves, and the list says so', (
      tester,
    ) async {
      final container = await _pump(tester, groupId: FakeData.home.id);
      await _tap(tester, find.text('Phòng khách'));

      await _tap(tester, find.text('Tắt hẳn AI'));
      expect(find.text(aiOffWarning), findsOneWidget);

      await _tap(tester, _button('Lưu'));
      expect(_aiOf(container, 'cam-living'), CameraAi.off);
      expect(find.text('camera đã kết nối'), findsOneWidget);
      expect(find.text('Đã tắt AI · không báo cháy'), findsOneWidget);
    });

    testWidgets('picking "Nghỉ AI theo giờ" starts at 17:00–19:30', (
      tester,
    ) async {
      final container = await _pump(
        tester,
        initial: AiModeRoutes.camera('cam-living'),
      );
      expect(_field('Từ, giờ'), findsNothing);

      await _tap(tester, find.text('Nghỉ AI theo giờ'));
      expect(_time(tester, 'Từ'), '17:00');
      expect(_time(tester, 'Đến'), '19:30');

      await _tap(tester, _day('T2'));
      expect(_dayOn(tester, 'T2'), isFalse);

      await _tap(tester, _button('Lưu'));
      expect(
        _aiOf(container, 'cam-living'),
        const CameraAi(
          mode: AiMode.scheduled,
          pauses: [
            AiPause(from: 17 * 60, to: 19 * 60 + 30, days: {2, 3, 4, 5, 6, 7}),
          ],
        ),
      );
    });

    testWidgets('a second window can be added and removed', (tester) async {
      await _pump(tester, initial: AiModeRoutes.camera('cam-kitchen'));

      await _tap(tester, find.text('+ Thêm khung giờ'));
      expect(find.text('KHUNG GIỜ 1'), findsOneWidget);
      expect(find.text('KHUNG GIỜ 2'), findsOneWidget);
      expect(_textField(tester, 'Từ, giờ', at: 1).controller!.text, '11');
      expect(find.bySemanticsLabel('Xoá khung giờ 1'), findsNothing);

      await _tap(tester, find.bySemanticsLabel('Xoá khung giờ 2'));
      expect(find.text('KHUNG GIỜ 2'), findsNothing);
      expect(_field('Từ, giờ'), findsOneWidget);
    });

    testWidgets('five windows at most: the add action hides, then returns', (
      tester,
    ) async {
      await _pump(tester, initial: AiModeRoutes.camera('cam-kitchen'));

      for (var i = 1; i < maxAiPauses; i++) {
        await _tap(tester, find.text('+ Thêm khung giờ'));
      }
      expect(find.text('KHUNG GIỜ 5'), findsOneWidget);
      expect(find.text('+ Thêm khung giờ'), findsNothing);

      await _tap(tester, find.bySemanticsLabel('Xoá khung giờ 5'));
      expect(find.text('KHUNG GIỜ 5'), findsNothing);
      expect(find.text('+ Thêm khung giờ'), findsOneWidget);
    });

    testWidgets('no day picked: "Lưu" is off', (tester) async {
      await _pump(tester, initial: AiModeRoutes.camera('cam-kitchen'));
      expect(_enabled(tester, 'Lưu'), isTrue);
      for (final day in weekdayLabels.values) {
        await _tap(tester, _day(day));
      }
      expect(_enabled(tester, 'Lưu'), isFalse);

      await _tap(tester, _day('CN'));
      expect(_enabled(tester, 'Lưu'), isTrue);
    });

    testWidgets('back to "Luôn bật AI" drops the schedule', (tester) async {
      final container = await _pump(
        tester,
        initial: AiModeRoutes.camera('cam-kitchen'),
      );
      await _tap(tester, find.text('Luôn bật AI'));
      expect(_field('Từ, giờ'), findsNothing);

      await _tap(tester, _button('Lưu'));
      expect(_aiOf(container, 'cam-kitchen'), CameraAi.alwaysOn);
    });

    testWidgets('times are typed in place: hour, then it jumps to minutes', (
      tester,
    ) async {
      final container = await _pump(
        tester,
        initial: AiModeRoutes.camera('cam-kitchen'),
      );
      expect(find.byType(TimePickerDialog), findsNothing);

      await _tap(tester, _field('Từ, giờ'));
      await tester.enterText(_field('Từ, giờ'), '06');
      await _settle(tester);
      expect(_focused(tester, 'Từ, phút'), isTrue);

      await tester.enterText(_field('Từ, phút'), '45');
      await _settle(tester);
      expect(_focused(tester, 'Từ, phút'), isFalse);

      await _tap(tester, _button('Lưu'));
      expect(
        _aiOf(container, 'cam-kitchen'),
        const CameraAi(
          mode: AiMode.scheduled,
          pauses: [AiPause(from: 6 * 60 + 45, to: 19 * 60 + 30)],
        ),
      );
    });

    testWidgets('an impossible time goes back to the last one', (tester) async {
      await _pump(tester, initial: AiModeRoutes.camera('cam-kitchen'));

      await _tap(tester, _field('Đến, giờ'));
      await tester.enterText(_field('Đến, giờ'), '25');
      await _settle(tester);
      expect(_focused(tester, 'Đến, giờ'), isTrue);

      FocusManager.instance.primaryFocus?.unfocus();
      await _settle(tester);
      expect(_text(tester, 'Đến, giờ'), '19');

      await _tap(tester, _field('Đến, phút'));
      await tester.enterText(_field('Đến, phút'), '7');
      FocusManager.instance.primaryFocus?.unfocus();
      await _settle(tester);
      expect(_text(tester, 'Đến, phút'), '07');
    });

    testWidgets('saving fails: a toast, the screen stays', (tester) async {
      final container = await _pump(
        tester,
        initial: AiModeRoutes.camera('cam-living'),
        cases: const {FakeCase.cameraUpdateFails},
      );
      await _tap(tester, find.text('Tắt hẳn AI'));
      await _tap(tester, _button('Lưu'));

      expect(
        find.text('Máy chủ đang bận. Thử lại sau ít phút.'),
        findsOneWidget,
      );
      expect(find.text(aiOffWarning), findsOneWidget);
      expect(_enabled(tester, 'Lưu'), isTrue);
      expect(_aiOf(container, 'cam-living'), CameraAi.alwaysOn);
      await tester.pump(const Duration(seconds: 5));
    });
  });

  group('aiModeSummary', () {
    test('always on, scheduled, off and off as seen by a member', () {
      expect(aiModeSummary(CameraAi.alwaysOn), _always);
      expect(aiModeSummary(FakeData.cookingPause), _cooking);
      expect(aiModeSummary(CameraAi.off), 'Đã tắt AI · không báo cháy');
      expect(aiModeSummary(CameraAi.off, locked: true), 'Chủ nhóm đã tắt AI');
    });

    test('more than one window: the first one, then how many more', () {
      const ai = CameraAi(
        mode: AiMode.scheduled,
        pauses: [defaultAiPause, extraAiPause],
      );
      expect(aiModeSummary(ai), '$_cooking · +1 khung');
    });

    test('formatAiDays: every day, weekend, weekdays, else T2 → CN', () {
      expect(formatAiDays(AiPause.everyDay), 'mỗi ngày');
      expect(formatAiDays({7, 6}), 'cuối tuần');
      expect(formatAiDays({1, 2, 3, 4, 5}), 'ngày thường');
      expect(formatAiDays({7, 1, 3}), 'T2, T4, CN');
      expect(formatAiDays({5}), 'T6');
    });

    test('formatClock pads hours and minutes', () {
      expect(formatClock(0), '00:00');
      expect(formatClock(9 * 60 + 5), '09:05');
      expect(formatClock(23 * 60 + 59), '23:59');
    });
  });
}
