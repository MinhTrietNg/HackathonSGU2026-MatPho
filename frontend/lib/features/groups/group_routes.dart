import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import 'create_group_screen.dart';
import 'invitation_screen.dart';
import 'invite_member_screen.dart';
import 'member_access_screen.dart';
import 'members_screen.dart';
import 'my_groups_screen.dart';

abstract final class GroupRoutes {
  static const groups = '${AppRoutes.settings}/groups';

  static const createGroup = '$groups/new';

  static const members = '${AppRoutes.settings}/members';

  static const invite = '$members/invite';

  static String member(String memberId) => '$members/$memberId';

  static String invitation(String invitationId) =>
      '${AppRoutes.settings}/invitation/$invitationId';
}

final groupSubRoutes = <RouteBase>[
  GoRoute(
    path: 'groups',
    parentNavigatorKey: rootNavigatorKey,
    builder: (context, state) => const MyGroupsScreen(),
    routes: [
      GoRoute(
        path: 'new',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const CreateGroupScreen(),
      ),
    ],
  ),
  GoRoute(
    path: 'members',
    parentNavigatorKey: rootNavigatorKey,
    builder: (context, state) => const MembersScreen(),
    routes: [
      GoRoute(
        path: 'invite',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const InviteMemberScreen(),
      ),
      GoRoute(
        path: ':memberId',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) =>
            MemberAccessScreen(memberId: state.pathParameters['memberId']!),
      ),
    ],
  ),
  GoRoute(
    path: 'invitation/:id',
    parentNavigatorKey: rootNavigatorKey,
    builder: (context, state) =>
        InvitationScreen(invitationId: state.pathParameters['id']!),
  ),
];
