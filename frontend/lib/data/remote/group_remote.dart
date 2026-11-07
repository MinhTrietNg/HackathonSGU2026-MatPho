library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../errors.dart';
import '../models/group.dart';
import '../models/incident.dart';
import '../repositories/group_repository.dart';
import 'core/api_client.dart';
import 'core/json.dart';
import 'core/remote_providers.dart';

final class RemoteGroupRepository implements GroupRepository {
  RemoteGroupRepository(this._api);

  final ApiClient _api;

  @override
  Future<List<Group>> listGroups() async {
    final groups = [
      for (final (i, item) in asJsonList(await _api.get('/groups')).indexed)
        _group(asJsonMap(item, 'groups[$i]')),
    ];
    return Future.wait([
      for (final g in groups) g.isPersonal ? Future.value(g) : _counted(g),
    ]);
  }

  Future<Group> _counted(Group group) async {
    try {
      final json = asJsonMap(await _api.get('/groups/${group.id}/members'));
      final members = asJsonList(json['members'], 'members');
      return group.copyWith(memberCount: members.length);
    } on Exception {
      return group;
    }
  }

  @override
  Future<Group> createGroup({required String name, String? myNickname}) async =>
      _group(
        asJsonMap(
          await _api.post(
            '/groups',
            body: {'name': name, 'my_nickname': myNickname},
          ),
        ),
      );

  @override
  Future<List<Member>> listMembers(String groupId) async {
    final json = asJsonMap(await _api.get('/groups/$groupId/members'));
    return [
      ...readObjectList(json, 'members', _member),
      ...readObjectList(json, 'pending_invitations', _pendingMember),
    ];
  }

  @override
  Future<Member> inviteMember({
    required String groupId,
    required String phone,
    required GroupRole role,
    required List<String> cameraIds,
    String? nickname,
  }) async {
    final ids = role.canManage ? null : cameraIds;
    final json = asJsonMap(
      await _api.post(
        '/groups/$groupId/invitations',
        body: {
          'phone_number': phone.replaceAll(' ', ''),
          'role': groupRoleToJson(role),
          'nickname': nickname,
          'camera_ids': ids,
        },
      ),
    );
    return Member(
      id: readString(json, 'invitation_id'),
      phone: displayPhone(readString(json, 'phone_number')),
      role: _role(json, 'role'),
      nickname: readStringOrNull(json, 'nickname') ?? nickname,
      cameraIds: ids,
      pending: true,
      invitedAt: _time(json, 'created_at'),
    );
  }

  @override
  Future<List<Invitation>> listMyInvitations() async => [
    for (final (i, item) in asJsonList(
      await _api.get('/invitations/my-invitations'),
    ).indexed)
      _invitation(asJsonMap(item, 'invitations[$i]')),
  ];

  @override
  Future<Invitation> getInvitation(String invitationId) async =>
      _invitation(asJsonMap(await _api.get('/invitations/$invitationId')));

  @override
  Future<Group> acceptInvitation(
    String invitationId, {
    String? nickname,
  }) async => _group(
    asJsonMap(
      await _api.post(
        '/invitations/$invitationId/accept',
        body: {'nickname': nickname},
      ),
    ),
  );

  @override
  Future<void> declineInvitation(String invitationId) async {
    await _api.post('/invitations/$invitationId/decline');
  }

  @override
  Future<Member> setRole({
    required String groupId,
    required String memberId,
    required GroupRole role,
  }) async {
    await _api.patch(
      '/groups/$groupId/members/$memberId/role',
      body: {'role': groupRoleToJson(role)},
    );
    return _memberById(groupId, memberId);
  }

  @override
  Future<Member> setCameraAccess({
    required String groupId,
    required String memberId,
    required String cameraId,
    required bool enabled,
  }) async {
    await _api.put(
      '/groups/$groupId/members/$memberId/cameras',
      body: {'camera_id': cameraId, 'enabled': enabled},
    );
    return _memberById(groupId, memberId);
  }

  @override
  Future<void> removeMember({
    required String groupId,
    required String memberId,
  }) async {
    await _api.delete('/groups/$groupId/members/$memberId');
  }

  @override
  Future<Member> setNickname({
    required String groupId,
    required String memberId,
    String? nickname,
  }) async {
    await _api.patch(
      '/groups/$groupId/members/$memberId/nickname',
      body: {'nickname': nickname},
    );
    return _memberById(groupId, memberId);
  }

  @override
  Future<void> leaveGroup(String groupId) async {
    try {
      await _api.post('/groups/$groupId/leave');
    } on ServerException catch (e) {
      if (e.code == 'LEADER_CANNOT_LEAVE') {
        throw const PermissionDeniedException();
      }
      rethrow;
    }
  }

  @override
  Future<void> dissolveGroup(String groupId) async {
    await _api.delete('/groups/$groupId');
  }

