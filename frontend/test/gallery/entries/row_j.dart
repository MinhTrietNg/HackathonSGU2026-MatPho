import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/misc.dart' show Override;

import '../../fakes/fake_data.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_world.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/features/auth/auth_session.dart';
import 'package:mat_pho/features/groups/create_group_screen.dart';
import 'package:mat_pho/features/groups/current_group.dart';
import 'package:mat_pho/features/groups/group_dialogs.dart';
import 'package:mat_pho/features/groups/invitation_screen.dart';
import 'package:mat_pho/features/groups/invite_member_screen.dart';
import 'package:mat_pho/features/groups/member_access_screen.dart';
import 'package:mat_pho/features/groups/members_screen.dart';
import 'package:mat_pho/features/groups/my_groups_screen.dart';
import 'package:mat_pho/features/groups/nickname_sheet.dart';
import '../gallery_registry.dart';
import '../gallery_scope.dart';

Override _skyGarden({
  List<String> tuanCameras = const ['cam-charger', 'cam-down'],
}) => fakeWorldProvider.overrideWith((ref) {
  final world = FakeWorld(ref.watch(fakeScenarioProvider));
  ref.onDispose(world.dispose);
  world.areas = [
    for (final a in world.areas)
      if (a.id == 'a-lobby')
        Area(id: a.id, groupId: a.groupId, name: 'Sảnh')
      else
        a,
    const Area(id: 'a-lift', groupId: 'g-sky', name: 'Thang máy'),
  ];
  world.cameras = [
    for (final c in world.cameras)
      if (c.id != 'cam-ramp') c,
    const Camera(
      id: 'cam-lobby',
      groupId: 'g-sky',
      areaId: 'a-lobby',
      name: 'Sảnh chính',
      rtspUrl: 'rtsp://192.168.1.13:554/stream1',
    ),
  ];
  world.members['g-sky'] = [
    for (final m in world.members['g-sky']!)
      if (m.id == 'm-tuan') m.copyWith(cameraIds: tuanCameras) else m,
  ];
  return world;
});

final _signedIn = authSessionProvider.overrideWith(_SignedInAsMinhAnh.new);

Override _current(String groupId) =>
    currentGroupIdProvider.overrideWith(() => _Selected(groupId));

const _allSky = ['cam-charger', 'cam-down', 'cam-lobby'];

