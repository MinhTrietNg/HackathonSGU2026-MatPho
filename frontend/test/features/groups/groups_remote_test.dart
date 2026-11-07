import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mat_pho/core/router/app_router.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_button.dart';
import 'package:mat_pho/core/widgets/mp_toast.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_data.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/remote/camera_remote.dart';
import 'package:mat_pho/data/remote/group_remote.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/groups/group_routes.dart';
import 'package:mat_pho/features/groups/group_widgets.dart';
import 'package:mat_pho/features/groups/invite_member_screen.dart'
    show alreadyInGroupHint, notRegisteredHint;

import '../../data/remote/group_camera_server.dart';

const _gid = 'grp_sky_garden_01';

class _SignedIn extends AuthSessionNotifier {
  @override
  AuthSession build() => const SignedIn(FakeData.user);
}

GroupCameraServer _sky({String role = 'MEMBER_MANAGER'}) => GroupCameraServer()
  ..on('GET', '/groups', groupsJson(skyRole: role))
  ..on('GET', '/cameras', camerasJson)
  ..on('GET', '/groups/$_gid/subgroups', [
    {'subgroup_id': 'sub_b1', 'name': 'Hầm B1', 'camera_count': 1},
    {'subgroup_id': 'sub_b2', 'name': 'Hầm B2', 'camera_count': 1},
  ])
  ..on('GET', '/groups/$_gid/members', {
    'members': [
      {
        'user_id': 'usr_lan',
        'full_name': 'Trần Thị Lan',
        'phone_number': '+84903112233',
        'role': 'LEADER',
        'nickname': 'Chị Lan',
        'note': null,
        'camera_ids': null,
        'is_you': false,
      },
      {
        'user_id': 'usr_me',
        'full_name': 'Nguyễn Minh Anh',
        'phone_number': '+84912345678',
        'role': role,
        'nickname': 'Minh Anh',
        'note': null,
        'camera_ids': null,
        'is_you': true,
      },
    ],
    'pending_invitations': [],
  })
  ..on('GET', '/invitations/my-invitations', []);

Future<GoRouter> _pump(
  WidgetTester tester,
  GroupCameraServer server, {
  required String initial,
}) async {
  tester.view
    ..physicalSize = const Size(360, 780) * 2
    ..devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  addTearDown(hideMpToast);
  final router = GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: initial,
    routes: [
      GoRoute(
        path: AppRoutes.settings,
        builder: (_, _) => const Text('SETTINGS'),
        routes: groupSubRoutes,
      ),
      GoRoute(
        path: AppRoutes.monitor,
        builder: (_, _) => const Text('MONITOR'),
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: fakeOverrides([
        authSessionProvider.overrideWith(_SignedIn.new),
        groupRepositoryProvider.overrideWith(
          (ref) => RemoteGroupRepository(server.api),
        ),
        cameraRepositoryProvider.overrideWith(
          (ref) => RemoteCameraRepository(server.api),
        ),
      ]),
      child: MaterialApp.router(
        theme: AppTheme.dark(),
        locale: const Locale('vi'),
        supportedLocales: const [Locale('vi')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        routerConfig: router,
      ),
    ),
  );
  await tester.pumpAndSettle();
  return router;
}

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Finder _button(String label) => find.widgetWithText(MpButton, label).last;

Future<void> _invite(WidgetTester tester, String phone) async {
  await tester.enterText(find.byType(TextField).first, phone);
  await _tap(tester, _button('Mời qua app'));
}

void main() {
  group('J2 · Mời thành viên', () {
    testWidgets('PHONE_NOT_REGISTERED: inline under the field', (tester) async {
      final server = _sky()
        ..fail(
          'POST',
          '/groups/$_gid/invitations',
          404,
          'PHONE_NOT_REGISTERED',
        );
      await _pump(tester, server, initial: GroupRoutes.invite);
      expect(find.text('Mời vào Sky Garden'), findsOneWidget);
      await _invite(tester, '0911222333');
      expect(find.text(notRegisteredHint), findsOneWidget);
      expect(server.body('POST', '/groups/$_gid/invitations'), {
        'phone_number': '0911222333',
        'role': 'MEMBER',
        'nickname': null,
        'camera_ids': ['cam_charger', 'cam_down'],
      });
      expect(_button('Mời qua app'), findsOneWidget);
    });

    testWidgets('ALREADY_IN_GROUP: inline under the field', (tester) async {
      final server = _sky()
        ..fail('POST', '/groups/$_gid/invitations', 409, 'ALREADY_IN_GROUP');
      await _pump(tester, server, initial: GroupRoutes.invite);
      await _invite(tester, '0903112233');
      expect(find.text(alreadyInGroupHint), findsOneWidget);
    });

    testWidgets('PERMISSION_DENIED: the J13 rule as a toast', (tester) async {
      final server = _sky()
        ..fail('POST', '/groups/$_gid/invitations', 403, 'PERMISSION_DENIED');
      await _pump(tester, server, initial: GroupRoutes.invite);
      await _invite(tester, '0987654321');
      expect(find.text(groupPermissionNote), findsOneWidget);
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
    });
  });

  testWidgets('J3 · INVITATION_UNAVAILABLE: "Lời mời không còn hiệu lực."', (
    tester,
  ) async {
    final server = _sky()
      ..fail('GET', '/invitations/inv_old', 410, 'INVITATION_UNAVAILABLE');
    await _pump(tester, server, initial: GroupRoutes.invitation('inv_old'));
    expect(find.text('Lời mời không còn hiệu lực.'), findsOneWidget);
  });

  testWidgets('J7 · no nickname on the server: the account name', (
    tester,
  ) async {
    final server = _sky()
      ..on('GET', '/groups', [
        personalGroupJson,
        {...skyGroupJson, 'my_nickname': null},
      ]);
    await _pump(tester, server, initial: GroupRoutes.groups);
    expect(
      find.text('Bạn là "Nguyễn Minh Anh" · 2 camera · 2 người'),
      findsOneWidget,
    );
  });
}
