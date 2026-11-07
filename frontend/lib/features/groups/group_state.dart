import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/models.dart';
import '../../data/providers.dart';
import '../../data/repositories/group_repository.dart';
import '../auth/auth_session.dart';
import 'current_group.dart';

final groupMembersProvider = FutureProvider.family<List<Member>, String>((
  ref,
  groupId,
) {
  ref.watch(sessionUserIdProvider);
  return ref.watch(groupRepositoryProvider).listMembers(groupId);
});

final groupCamerasProvider = FutureProvider.family<List<Camera>, String>((
  ref,
  groupId,
) async {
  ref.watch(sessionUserIdProvider);
  final role = await ref.watch(
    groupsProvider.selectAsync(
      (groups) => groups.where((g) => g.id == groupId).firstOrNull?.myRole,
    ),
  );
  final cameras = await ref
      .watch(cameraRepositoryProvider)
      .listCameras(groupId);
  if (role != GroupRole.member) return cameras;
  return [
    for (final c in cameras)
      if (c.liveStreamUrl != null) c,
  ];
});

final groupAreasProvider = FutureProvider.family<List<Area>, String>((
  ref,
  groupId,
) {
  ref.watch(sessionUserIdProvider);
  return ref.watch(cameraRepositoryProvider).listAreas(groupId);
});

typedef CurrentGroupView = ({
  Group group,
  List<Member> members,
  List<Camera> cameras,
  List<Area> areas,
});

final currentGroupViewProvider = FutureProvider<CurrentGroupView>((ref) async {
  final group = await ref.watch(currentGroupProvider.future);
  final (members, cameras, areas) = await (
    ref.watch(groupMembersProvider(group.id).future),
    ref.watch(groupCamerasProvider(group.id).future),
    ref.watch(groupAreasProvider(group.id).future),
  ).wait;
  return (group: group, members: members, cameras: cameras, areas: areas);
});

final myInvitationsProvider = FutureProvider<List<Invitation>>((ref) {
  ref.watch(sessionUserIdProvider);
  return ref.watch(groupRepositoryProvider).listMyInvitations();
});

final invitationProvider = FutureProvider.autoDispose
    .family<Invitation, String>(
      (ref, id) => ref.watch(groupRepositoryProvider).getInvitation(id),
    );

final groupAccountProvider = Provider<User?>(
  (ref) => switch (ref.watch(authSessionProvider)) {
    SignedIn(:final user) => user,
    _ => null,
  },
);

final groupActionsProvider = Provider<GroupActions>(GroupActions.new);

class GroupActions {
  GroupActions(this._ref);

  final Ref _ref;

  GroupRepository get _repo => _ref.read(groupRepositoryProvider);

  void _refresh(String groupId) {
    _ref
      ..invalidate(groupsProvider)
      ..invalidate(groupMembersProvider(groupId));
  }

  Future<void> reload() async {
    _ref
      ..invalidate(groupsProvider)
      ..invalidate(myInvitationsProvider);
    try {
      await Future.wait([
        _ref.read(groupsProvider.future),
        _ref.read(myInvitationsProvider.future),
      ]);
    } on Object {
      // Offline or a server error: the last lists stay.
    }
  }

  void roleChanged(String groupId) => _refresh(groupId);

  Future<Group> createGroup({required String name, String? myNickname}) async {
    final group = await _repo.createGroup(name: name, myNickname: myNickname);
    _ref.invalidate(groupsProvider);
    _ref.read(currentGroupIdProvider.notifier).select(group.id);
    return group;
  }

  Future<Member> inviteMember({
    required String groupId,
    required String phone,
    required GroupRole role,
    required List<String> cameraIds,
    String? nickname,
  }) async {
    final member = await _repo.inviteMember(
      groupId: groupId,
      phone: phone,
      role: role,
      cameraIds: cameraIds,
      nickname: nickname,
    );
    _refresh(groupId);
    return member;
  }

  Future<Group> acceptInvitation(
    String invitationId, {
    String? nickname,
    bool makeCurrent = true,
  }) async {
    final group = await _repo.acceptInvitation(
      invitationId,
      nickname: nickname,
    );
    _refresh(group.id);
    _ref.invalidate(myInvitationsProvider);
    if (makeCurrent) {
      _ref.read(currentGroupIdProvider.notifier).select(group.id);
    }
    return group;
  }

  Future<void> declineInvitation(String invitationId) async {
    await _repo.declineInvitation(invitationId);
    _ref.invalidate(myInvitationsProvider);
  }

  Future<void> setRole({
    required String groupId,
    required String memberId,
    required GroupRole role,
  }) async {
    await _repo.setRole(groupId: groupId, memberId: memberId, role: role);
    _refresh(groupId);
  }

  Future<void> setCameraAccess({
    required String groupId,
    required String memberId,
    required String cameraId,
    required bool enabled,
  }) async {
    await _repo.setCameraAccess(
      groupId: groupId,
      memberId: memberId,
      cameraId: cameraId,
      enabled: enabled,
    );
    _refresh(groupId);
  }

  Future<void> removeMember({
    required String groupId,
    required String memberId,
  }) async {
    await _repo.removeMember(groupId: groupId, memberId: memberId);
    _refresh(groupId);
  }

  Future<void> setNickname({
    required String groupId,
    required String memberId,
    String? nickname,
  }) async {
    await _repo.setNickname(
      groupId: groupId,
      memberId: memberId,
      nickname: nickname,
    );
    _refresh(groupId);
  }