final rowJEntries = <GalleryEntry>[
  GalleryEntry(
    code: 'J1',
    title: 'Thành viên · toà nhà',
    builder: (_) => GalleryScope(
      overrides: [_skyGarden(tuanCameras: _allSky)],
      child: const MembersScreen(),
    ),
  ),
  GalleryEntry(
    code: 'J2',
    title: 'Mời thành viên',
    builder: (_) => GalleryScope(
      overrides: [_skyGarden()],
      child: const InviteMemberScreen(
        initialPhone: '0903456112',
        initialNickname: 'Bảo vệ ca đêm',
        initialAreaIds: {'a-b1', 'a-b2'},
        previewFocused: true,
      ),
    ),
  ),
  GalleryEntry(
    code: 'J3',
    title: 'Nhận lời mời (người được mời)',
    builder: (_) => GalleryScope(
      overrides: [_signedIn],
      child: InvitationScreen(invitationId: FakeData.invitation.id),
    ),
  ),
  GalleryEntry(
    code: 'J4',
    title: 'Quyền của thành viên',
    builder: (_) => GalleryScope(
      overrides: [_skyGarden()],
      child: const MemberAccessScreen(memberId: 'm-tuan'),
    ),
  ),
  GalleryEntry(
    code: 'J5',
    title: 'Thu hồi quyền (overlay)',
    builder: (_) => GalleryScope(
      overrides: [_skyGarden()],
      child: _ShowOnStart(
        show: (context) => confirmRemoveMember(context, 'Anh Tuấn'),
        child: const MemberAccessScreen(memberId: 'm-tuan'),
      ),
    ),
  ),
  GalleryEntry(
    code: 'J6',
    title: 'Thành viên · gia đình',
    builder: (_) => GalleryScope(
      overrides: [_current(FakeData.home.id)],
      child: const MembersScreen(),
    ),
  ),
  GalleryEntry(
    code: 'J7',
    title: 'Nhóm của tôi',
    builder: (_) => const GalleryScope(child: MyGroupsScreen()),
  ),
  GalleryEntry(
    code: 'J7a',
    title: 'Nhóm của tôi · có lời mời',
    builder: (_) =>
        GalleryScope(overrides: [_invited()], child: const MyGroupsScreen()),
  ),
  GalleryEntry(
    code: 'J8',
    title: 'Tạo nhóm',
    builder: (_) => GalleryScope(
      overrides: [_signedIn],
      child: const CreateGroupScreen(
        initialName: 'Nhà mình',
        previewFocused: true,
      ),
    ),
  ),
  GalleryEntry(
    code: 'J11',
    title: 'Biệt danh thành viên (overlay)',
    builder: (_) => GalleryScope(
      overrides: [_skyGarden()],
      child: _ShowOnStart(
        show: (context) => showNicknameSheet(
          context,
          title: 'Tên của Anh Tuấn',
          subtitle: 'Tên thật: Trần Anh Tuấn.',
          initialNickname: 'Chú Tuấn bảo vệ',
          realName: 'Trần Anh Tuấn',
          suggestions: const ['Chú Tuấn', 'Bảo vệ ca ngày', 'Anh Tuấn'],
          previewFocused: true,
        ),
        child: const MemberAccessScreen(memberId: 'm-tuan'),
      ),
    ),
  ),
  GalleryEntry(
    code: 'J12',
    title: 'Biệt danh của bạn (overlay)',
    builder: (_) => GalleryScope(
      overrides: [_skyGarden(tuanCameras: _allSky)],
      child: _ShowOnStart(
        show: (context) => showNicknameSheet(
          context,
          title: 'Tên của bạn',
          subtitle: 'Cả nhóm sẽ thấy tên này.',
          initialNickname: 'Minh Anh',
          realName: 'Nguyễn Minh Anh',
          previewFocused: true,
        ),
        child: const MembersScreen(),
      ),
    ),
  ),
  GalleryEntry(
    code: 'J13',
    title: 'Thành viên · bạn là thành viên',
    builder: (_) => GalleryScope(
      overrides: [_current(FakeData.office.id)],
      child: const MembersScreen(),
    ),
  ),
  GalleryEntry(
    code: 'J14',
    title: 'Rời nhóm (overlay)',
    builder: (_) => GalleryScope(
      overrides: [_current(FakeData.office.id)],
      child: _ShowOnStart(
        show: (context) => confirmLeaveGroup(context, FakeData.office.name),
        child: const MembersScreen(),
      ),
    ),
  ),
  GalleryEntry(
    code: 'J15',
    title: 'Giải tán nhóm (overlay)',
    builder: (_) => GalleryScope(
      overrides: [_skyGarden(tuanCameras: _allSky)],
      child: const _ShowOnStart(
        show: confirmDissolveGroup,
        child: MembersScreen(),
      ),
    ),
  ),
  GalleryEntry(
    code: 'J17',
    title: 'Nhóm của tôi · vừa tham gia',
    builder: (_) => GalleryScope(
      overrides: [_joinedAnPhu(), _current(FakeData.skyGarden.id)],
      child: _ShowOnStart(
        show: (context) =>
            showJoinedGroupToast(context, _anPhu.groupName, duration: null),
        child: const MyGroupsScreen(),
      ),
    ),
  ),
  GalleryEntry(
    code: 'J18',
    title: 'Từ chối lời mời (overlay)',
    builder: (_) => GalleryScope(
      overrides: [_invited()],
      child: _ShowOnStart(
        show: (context) =>
            confirmDeclineInvitation(context, _anPhu.inviterName),
        child: const MyGroupsScreen(),
      ),
    ),
  ),
  GalleryEntry(
    code: 'J19',
    title: 'Nhóm của tôi · vừa từ chối',
    builder: (_) => GalleryScope(
      child: _ShowOnStart(
        show: (context) => showDeclinedInvitationToast(
          context,
          _anPhu.groupName,
          onUndo: () {},
          duration: null,
        ),
        child: const MyGroupsScreen(),
      ),
    ),
  ),
];

const _anPhu = Invitation(
  id: 'inv-an-phu',
  groupId: 'g-an-phu',
  groupName: 'Nhà trọ An Phú',
  inviterName: 'Cô Lan',
  role: GroupRole.member,
  cameraNames: ['Hành lang', 'Bãi xe'],
  nickname: 'Phòng 203',
  memberCount: 8,
);

Override _invited() => fakeWorldProvider.overrideWith((ref) {
  final world = FakeWorld(ref.watch(fakeScenarioProvider));
  ref.onDispose(world.dispose);
  world.invitationsWaiting.add(_anPhu);
  return world;
});

Override _joinedAnPhu() => fakeWorldProvider.overrideWith((ref) {
  final world = FakeWorld(ref.watch(fakeScenarioProvider));
  ref.onDispose(world.dispose);
  world.groups.insert(
    0,
    Group(
      id: _anPhu.groupId,
      name: _anPhu.groupName,
      myRole: _anPhu.role,
      myNickname: _anPhu.nickname!,
      cameraCount: _anPhu.cameraNames.length,
      memberCount: _anPhu.memberCount!,
    ),
  );
  return world;
});

class _ShowOnStart extends StatefulWidget {
  const _ShowOnStart({required this.show, required this.child});

  final void Function(BuildContext context) show;
  final Widget child;

  @override
  State<_ShowOnStart> createState() => _ShowOnStartState();
}

class _ShowOnStartState extends State<_ShowOnStart> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) widget.show(context);
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

class _SignedInAsMinhAnh extends AuthSessionNotifier {
  @override
  AuthSession build() => const SignedIn(FakeData.user);
}

class _Selected extends CurrentGroup {
  _Selected(this.groupId);

  final String groupId;

  @override
  String? build() => groupId;
}
