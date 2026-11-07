import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_button.dart';
import 'package:mat_pho/core/widgets/mp_duotone_icon.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import 'package:mat_pho/core/widgets/mp_toggle.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_scenario.dart';
import '../../fakes/fake_world.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/groups/current_group.dart';
import 'package:mat_pho/features/groups/group_routes.dart';
import 'package:mat_pho/features/groups/group_state.dart'
    show
        currentGroupViewProvider,
        groupActionsProvider,
        invitationRowSubtitle,
        shortGroupName;
import 'package:mat_pho/features/groups/group_widgets.dart';
import 'package:mat_pho/features/groups/invite_member_screen.dart'
    show alreadyInGroupHint, notRegisteredHint;
import 'package:mat_pho/features/groups/member_access_screen.dart';
import 'package:mat_pho/features/groups/members_screen.dart';

const _settingsStub = 'SETTINGS';
const _monitorStub = 'MONITOR';

class _SignedIn extends AuthSessionNotifier {
  @override
  AuthSession build() => const SignedIn(FakeData.user);
}

Future<ProviderContainer> _pump(
  WidgetTester tester, {
  required String initial,
  String? groupId,
  List<Override> overrides = const [],
  FakeScenario scenario = const FakeScenario.test(),
}) async {
  tester.view
    ..physicalSize = const Size(360, 780) * 2
    ..devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  addTearDown(hideMpToast);
  final container = ProviderContainer(
    overrides: fakeOverrides([
      fakeScenarioProvider.overrideWithValue(scenario),
      authSessionProvider.overrideWith(_SignedIn.new),
      ...overrides,
    ]),
  );
  addTearDown(container.dispose);
  if (groupId != null) {
    container.read(currentGroupIdProvider.notifier).select(groupId);
  }
  Widget stub(String text) => Scaffold(body: Center(child: Text(text)));
  final router = GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: initial,
    routes: [
      GoRoute(
        path: AppRoutes.settings,
        builder: (_, _) => stub(_settingsStub),
        routes: groupSubRoutes,
      ),
      GoRoute(path: AppRoutes.monitor, builder: (_, _) => stub(_monitorStub)),
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

Finder _button(String label) => find.widgetWithText(MpButton, label).last;

List<Member> _members(ProviderContainer c, String groupId) =>
    c.read(fakeWorldProvider).members[groupId] ?? const [];

List<Group> _groups(ProviderContainer c) => c.read(fakeWorldProvider).groups;

// Every repository call waits 400 ms, so a group's data is still on its way
// for a while after it is picked.
const _slow = FakeScenario(freezeClock: true);

Finder _onMembers(String text) =>
    find.descendant(of: find.byType(MembersScreen), matching: find.text(text));

const _joinedElsewhere = Group(
  id: 'g-hi',
  name: 'hi',
  myRole: GroupRole.manager,
  myNickname: 'tai',
  cameraCount: 0,
  memberCount: 2,
);

final _waiting = fakeWorldProvider.overrideWith((ref) {
  final world = FakeWorld(ref.watch(fakeScenarioProvider));
  ref.onDispose(world.dispose);
  world.invitationsWaiting.add(FakeData.invitation);
  return world;
});

final _managerOfSky = fakeWorldProvider.overrideWith((ref) {
  final world = FakeWorld(ref.watch(fakeScenarioProvider));
  ref.onDispose(world.dispose);
  world.replaceGroup(
    const Group(
      id: 'g-sky',
      name: 'Chung cư Sky Garden',
      myRole: GroupRole.manager,
      myNickname: 'Minh Anh',
      cameraCount: 5,
      memberCount: 4,
    ),
  );
  world.members['g-sky'] = [
    for (final m in world.members['g-sky']!)
      m.isYou ? m.copyWith(role: GroupRole.manager, allCameras: true) : m,
  ];
  return world;
});

void main() {
  group('J1 / J6 / J13 · members per role', () {
    testWidgets('owner (J1): members, invite and dissolve', (tester) async {
      await _pump(tester, initial: GroupRoutes.members);
      expect(find.text('Chung cư Sky Garden'), findsOneWidget);
      expect(find.text('Minh Anh (bạn)'), findsOneWidget);
      expect(find.text('Quản lý toà nhà'), findsOneWidget);
      expect(find.text('Trần Anh Tuấn · Hầm B1, B2'), findsOneWidget);
      expect(find.text('0903 ••• 112'), findsOneWidget);
      expect(find.text('Bảo vệ ca đêm · mời 10 phút trước'), findsOneWidget);
      expect(find.text('Chờ đồng ý'), findsOneWidget);
      expect(_button('Mời thành viên'), findsOneWidget);
      expect(_button('Giải tán nhóm'), findsOneWidget);
      expect(find.text(groupPermissionNote), findsNothing);
    });

    testWidgets('rows that open J4 end with a chevron', (tester) async {
      await _pump(tester, initial: GroupRoutes.members);
      Finder chevronIn(String name) => find.descendant(
        of: find.ancestor(
          of: find.text(name),
          matching: find.byType(GroupMemberCard),
        ),
        matching: find.byType(MpChevron),
      );
      expect(chevronIn('Phạm Thị Lan'), findsOneWidget);
      expect(chevronIn('Chú Tuấn bảo vệ'), findsOneWidget);
      expect(chevronIn('Minh Anh (bạn)'), findsNothing);
      expect(chevronIn('0903 ••• 112'), findsNothing);
    });

    testWidgets('family (J6): roles and access lines', (tester) async {
      await _pump(tester, initial: GroupRoutes.members, groupId: 'g-home');
      expect(find.text('Ba (bạn)'), findsOneWidget);
      expect(find.text('Mọi camera · được mời người'), findsOneWidget);
      expect(find.text('Nhận báo cháy 3 camera'), findsOneWidget);
      expect(find.text('Chỉ camera phòng khách'), findsOneWidget);
      expect(find.text('Chỉ báo cháy'), findsOneWidget);
    });

    testWidgets('member (J13): read-only, the rule, "Rời nhóm"', (
      tester,
    ) async {
      await _pump(tester, initial: GroupRoutes.members, groupId: 'g-office');
      expect(find.text('Minh Anh (bạn)'), findsOneWidget);
      expect(find.text('Xem 2 camera: Kho hàng, Cửa sau'), findsOneWidget);
      expect(find.text(groupPermissionNote), findsOneWidget);
      expect(find.byType(MpChevron), findsNothing);
      expect(_button('Rời nhóm'), findsOneWidget);
      expect(find.widgetWithText(MpButton, 'Mời thành viên'), findsNothing);
      expect(find.widgetWithText(MpButton, 'Giải tán nhóm'), findsNothing);
      await _tap(tester, find.text('Chị Mai'));
      expect(find.text('TÊN TRONG NHÓM'), findsNothing);
    });
  });

  group('J2 · Mời thành viên', () {
    testWidgets('a wrong number is refused inline', (tester) async {
      await _pump(tester, initial: GroupRoutes.invite);
      expect(find.text('Mời vào Sky Garden'), findsOneWidget);
      await tester.enterText(find.byType(TextField).first, '0903');
      await _tap(tester, _button('Mời qua app'));
      expect(find.text('Số điện thoại cần đủ 10 số'), findsOneWidget);
    });

    testWidgets('sends the invite; J1 lists it as pending', (tester) async {
      final c = await _pump(tester, initial: GroupRoutes.members);
      await _tap(tester, _button('Mời thành viên'));
      await tester.enterText(find.byType(TextField).first, '0987654321');
      await _tap(tester, find.text('Chỉ báo cháy'));
      await _tap(tester, _button('Mời qua app'));
      expect(find.text('Thành viên'), findsWidgets);
      expect(find.text('0987 ••• 321'), findsOneWidget);
      final invited = (_members(
        c,
        'g-sky',
      )).firstWhere((m) => m.phone == '0987654321');
      expect(invited.pending, isTrue);
      expect(invited.role, GroupRole.alertsOnly);
      expect(invited.nickname, isNull);
    });

    testWidgets('a number without an account: inline error, nothing sent', (
      tester,
    ) async {
      final c = await _pump(tester, initial: GroupRoutes.members);
      final before = _members(c, 'g-sky').length;
      await _tap(tester, _button('Mời thành viên'));
      await tester.enterText(
        find.byType(TextField).first,
        FakeData.unregisteredPhone,
      );
      await _tap(tester, _button('Mời qua app'));
      expect(find.text(notRegisteredHint), findsOneWidget);
      expect(_members(c, 'g-sky').length, before);
      expect(_button('Mời qua app'), findsOneWidget);
    });

    testWidgets('a number already in the group: inline error', (tester) async {
      final c = await _pump(tester, initial: GroupRoutes.members);
      final before = _members(c, 'g-sky').length;
      await _tap(tester, _button('Mời thành viên'));
      for (final phone in ['0912000678', '0903456112', '0912345678']) {
        await tester.enterText(find.byType(TextField).first, phone);
        await _tap(tester, _button('Mời qua app'));
        expect(find.text(alreadyInGroupHint), findsOneWidget);
      }
      expect(_members(c, 'g-sky').length, before);
    });

    testWidgets('"Tên trong nhóm" goes with the invite', (tester) async {
      final c = await _pump(tester, initial: GroupRoutes.members);
      await _tap(tester, _button('Mời thành viên'));
      expect(find.text('Tên trong nhóm · không bắt buộc'), findsOneWidget);
      await tester.enterText(find.byType(TextField).first, '0987654321');
      await tester.enterText(find.byType(TextField).last, ' Tạp vụ ');
      await _tap(tester, _button('Mời qua app'));
      expect(find.text('Tạp vụ · mời vừa xong'), findsOneWidget);
      final invited = (_members(
        c,
        'g-sky',
      )).firstWhere((m) => m.phone == '0987654321');
      expect(invited.nickname, 'Tạp vụ');
    });

    testWidgets('refused for a member: the J13 rule shows', (tester) async {
      await _pump(tester, initial: GroupRoutes.invite, groupId: 'g-office');
      await tester.enterText(find.byType(TextField).first, '0987654321');
      await _tap(tester, _button('Mời qua app'));
      expect(find.text(groupPermissionNote), findsOneWidget);
      expect(find.text('Mời vào Văn phòng công ty'), findsOneWidget);
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
    });
  });

  group('J3 · Nhận lời mời', () {
    testWidgets('shows what the role gives', (tester) async {
      await _pump(tester, initial: GroupRoutes.invitation('inv-riverside'));
      expect(
        find.text('Chị Hoa mời bạn vào "Chung cư Riverside"'),
        findsOneWidget,
      );
      expect(find.text('Vai trò: Thành viên'), findsOneWidget);
      expect(find.text('Xem camera: Hầm B1, Hầm B2'), findsOneWidget);
      expect(find.text('Nhận báo cháy của 2 camera này'), findsOneWidget);
    });

    testWidgets('offers the name the inviter set', (tester) async {
      await _pump(tester, initial: GroupRoutes.invitation('inv-riverside'));
      final field = tester.widget<TextField>(find.byType(TextField));
      expect(field.decoration?.hintText, 'Minh Anh tầng 5');
      expect(find.text('Chị Hoa đặt'), findsOneWidget);
      expect(find.text('Mặc định'), findsNothing);
      await tester.enterText(find.byType(TextField), 'Anh Ba');
      await tester.pump();
      expect(find.text('Chị Hoa đặt'), findsNothing);
    });

    testWidgets('accept selects the group and opens Theo dõi', (tester) async {
      final c = await _pump(
        tester,
        initial: GroupRoutes.invitation('inv-riverside'),
      );
      await _tap(tester, _button('Chấp nhận'));
      expect(find.text(_monitorStub), findsOneWidget);
      expect(c.read(currentGroupIdProvider), 'g-riverside');
    });

    testWidgets('decline opens Theo dõi', (tester) async {
      final c = await _pump(
        tester,
        initial: GroupRoutes.invitation('inv-riverside'),
      );
      await _tap(tester, _button('Từ chối'));
      expect(find.text(_monitorStub), findsOneWidget);
      expect(c.read(currentGroupIdProvider), isNull);
    });
  });

  group('J4 · Quyền của thành viên', () {
    testWidgets('changes role and per-camera access at once', (tester) async {
      final c = await _pump(tester, initial: GroupRoutes.members);
      await _tap(tester, find.text('Chú Tuấn bảo vệ'));
      expect(find.text('Trần Anh Tuấn · 0912 ••• 678'), findsOneWidget);
      expect(find.text('Hầm B1 · Khu sạc xe'), findsOneWidget);

      await _tap(tester, find.byType(MpToggle).first);
      var tuan = (_members(c, 'g-sky')).firstWhere((m) => m.id == 'm-tuan');
      expect(tuan.cameraIds, isNot(contains('cam-charger')));
      expect(tester.widget<MpToggle>(find.byType(MpToggle).first).value, false);

      await _tap(tester, find.text('Chỉ báo cháy'));
      tuan = (_members(c, 'g-sky')).firstWhere((m) => m.id == 'm-tuan');
      expect(tuan.role, GroupRole.alertsOnly);

      await _tap(tester, find.text('Quản lý').last);
      tuan = (_members(c, 'g-sky')).firstWhere((m) => m.id == 'm-tuan');
      expect(tuan.role, GroupRole.manager);
      expect(find.text('CAMERA'), findsNothing);
    });

    testWidgets('J5 · revoke asks, then removes the member', (tester) async {
      final c = await _pump(tester, initial: GroupRoutes.member('m-tuan'));
      await _tap(tester, _button('Xoá khỏi nhóm'));
      expect(find.text('Xoá Chú Tuấn bảo vệ khỏi nhóm?'), findsOneWidget);
      await _tap(tester, _button('Huỷ'));
      expect(_members(c, 'g-sky'), hasLength(4));

      await _tap(tester, _button('Xoá khỏi nhóm'));
      await _tap(tester, _button('Xoá'));
      final members = _members(c, 'g-sky');
      expect(members.any((m) => m.id == 'm-tuan'), isFalse);
    });

    testWidgets('J11 · nickname sheet saves a suggestion', (tester) async {
      final c = await _pump(tester, initial: GroupRoutes.member('m-tuan'));
      await _tap(tester, find.text('Sửa'));
      expect(find.text('Tên của Chú Tuấn bảo vệ'), findsOneWidget);
      expect(find.text('Tên thật: Trần Anh Tuấn.'), findsOneWidget);
      await _tap(tester, find.text('Anh Tuấn'));
      await _tap(tester, _button('Lưu'));
      final tuan = (_members(c, 'g-sky')).firstWhere((m) => m.id == 'm-tuan');
      expect(tuan.nickname, 'Anh Tuấn');
      expect(find.text('Anh Tuấn'), findsWidgets);
    });

    testWidgets('J11 · only the owner names another member', (tester) async {
      await _pump(tester, initial: GroupRoutes.member('m-tuan'));
      expect(find.text('TÊN TRONG NHÓM'), findsOneWidget);
      expect(find.text('Sửa'), findsOneWidget);
    });

    testWidgets('J11 · a manager sees no nickname row', (tester) async {
      await _pump(
        tester,
        initial: GroupRoutes.member('m-tuan'),
        overrides: [_managerOfSky],
      );
      expect(find.text('VAI TRÒ'), findsOneWidget);
      expect(find.text('TÊN TRONG NHÓM'), findsNothing);
      expect(find.text('Sửa'), findsNothing);
    });
  });

  testWidgets('J12 · your nickname: "Dùng tên thật"', (tester) async {
    final c = await _pump(tester, initial: GroupRoutes.members);
    await _tap(tester, find.text('Minh Anh (bạn)'));
    expect(find.text('Tên của bạn'), findsOneWidget);
    expect(find.text('Hiện là "Nguyễn Minh Anh"'), findsOneWidget);
    await _tap(tester, find.text('Dùng tên thật'));
    await _tap(tester, _button('Lưu'));
    expect(find.text('Nguyễn Minh Anh (bạn)'), findsOneWidget);
    final me = (_members(c, 'g-sky')).firstWhere((m) => m.isYou);
    expect(me.nickname, isNull);
  });

  group('J7 · Nhóm của tôi', () {
    testWidgets('picking a group makes it current', (tester) async {
      final c = await _pump(tester, initial: GroupRoutes.groups);
      expect(find.text('NHÓM CỦA BẠN · 3'), findsOneWidget);
      expect(find.text('Bạn là "Ba" · 3 camera · 4 người'), findsOneWidget);
      await _tap(tester, find.text('Nhà mình'));
      expect(c.read(currentGroupIdProvider), 'g-home');
      expect(find.text('Ba (bạn)'), findsOneWidget);

      await _tap(tester, find.bySemanticsLabel('Quay lại'));
      expect(find.text('NHÓM CỦA BẠN · 3'), findsOneWidget);
      await _tap(tester, find.text('Văn phòng công ty'));
      expect(c.read(currentGroupIdProvider), 'g-office');
      expect(find.text('Minh Anh (bạn)'), findsOneWidget);
    });

    testWidgets('the personal group is not listed', (tester) async {
      final c = await _pump(tester, initial: GroupRoutes.groups);
      expect(_groups(c).where((g) => g.isPersonal), hasLength(1));
      expect(find.text('NHÓM CỦA BẠN · 3'), findsOneWidget);
      expect(find.text('Camera của tôi'), findsNothing);
      expect(find.text('Cá Nhân'), findsNothing);
    });

    testWidgets('pull-to-refresh shows a group joined elsewhere', (
      tester,
    ) async {
      final c = await _pump(tester, initial: GroupRoutes.groups);
      expect(find.text('NHÓM CỦA BẠN · 3'), findsOneWidget);
      _groups(c).add(_joinedElsewhere);
      await tester.pumpAndSettle();
      expect(find.text('hi'), findsNothing);

      await tester.fling(
        find.text('Mỗi nhóm có camera và người riêng.'),
        const Offset(0, 400),
        1000,
      );
      await _settle(tester);
      expect(find.text('NHÓM CỦA BẠN · 4'), findsOneWidget);
      expect(find.text('hi'), findsOneWidget);
    });

    testWidgets('coming back to the app reads the groups again', (
      tester,
    ) async {
      final c = await _pump(tester, initial: GroupRoutes.groups);
      _groups(c).add(_joinedElsewhere);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await _settle(tester);
      expect(find.text('NHÓM CỦA BẠN · 4'), findsOneWidget);
      expect(find.text('hi'), findsOneWidget);
    });

    testWidgets('opening J7 reads the groups again', (tester) async {
      final c = await _pump(tester, initial: AppRoutes.settings);
      c.listen(groupsProvider, (_, _) {});
      await _settle(tester);
      expect(c.read(groupsProvider).value, hasLength(4));
      _groups(c).add(_joinedElsewhere);
      unawaited(
        GoRouter.of(
          tester.element(find.text(_settingsStub)),
        ).push<void>(GroupRoutes.groups),
      );
      await _settle(tester);
      expect(find.text('NHÓM CỦA BẠN · 4'), findsOneWidget);
      expect(find.text('hi'), findsOneWidget);
    });

    testWidgets('no count before the groups arrive; a refresh keeps them', (
      tester,
    ) async {
      final c = await _pump(
        tester,
        initial: AppRoutes.settings,
        scenario: const FakeScenario(freezeClock: true),
      );
      unawaited(
        GoRouter.of(
          tester.element(find.text(_settingsStub)),
        ).push<void>(GroupRoutes.groups),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.text('Tạo nhóm'), findsOneWidget);
      expect(find.textContaining('NHÓM CỦA BẠN'), findsNothing);

      await _settle(tester);
      expect(find.text('NHÓM CỦA BẠN · 3'), findsOneWidget);

      _groups(c).add(_joinedElsewhere);
      await tester.fling(
        find.text('Mỗi nhóm có camera và người riêng.'),
        const Offset(0, 400),
        1000,
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 250));
      expect(c.read(groupsProvider).isLoading, isTrue);
      expect(find.text('NHÓM CỦA BẠN · 3'), findsOneWidget);
      expect(find.text('Văn phòng công ty'), findsOneWidget);

      await _settle(tester);
      expect(find.text('NHÓM CỦA BẠN · 4'), findsOneWidget);
      expect(find.text('hi'), findsOneWidget);
    });

    testWidgets('an invitation waiting is listed and opens J3', (tester) async {
      await _pump(tester, initial: GroupRoutes.groups, overrides: [_waiting]);
      expect(find.text('LỜI MỜI · 1'), findsOneWidget);
      expect(find.text('Chung cư Riverside'), findsOneWidget);
      expect(find.text('Chị Hoa mời bạn · 2 camera'), findsOneWidget);
      await _tap(tester, find.text('Chung cư Riverside'));
      expect(
        find.text('Chị Hoa mời bạn vào "Chung cư Riverside"'),
        findsOneWidget,
      );
    });

    testWidgets('no invitation: no "LỜI MỜI" section', (tester) async {
      await _pump(tester, initial: GroupRoutes.groups);
      expect(find.textContaining('LỜI MỜI'), findsNothing);
    });

    testWidgets('J17 · "Chấp nhận" on the card joins and stays on J7', (
      tester,
    ) async {
      final c = await _pump(
        tester,
        initial: GroupRoutes.groups,
        overrides: [_waiting],
      );
      await _tap(tester, find.widgetWithText(MpButton, 'Chấp nhận'));
      expect(find.text('Đã vào nhóm Chung cư Riverside'), findsOneWidget);
      expect(find.textContaining('LỜI MỜI'), findsNothing);
      expect(find.text('NHÓM CỦA BẠN · 4'), findsOneWidget);
      expect(_groups(c).map((g) => g.id), contains('g-riverside'));
      expect(c.read(currentGroupIdProvider), isNull);
      await tester.pump(const Duration(seconds: 6));
    });

    testWidgets('J18 · "Không" keeps the invitation', (tester) async {
      final c = await _pump(
        tester,
        initial: GroupRoutes.groups,
        overrides: [_waiting],
      );
      await _tap(tester, _button('Từ chối'));
      expect(find.text('Từ chối lời mời?'), findsOneWidget);
      expect(
        find.text(
          'Chị Hoa sẽ thấy bạn đã từ chối. Muốn vào sau thì nhờ Chị Hoa mời '
          'lại.',
        ),
        findsOneWidget,
      );
      await _tap(tester, find.text('Không'));
      expect(find.text('Từ chối lời mời?'), findsNothing);
      expect(find.text('LỜI MỜI · 1'), findsOneWidget);
      expect(c.read(fakeWorldProvider).invitationsWaiting, hasLength(1));
    });

    testWidgets('J19 · declined: gone at once, sent after "Hoàn tác" ends', (
      tester,
    ) async {
      final c = await _pump(
        tester,
        initial: GroupRoutes.groups,
        overrides: [_waiting],
      );
      await _tap(tester, _button('Từ chối'));
      await _tap(tester, _button('Từ chối'));
      expect(find.text('Đã từ chối lời mời · Riverside'), findsOneWidget);
      expect(find.textContaining('LỜI MỜI'), findsNothing);
      expect(c.read(fakeWorldProvider).invitationsWaiting, hasLength(1));

      await tester.pump(const Duration(seconds: 6));
      await _settle(tester);
      expect(c.read(fakeWorldProvider).invitationsWaiting, isEmpty);
      expect(find.textContaining('LỜI MỜI'), findsNothing);
    });

    testWidgets('J19 · "Hoàn tác" brings the invitation back, unsent', (
      tester,
    ) async {
      final c = await _pump(
        tester,
        initial: GroupRoutes.groups,
        overrides: [_waiting],
      );
      await _tap(tester, _button('Từ chối'));
      await _tap(tester, _button('Từ chối'));
      await _tap(tester, find.text('Hoàn tác'));
      expect(find.text('LỜI MỜI · 1'), findsOneWidget);

      await tester.pump(const Duration(seconds: 6));
      await _settle(tester);
      expect(c.read(fakeWorldProvider).invitationsWaiting, hasLength(1));
      expect(find.text('LỜI MỜI · 1'), findsOneWidget);
    });
  });

  test('J7 invitation subtitle: cameras and people when the server says', () {
    expect(
      invitationRowSubtitle(FakeData.invitation),
      'Chị Hoa mời bạn · 2 camera',
    );
    const anPhu = Invitation(
      id: 'inv',
      groupId: 'g',
      groupName: 'Nhà trọ An Phú',
      inviterName: 'Cô Lan',
      role: GroupRole.member,
      cameraNames: [],
      cameraCount: 2,
      memberCount: 8,
    );
    expect(invitationRowSubtitle(anPhu), 'Cô Lan mời bạn · 2 camera · 8 người');
    expect(shortGroupName(anPhu.groupName), 'An Phú');
  });

  test(
    'ROLE_CHANGED: the groups and that group\'s members are read again',
    () async {
      final c = ProviderContainer(
        overrides: fakeOverrides([
          fakeScenarioProvider.overrideWithValue(const FakeScenario.test()),
          authSessionProvider.overrideWith(_SignedIn.new),
        ]),
      );
      addTearDown(c.dispose);
      final before = await c.read(groupsProvider.future);
      expect(
        before.firstWhere((g) => g.id == 'g-office').myRole,
        isNot(GroupRole.manager),
      );
      final office = c
          .read(fakeWorldProvider)
          .groups
          .firstWhere((g) => g.id == 'g-office');
      c
          .read(fakeWorldProvider)
          .replaceGroup(
            Group(
              id: office.id,
              name: office.name,
              myRole: GroupRole.manager,
              myNickname: office.myNickname,
              cameraCount: office.cameraCount,
              memberCount: office.memberCount,
            ),
          );
      c.read(groupActionsProvider).roleChanged('g-office');
      final after = await c.read(groupsProvider.future);
      expect(
        after.firstWhere((g) => g.id == 'g-office').myRole,
        GroupRole.manager,
      );
    },
  );

  testWidgets('J8 → J1 · create a group, then its members', (tester) async {
    final c = await _pump(tester, initial: GroupRoutes.createGroup);
    expect(find.text('CAMERA'), findsNothing);
    expect(find.byType(MpToggle), findsNothing);
    expect(
      tester
          .widget<MpButton>(find.widgetWithText(MpButton, 'Tạo nhóm'))
          .onPressed,
      isNull,
    );
    await tester.enterText(find.byType(TextField).first, 'Nhà mới');
    await tester.pump();
    await _tap(tester, _button('Tạo nhóm'));

    final groups = _groups(c);
    final created = groups.firstWhere((g) => g.name == 'Nhà mới');
    expect(created.cameraCount, 0);
    expect(created.myRole, GroupRole.owner);
    expect(c.read(currentGroupIdProvider), created.id);

    expect(find.text('Nguyễn Minh Anh (bạn)'), findsOneWidget);
    expect(_button('Mời thành viên'), findsOneWidget);
  });

  testWidgets('J14 · leave asks, then the group is gone', (tester) async {
    final c = await _pump(
      tester,
      initial: GroupRoutes.members,
      groupId: 'g-office',
    );
    await _tap(tester, _button('Rời nhóm'));
    expect(find.text('Rời Văn phòng công ty?'), findsOneWidget);
    await _tap(tester, _button('Rời nhóm'));
    expect(find.text('NHÓM CỦA BẠN · 2'), findsOneWidget);
    expect(find.text('Văn phòng công ty'), findsNothing);
    expect(c.read(currentGroupIdProvider), isNull);
  });

  group('the current group never shows another group', () {
    testWidgets('J7 → J1: while the picked group loads, nothing of the last '
        'one shows and no action is reachable', (tester) async {
      await _pump(tester, initial: GroupRoutes.groups, scenario: _slow);
      await _tap(tester, find.text('Chung cư Sky Garden'));
      expect(_onMembers('Quản lý toà nhà'), findsOneWidget);
      expect(_onMembers('Giải tán nhóm'), findsOneWidget);
      await _tap(tester, find.bySemanticsLabel('Quay lại'));

      await tester.tap(find.text('Văn phòng công ty'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.byType(MembersScreen), findsOneWidget);
      expect(_onMembers('Thành viên'), findsOneWidget);
      for (final text in [
        'Chung cư Sky Garden',
        'Văn phòng công ty',
        'Quản lý toà nhà',
        'Minh Anh (bạn)',
        'Giải tán nhóm',
        'Rời nhóm',
        'Mời thành viên',
      ]) {
        expect(_onMembers(text), findsNothing, reason: text);
      }

      await _settle(tester);
      expect(_onMembers('Văn phòng công ty'), findsOneWidget);
      expect(_onMembers('Chị Mai'), findsOneWidget);
      expect(_onMembers('Rời nhóm'), findsOneWidget);
      expect(_onMembers('Chung cư Sky Garden'), findsNothing);
      expect(_onMembers('Giải tán nhóm'), findsNothing);
    });

    testWidgets('a reload of the same group keeps it on screen', (
      tester,
    ) async {
      final c = await _pump(
        tester,
        initial: GroupRoutes.members,
        scenario: _slow,
      );
      void expectSky() {
        expect(_onMembers('Chung cư Sky Garden'), findsOneWidget);
        expect(_onMembers('Quản lý toà nhà'), findsOneWidget);
        expect(_onMembers('Giải tán nhóm'), findsOneWidget);
      }

      expectSky();
      c.read(groupActionsProvider).roleChanged('g-sky');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(c.read(currentGroupViewProvider).isLoading, isTrue);
      expectSky();

      // Picking the group already shown (it was the default) is no switch.
      c.read(currentGroupIdProvider.notifier).select('g-sky');
      await tester.pump();
      expectSky();
      await _settle(tester);
      expectSky();
    });

    testWidgets('dissolve keeps the group tapped: a switch during the '
        'confirm cancels it', (tester) async {
      final c = await _pump(tester, initial: GroupRoutes.members);
      await _tap(tester, _button('Giải tán nhóm'));
      expect(find.text('Giải tán nhóm này?'), findsOneWidget);
      c.read(currentGroupIdProvider.notifier).select('g-home');
      await _settle(tester);
      await _tap(tester, _button('Giải tán'));
      expect(find.text('Giải tán nhóm này?'), findsNothing);
      expect(_groups(c).map((g) => g.id), containsAll(['g-sky', 'g-home']));
      expect(c.read(currentGroupIdProvider), 'g-home');
      expect(_onMembers('Ba (bạn)'), findsOneWidget);
    });

    testWidgets('leave keeps the group tapped: a switch during the confirm '
        'cancels it', (tester) async {
      final c = await _pump(
        tester,
        initial: GroupRoutes.members,
        groupId: 'g-office',
      );
      await _tap(tester, _button('Rời nhóm'));
      expect(find.text('Rời Văn phòng công ty?'), findsOneWidget);
      c.read(currentGroupIdProvider.notifier).select('g-sky');
      await _settle(tester);
      await _tap(tester, _button('Rời nhóm'));
      expect(find.text('Rời Văn phòng công ty?'), findsNothing);
      expect(_groups(c).map((g) => g.id), contains('g-office'));
      expect(c.read(currentGroupIdProvider), 'g-sky');
    });

    testWidgets('J5 · a switch during "Xoá khỏi nhóm?" removes no one', (
      tester,
    ) async {
      final c = await _pump(tester, initial: GroupRoutes.member('m-tuan'));
      await _tap(tester, _button('Xoá khỏi nhóm'));
      expect(find.text('Xoá Chú Tuấn bảo vệ khỏi nhóm?'), findsOneWidget);
      c.read(currentGroupIdProvider.notifier).select('g-home');
      await _settle(tester);
      expect(
        find.descendant(
          of: find.byType(MemberAccessScreen),
          matching: find.text('Xoá khỏi nhóm'),
        ),
        findsNothing,
      );
      await _tap(tester, _button('Xoá'));
      expect(_members(c, 'g-sky').any((m) => m.id == 'm-tuan'), isTrue);
    });
  });

  testWidgets('J15 · the owner dissolves the group', (tester) async {
    final c = await _pump(tester, initial: GroupRoutes.members);
    await _tap(tester, _button('Giải tán nhóm'));
    expect(find.text('Giải tán nhóm này?'), findsOneWidget);
    await _tap(tester, _button('Giải tán'));
    expect(find.text('NHÓM CỦA BẠN · 2'), findsOneWidget);
    expect(find.text('Chung cư Sky Garden'), findsNothing);
    final groups = _groups(c);
    expect(groups.any((g) => g.id == 'g-sky'), isFalse);
  });
}