  @override
  Future<Group> updateGroup({
    required String groupId,
    String? name,
    String? address,
  }) async {
    await _api.patch(
      '/groups/$groupId',
      body: {'name': ?name, 'address': ?address},
    );
    final groups = asJsonList(await _api.get('/groups'));
    for (final (i, item) in groups.indexed) {
      final json = asJsonMap(item, 'groups[$i]');
      if (json['group_id'] == groupId) return _group(json);
    }
    throw const ServerException(code: 'NOT_FOUND');
  }

  @override
  Future<void> revokeInvitation({
    required String groupId,
    required String invitationId,
  }) async {
    await _api.delete('/groups/$groupId/invitations/$invitationId');
  }

  @override
  Future<List<AuditEntry>> listAuditLog(
    String groupId, {
    int limit = 50,
  }) async => readObjectList(
    asJsonMap(
      await _api.get('/groups/$groupId/audit-logs', query: {'limit': limit}),
    ),
    'items',
    parseAuditEntry,
  );

  Future<Member> _memberById(String groupId, String memberId) async {
    final members = await listMembers(groupId);
    return members.where((m) => m.id == memberId).firstOrNull ??
        (throw ServerException(
          code: badResponse,
          message: 'Member $memberId missing after the change',
        ));
  }
}

GroupRole parseGroupRole(String value) => switch (value) {
  'LEADER' => GroupRole.owner,
  'MEMBER_MANAGER' => GroupRole.manager,
  'MEMBER' => GroupRole.member,
  'NOTIFIER' => GroupRole.alertsOnly,
  _ => throw ServerException(
    code: badResponse,
    message: 'Unknown role "$value"',
  ),
};

String groupRoleToJson(GroupRole role) => switch (role) {
  GroupRole.owner => 'LEADER',
  GroupRole.manager => 'MEMBER_MANAGER',
  GroupRole.member => 'MEMBER',
  GroupRole.alertsOnly => 'NOTIFIER',
};

GroupRole _role(Map<String, Object?> json, String key) =>
    parseGroupRole(readString(json, key));

DateTime? _time(Map<String, Object?> json, String key) {
  final value = json[key];
  return value is String ? tryParseServerTime(value) : null;
}

Group _group(Map<String, Object?> json) => Group(
  id: readString(json, 'group_id'),
  name: readString(json, 'group_name'),
  myRole: _role(json, 'my_role'),
  myNickname: readStringOrNull(json, 'my_nickname') ?? '',
  cameraCount: readIntOrNull(json, 'camera_count') ?? 0,
  memberCount: readIntOrNull(json, 'member_count') ?? 1,
  isPersonal: readBoolOrNull(json, 'is_personal') ?? false,
  address: readStringOrNull(json, 'address'),
);

Member _member(Map<String, Object?> json) => Member(
  id: readString(json, 'user_id'),
  phone: displayPhone(readString(json, 'phone_number')),
  role: _role(json, 'role'),
  realName: readStringOrNull(json, 'full_name'),
  nickname: readStringOrNull(json, 'nickname'),
  note: readStringOrNull(json, 'note'),
  cameraIds: json['camera_ids'] == null
      ? null
      : readStringList(json, 'camera_ids'),
  isYou: readBoolOrNull(json, 'is_you') ?? false,
);

Member _pendingMember(Map<String, Object?> json) => Member(
  id: readString(json, 'invitation_id'),
  phone: displayPhone(readString(json, 'phone_number')),
  role: _role(json, 'role'),
  nickname: readStringOrNull(json, 'nickname'),
  cameraIds: json['camera_ids'] == null
      ? null
      : readStringList(json, 'camera_ids'),
  pending: true,
  invitedAt: _time(json, 'created_at'),
);

AuditEntry parseAuditEntry(Map<String, Object?> json) => AuditEntry(
  id: readString(json, 'log_id'),
  action: readString(json, 'action'),
  actorId: readStringOrNull(json, 'actor_id'),
  target: readStringOrNull(json, 'target_entity'),
  details: readMapOrNull(json, 'details') ?? const {},
  createdAt: _time(json, 'created_at'),
);

Invitation _invitation(Map<String, Object?> json) {
  final names = json['camera_names'] == null
      ? const <String>[]
      : readStringList(json, 'camera_names');
  return Invitation(
    id: readString(json, 'invitation_id'),
    groupId: readString(json, 'group_id'),
    groupName: readString(json, 'group_name'),
    inviterName: readString(json, 'invited_by_name'),
    role: _role(json, 'role'),
    cameraNames: names,
    nickname: readStringOrNull(json, 'suggested_nickname'),
    groupAddress: readStringOrNull(json, 'group_address'),
    cameraCount: readIntOrNull(json, 'camera_count'),
    memberCount: readIntOrNull(json, 'member_count'),
    createdAt: _time(json, 'created_at'),
  );
}

final remoteGroupRepositoryProvider = Provider<GroupRepository>(
  (ref) => RemoteGroupRepository(ref.watch(apiClientProvider)),
);