  Future<void> leaveGroup(String groupId) async {
    await _repo.leaveGroup(groupId);
    _forget(groupId);
  }

  Future<void> dissolveGroup(String groupId) async {
    await _repo.dissolveGroup(groupId);
    _forget(groupId);
  }

  void _forget(String groupId) {
    final current = _ref.read(currentGroupIdProvider.notifier);
    if (_ref.read(currentGroupIdProvider) == groupId) current.clear();
    _refresh(groupId);
  }
}

String groupDisplayName(Group g) => g.isPersonal ? 'Camera của tôi' : g.name;

String roleLabel(GroupRole role) => switch (role) {
  GroupRole.owner => 'Chủ sở hữu',
  GroupRole.manager => 'Quản lý',
  GroupRole.member => 'Thành viên',
  GroupRole.alertsOnly => 'Chỉ báo cháy',
};

String memberTitle(Member m) {
  if (m.pending) return maskPhone(m.phone);
  return m.isYou ? '${m.displayName} (bạn)' : m.displayName;
}

String memberInitial(Member m) {
  if (m.pending) return '?';
  final name = (m.realName ?? m.nickname ?? m.phone)
      .replaceAll(RegExp(r'\s*\(.*?\)'), '')
      .trim();
  final words = name.split(RegExp(r'\s+'));
  final last = words.isEmpty ? '' : words.last;
  return last.isEmpty ? '?' : last[0].toUpperCase();
}

String memberSubtitle(
  Member m, {
  required List<Camera> cameras,
  required List<Area> areas,
  required DateTime now,
}) {
  if (m.pending) {
    final invited = m.invitedAt;
    return [
      ?(m.nickname ?? m.note),
      if (invited != null) 'mời ${formatAgo(now.difference(invited))}',
    ].join(' · ');
  }
  if (m.note case final note?) return note;
  final ids = m.cameraIds;
  final mine = [
    for (final c in cameras)
      if (ids == null || ids.contains(c.id)) c,
  ];
  return switch (m.role) {
    GroupRole.owner => m.realName ?? '',
    GroupRole.manager => 'Mọi camera · được mời người',
    GroupRole.alertsOnly =>
      'Nhận báo cháy ${ids?.length ?? cameras.length} camera',
    GroupRole.member when m.isYou =>
      'Xem ${mine.length} camera: ${mine.map((c) => c.name).join(', ')}',
    GroupRole.member when mine.length == 1 =>
      'Chỉ camera ${_lowerFirst(mine.single.name)}',
    GroupRole.member => [
      ?m.realName,
      if (mine.isNotEmpty) areaSummary(mine, areas),
    ].join(' · '),
  };
}

String areaSummary(List<Camera> cameras, List<Area> areas) {
  final used = {for (final c in cameras) c.areaId};
  final names = [
    for (final a in areas)
      if (used.contains(a.id)) a.name,
  ];
  final out = <String>[];
  String? lastFull;
  for (final name in names) {
    final first = name.split(' ').first;
    if (lastFull != null &&
        name.contains(' ') &&
        lastFull.split(' ').first == first) {
      out.add(name.substring(first.length + 1));
    } else {
      out.add(name);
      lastFull = name;
    }
  }
  return out.join(', ');
}

String cameraLabel(Camera camera, List<Area> areas) {
  final area = areas.where((a) => a.id == camera.areaId).firstOrNull;
  if (area == null ||
      camera.name.toLowerCase().startsWith(area.name.toLowerCase())) {
    return camera.name;
  }
  return '${area.name} · ${camera.name}';
}

String groupRowSubtitle(Group g, {String accountName = ''}) {
  final name = g.myNickname.isEmpty ? accountName : g.myNickname;
  return 'Bạn là "$name" · ${groupCounts(g)}';
}

String invitationRowSubtitle(Invitation invitation) {
  final cameras = invitation.cameraCount ?? invitation.cameraNames.length;
  final people = invitation.memberCount;
  return [
    '${invitation.inviterName} mời bạn',
    if (cameras > 0) '$cameras camera',
    if (people != null && people > 0) '$people người',
  ].join(' · ');
}

String groupCounts(Group g) =>
    '${g.cameraCount} camera · ${g.memberCount} người';

String shortGroupName(String name) {
  for (final prefix in const [
    'Chung cư ',
    'Toà nhà ',
    'Tòa nhà ',
    'Nhà trọ ',
  ]) {
    if (name.startsWith(prefix) && name.length > prefix.length) {
      return name.substring(prefix.length);
    }
  }
  return name;
}

String givenNames(String fullName) {
  final words = fullName.trim().split(RegExp(r'\s+'));
  return words.length > 1 ? words.skip(1).join(' ') : fullName.trim();
}

String formatAgo(Duration d) {
  if (d.inMinutes < 1) return 'vừa xong';
  if (d.inHours < 1) return '${d.inMinutes} phút trước';
  if (d.inDays < 1) return '${d.inHours} giờ trước';
  return '${d.inDays} ngày trước';
}

List<String> nicknameSuggestions(Member m) {
  final real = m.realName;
  if (real == null) return [?m.note];
  final given = real.trim().split(RegExp(r'\s+')).last;
  return ['Chú $given', ?m.note, 'Anh $given'];
}

String _lowerFirst(String s) =>
    s.isEmpty ? s : s[0].toLowerCase() + s.substring(1);
