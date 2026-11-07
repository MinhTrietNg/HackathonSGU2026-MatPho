import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/group.dart';
import 'package:mat_pho/data/models/incident.dart';
import 'package:mat_pho/data/repositories/group_repository.dart';
import 'fake_data.dart';
import 'fake_world.dart';

final class FakeGroupRepository implements GroupRepository {
  FakeGroupRepository(this._world);

  final FakeWorld _world;

  @override
  Future<List<Group>> listGroups() async {
    await _world.delay();
    return List.unmodifiable(_world.groups);
  }

  @override
  Future<Group> createGroup({required String name, String? myNickname}) async {
    await _world.delay();
    final group = Group(
      id: _world.newId('g'),
      name: name,
      myRole: GroupRole.owner,
      myNickname: myNickname ?? _world.user.fullName,
      cameraCount: 0,
      memberCount: 1,
    );
    _world.groups.add(group);
    _addSelf(group.id, GroupRole.owner, nickname: myNickname);
    return group;
  }

  @override
  Future<List<Member>> listMembers(String groupId) async {
    await _world.delay();
    return List.unmodifiable(_members(groupId));
  }

  @override
  Future<Member> inviteMember({
    required String groupId,
    required String phone,
    required GroupRole role,
    required List<String> cameraIds,
    String? nickname,
  }) async {
    await _world.delay();
    _requireManager(groupId);
    _requireShared(groupId);
    final digits = phone.replaceAll(' ', '');
    if (!FakeData.registeredPhones.contains(digits)) {
      throw const PhoneNotRegisteredException();
    }
    if (_members(groupId).any((m) => m.phone == digits)) {
      throw const AlreadyInGroupException();
    }
    final member = Member(
      id: _world.newId('m'),
      phone: digits,
      role: role,
      nickname: nickname,
      cameraIds: role.canManage ? null : cameraIds,
      pending: true,
      invitedAt: _world.now(),
    );
    _members(groupId).add(member);
    _bumpMemberCount(groupId, 1);
    return member;
  }

  @override
  Future<List<Invitation>> listMyInvitations() async {
    await _world.delay();
    return List.unmodifiable(_world.invitationsWaiting);
  }

  @override
  Future<Invitation> getInvitation(String invitationId) async {
    await _world.delay();
    if (invitationId != FakeData.invitation.id) {
      throw const InvitationUnavailableException();
    }
    return FakeData.invitation;
  }

  @override
  Future<Group> acceptInvitation(
    String invitationId, {
    String? nickname,
  }) async {
    final invitation = await getInvitation(invitationId);
    nickname ??= invitation.nickname;
    if (_world.groups.any((g) => g.id == invitation.groupId)) {
      throw const InvitationUnavailableException();
    }
    final group = Group(
      id: invitation.groupId,
      name: invitation.groupName,
      myRole: invitation.role,
      myNickname: nickname ?? _world.user.fullName,
      cameraCount: 0,
      memberCount: 1,
    );
    _world.groups.add(group);
    _addSelf(
      group.id,
      invitation.role,
      nickname: nickname,
      cameraIds: invitation.role.canManage ? null : const [],
    );
    _world.invitationsWaiting.removeWhere((i) => i.id == invitationId);
    return group;
  }

  @override
  Future<void> declineInvitation(String invitationId) async {
    await getInvitation(invitationId);
    _world.invitationsWaiting.removeWhere((i) => i.id == invitationId);
  }

  @override
  Future<Member> setRole({
    required String groupId,
    required String memberId,
    required GroupRole role,
  }) async {
    await _world.delay();
    _requireCanChange(groupId, memberId);
    if (role == GroupRole.owner) throw const PermissionDeniedException();
    return _replace(groupId, memberId, (m) {
      if (role.canManage) return m.copyWith(role: role, allCameras: true);
      return m.copyWith(
        role: role,
        cameraIds: _camerasAfterDemotion(m, groupId),
      );
    });
  }

  List<String> _camerasAfterDemotion(Member m, String groupId) =>
      m.cameraIds ??
      [
        for (final c in _world.cameras)
          if (c.groupId == groupId) c.id,
      ];

  @override
  Future<Member> setCameraAccess({
    required String groupId,
    required String memberId,
    required String cameraId,
    required bool enabled,
  }) async {
    await _world.delay();
    _requireCanChange(groupId, memberId);
    if (_member(groupId, memberId).role.canManage) {
      throw const PermissionDeniedException();
    }
    return _replace(groupId, memberId, (m) {
      final current =
          m.cameraIds ??
          [
            for (final c in _world.cameras)
              if (c.groupId == groupId) c.id,
          ];
      return m.copyWith(
        cameraIds: [
          for (final id in current)
            if (id != cameraId) id,
          if (enabled) cameraId,
        ],
      );
    });
  }

  @override
  Future<void> removeMember({
    required String groupId,
    required String memberId,
  }) async {
    await _world.delay();
    _requireCanChange(groupId, memberId, allowPending: true);
    _members(groupId).removeWhere((m) => m.id == memberId);
    _bumpMemberCount(groupId, -1);
  }

  @override
  Future<Member> setNickname({
    required String groupId,
    required String memberId,
    String? nickname,
  }) async {
    await _world.delay();
    final me = _world.me(groupId);
    if (memberId != me.id && _world.group(groupId).myRole != GroupRole.owner) {
      throw const PermissionDeniedException();
    }
    final updated = _replace(
      groupId,
      memberId,
      (m) => m.copyWith(nickname: nickname, clearNickname: nickname == null),
    );
    if (updated.isYou) {
      final group = _world.group(groupId);
      _world.replaceGroup(
        group.copyWith(myNickname: nickname ?? updated.realName),
      );
    }
    return updated;
  }

  @override
  Future<void> leaveGroup(String groupId) async {
    await _world.delay();
    _requireShared(groupId);
    if (_world.group(groupId).myRole == GroupRole.owner) {
      throw const PermissionDeniedException();
    }
    _drop(groupId);
  }

  @override
  Future<void> dissolveGroup(String groupId) async {
    await _world.delay();
    _requireShared(groupId);
    if (_world.group(groupId).myRole != GroupRole.owner) {
      throw const PermissionDeniedException();
    }
    _drop(groupId);
  }

  @override
  Future<Group> updateGroup({
    required String groupId,
    String? name,
    String? address,
  }) async {
    await _world.delay();
    if (_world.group(groupId).myRole != GroupRole.owner) {
      throw const PermissionDeniedException();
    }
    final updated = _world
        .group(groupId)
        .copyWith(name: name, address: address);
    _world.replaceGroup(updated);
    return updated;
  }

  @override
  Future<void> revokeInvitation({
    required String groupId,
    required String invitationId,
  }) async {
    await _world.delay();
    _requireManager(groupId);
    final invite = _members(
      groupId,
    ).where((m) => m.id == invitationId && m.pending).firstOrNull;
    if (invite == null) throw const ServerException(code: 'NOT_FOUND');
    _members(groupId).remove(invite);
    _bumpMemberCount(groupId, -1);
  }

  @override
  Future<List<AuditEntry>> listAuditLog(
    String groupId, {
    int limit = 50,
  }) async {
    await _world.delay();
    _requireManager(groupId);
    return const [];
  }

  void _addSelf(
    String groupId,
    GroupRole role, {
    String? nickname,
    List<String>? cameraIds,
  }) {
    _world.members[groupId] = [
      Member(
        id: _world.newId('m'),
        phone: _world.user.phone,
        role: role,
        realName: _world.user.fullName,
        nickname: nickname,
        cameraIds: cameraIds,
        isYou: true,
      ),
    ];
  }

  void _drop(String groupId) {
    _world.groups.removeWhere((g) => g.id == groupId);
    _world.members.remove(groupId);
    _world.cameras.removeWhere((c) => c.groupId == groupId);
    _world.areas.removeWhere((a) => a.groupId == groupId);
    _world.trash.removeWhere((t) => t.entry.groupId == groupId);
  }

  List<Member> _members(String groupId) {
    _world.group(groupId);
    return _world.members.putIfAbsent(groupId, () => []);
  }

  Member _replace(
    String groupId,
    String memberId,
    Member Function(Member) change,
  ) {
    final list = _members(groupId);
    final i = list.indexWhere((m) => m.id == memberId);
    if (i < 0) throw StateError('No member $memberId');
    return list[i] = change(list[i]);
  }

  void _bumpMemberCount(String groupId, int delta) {
    final group = _world.group(groupId);
    _world.replaceGroup(group.copyWith(memberCount: group.memberCount + delta));
  }

  void _requireManager(String groupId) {
    if (!_world.group(groupId).myRole.canManage) {
      throw const PermissionDeniedException();
    }
  }

  void _requireShared(String groupId) {
    if (_world.group(groupId).isPersonal) {
      throw const PermissionDeniedException();
    }
  }

  void _requireCanChange(
    String groupId,
    String memberId, {
    bool allowPending = false,
  }) {
    _requireManager(groupId);
    final m = _member(groupId, memberId);
    if (m.isYou || m.role == GroupRole.owner || (m.pending && !allowPending)) {
      throw const PermissionDeniedException();
    }
  }

  Member _member(String groupId, String memberId) =>
      _members(groupId).firstWhere(
        (m) => m.id == memberId,
        orElse: () => throw StateError('No member $memberId'),
      );
}
