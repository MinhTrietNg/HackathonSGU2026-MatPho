import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/remote/group_remote.dart';

import 'group_camera_server.dart';

const _gid = 'grp_sky_garden_01';

const _membersJson = {
  'members': [
    {
      'user_id': 'usr_lan',
      'full_name': 'Trần Thị Lan',
      'phone_number': '+84903112233',
      'role': 'LEADER',
      'nickname': 'Chị Lan',
      'note': 'Quản lý toà nhà',
      'camera_ids': null,
      'joined_at': '2026-11-01T08:00:00+00:00',
      'is_you': false,
    },
    {
      'user_id': 'usr_me',
      'full_name': 'Nguyễn Minh Anh',
      'phone_number': '+84912345678',
      'role': 'MEMBER_MANAGER',
      'nickname': null,
      'note': null,
      'camera_ids': null,
      'joined_at': '2026-11-02T08:00:00+00:00',
      'is_you': true,
    },
    {
      'user_id': 'usr_tuan',
      'full_name': 'Trần Anh Tuấn',
      'phone_number': '+84912000678',
      'role': 'MEMBER',
      'nickname': 'Chú Tuấn bảo vệ',
      'note': null,
      'camera_ids': ['cam_charger'],
      'joined_at': 'None',
      'is_you': false,
    },
    {
      'user_id': 'usr_bin',
      'full_name': 'Nguyễn Văn Bin',
      'phone_number': '+84901000111',
      'role': 'NOTIFIER',
      'nickname': null,
      'note': null,
      'camera_ids': [],
      'joined_at': '2026-11-03T08:00:00+00:00',
      'is_you': false,
    },
  ],
  'pending_invitations': [
    {
      'invitation_id': 'inv_987654',
      'phone_number': '+84903456112',
      'role': 'NOTIFIER',
      'nickname': 'Bảo vệ ca đêm',
      'camera_ids': ['cam_charger'],
      'camera_names': ['Hầm B1 · Khu sạc xe'],
      'created_at': '2026-11-04T12:00:00.000Z',
    },
  ],
};

const _myInvitationJson = {
  'invitation_id': 'inv_987654',
  'group_id': 'grp_sky_garden_01',
  'group_name': 'Chung cư Sky Garden',
  'group_address': '12 Nguyễn Văn Linh, Q.7, TP.HCM',
  'invited_by_name': 'Trần Thị Lan',
  'role': 'MEMBER',
  'suggested_nickname': 'Anh Hùng Kỹ Thuật',
  'camera_count': 2,
  'camera_names': ['Hầm B1 · Khu sạc xe', 'Cổng chính'],
  'status': 'PENDING',
  'created_at': '2026-11-04T12:00:00.000Z',
};

void main() {
  late GroupCameraServer server;
  late RemoteGroupRepository repo;

  setUp(() {
    server = GroupCameraServer();
    repo = RemoteGroupRepository(server.api);
  });

  group('roles', () {
    test('contract names ↔ GroupRole', () {
      expect(parseGroupRole('LEADER'), GroupRole.owner);
      expect(parseGroupRole('MEMBER_MANAGER'), GroupRole.manager);
      expect(parseGroupRole('MEMBER'), GroupRole.member);
      expect(parseGroupRole('NOTIFIER'), GroupRole.alertsOnly);
      for (final role in GroupRole.values) {
        expect(parseGroupRole(groupRoleToJson(role)), role);
      }
      expect(
        () => parseGroupRole('OWNER'),
        throwsA(
          isA<ServerException>().having((e) => e.code, 'code', 'BAD_RESPONSE'),
        ),
      );
    });
  });

  group('groups', () {
    test('GET /groups: personal flag, role, counts, address', () async {
      server
        ..on('GET', '/groups', [
          personalGroupJson,
          {...skyGroupJson, 'my_nickname': null},
        ])
        ..on('GET', '/groups/$_gid/members', _membersJson);
      final groups = await repo.listGroups();
      expect(server.calls, ['GET /groups', 'GET /groups/$_gid/members']);
      expect(
        server.request('GET', '/groups').headers['Authorization'],
        'Bearer tok-1',
      );

      final personal = groups.first;
      expect(personal.id, 'grp_personal_usr_me');
      expect(personal.name, 'Cá Nhân');
      expect(personal.isPersonal, isTrue);
      expect(personal.myRole, GroupRole.owner);
      expect(personal.address, isNull);

      final sky = groups.last;
      expect(sky.isPersonal, isFalse);
      expect(sky.name, 'Chung cư Sky Garden');
      expect(sky.myRole, GroupRole.manager);
      expect(sky.myNickname, '');
      expect(sky.cameraCount, 2);
      expect(sky.memberCount, 4);
      expect(sky.address, '12 Nguyễn Văn Linh, Q.7, TP.HCM');
    });

    test('GET /groups: member count from the members, not member_count '
        '(a stale counter)', () async {
      server
        ..on('GET', '/groups', [
          personalGroupJson,
          {...skyGroupJson, 'member_count': 1},
        ])
        ..on('GET', '/groups/$_gid/members', _membersJson);
      final groups = await repo.listGroups();
      expect(groups.first.memberCount, 1);
      expect(groups.last.memberCount, 4);
    });

    test('GET /groups: member_count when the members cannot be read', () async {
      server
        ..on('GET', '/groups', [
          personalGroupJson,
          {...skyGroupJson, 'member_count': 7},
        ])
        ..fail('GET', '/groups/$_gid/members', 403, 'PERMISSION_DENIED');
      final groups = await repo.listGroups();
      expect(groups.last.memberCount, 7);
    });

    test('a reply of the wrong shape is a ServerException', () async {
      server.on('GET', '/groups', {'groups': []});
      await expectLater(repo.listGroups(), throwsA(isA<ServerException>()));
      server.on('GET', '/groups', [
        {...skyGroupJson, 'my_role': 'BOSS'},
      ]);
      await expectLater(repo.listGroups(), throwsA(isA<ServerException>()));
    });

    test('POST /groups: name and nickname, no address (J8)', () async {
      server.on('POST', '/groups', {
        'group_id': 'grp_new',
        'group_name': 'Nhà mới',
        'is_personal': false,
        'address': null,
        'member_count': 1,
        'camera_count': 0,
        'my_role': 'LEADER',
        'my_nickname': 'Nguyễn Minh Anh',
      }, status: 201);
      final g = await repo.createGroup(
        name: 'Nhà mới',
        myNickname: 'Nguyễn Minh Anh',
      );
      expect(server.body('POST', '/groups'), {
        'name': 'Nhà mới',
        'my_nickname': 'Nguyễn Minh Anh',
      });
      expect(g.id, 'grp_new');
      expect(g.myRole, GroupRole.owner);
      expect(g.myNickname, 'Nguyễn Minh Anh');
      expect(g.cameraCount, 0);
    });

    test('leave, dissolve', () async {
      server
        ..on('POST', '/groups/$_gid/leave', {'status': 'success'})
        ..on('DELETE', '/groups/$_gid', {'status': 'success'});
      await repo.leaveGroup(_gid);
      await repo.dissolveGroup(_gid);
      expect(server.calls, [
        'POST /groups/$_gid/leave',
        'DELETE /groups/$_gid',
      ]);
    });

    test('the owner leaving (LEADER_CANNOT_LEAVE) is refused', () async {
      server.fail('POST', '/groups/$_gid/leave', 400, 'LEADER_CANNOT_LEAVE');
      await expectLater(
        repo.leaveGroup(_gid),
        throwsA(isA<PermissionDeniedException>()),
      );
    });

    test('PERMISSION_DENIED → PermissionDeniedException', () async {
      server.fail('DELETE', '/groups/$_gid', 403, 'PERMISSION_DENIED');
      await expectLater(
        repo.dissolveGroup(_gid),
        throwsA(isA<PermissionDeniedException>()),
      );
    });
  });

  group('members', () {
    test('GET members: members then pending invitations', () async {
      server.on('GET', '/groups/$_gid/members', _membersJson);
      final members = await repo.listMembers(_gid);
      expect(members.map((m) => m.id), [
        'usr_lan',
        'usr_me',
        'usr_tuan',
        'usr_bin',
        'inv_987654',
      ]);

      final lan = members[0];
      expect(lan.role, GroupRole.owner);
      expect(lan.phone, '0903112233');
      expect(lan.realName, 'Trần Thị Lan');
      expect(lan.nickname, 'Chị Lan');
      expect(lan.note, 'Quản lý toà nhà');
      expect(lan.cameraIds, isNull);
      expect(lan.isYou, isFalse);
      expect(lan.pending, isFalse);

      final me = members[1];
      expect(me.role, GroupRole.manager);
      expect(me.isYou, isTrue);
      expect(me.displayName, 'Nguyễn Minh Anh');

      final tuan = members[2];
      expect(tuan.role, GroupRole.member);
      expect(tuan.cameraIds, ['cam_charger']);

      final bin = members[3];
      expect(bin.role, GroupRole.alertsOnly);
      expect(bin.cameraIds, isEmpty);

      final pending = members[4];
      expect(pending.pending, isTrue);
      expect(pending.phone, '0903456112');
      expect(pending.role, GroupRole.alertsOnly);
      expect(pending.nickname, 'Bảo vệ ca đêm');
      expect(pending.realName, isNull);
      expect(pending.cameraIds, ['cam_charger']);
      expect(pending.invitedAt, DateTime.utc(2026, 11, 4, 12).toLocal());
    });

    test(
      'invite: phone, role, nickname, camera ids → pending member',
      () async {
        server.on('POST', '/groups/$_gid/invitations', {
          'invitation_id': 'inv_new',
          'phone_number': '+84987654321',
          'role': 'MEMBER',
          'nickname': 'Tạp vụ',
          'status': 'PENDING',
          'created_at': '2026-11-04T12:00:00.000Z',
        }, status: 201);
        final m = await repo.inviteMember(
          groupId: _gid,
          phone: '0987 654 321',
          role: GroupRole.member,
          cameraIds: ['cam_charger'],
          nickname: 'Tạp vụ',
        );
        expect(server.body('POST', '/groups/$_gid/invitations'), {
          'phone_number': '0987654321',
          'role': 'MEMBER',
          'nickname': 'Tạp vụ',
          'camera_ids': ['cam_charger'],
        });
        expect(m.id, 'inv_new');
        expect(m.pending, isTrue);
        expect(m.phone, '0987654321');
        expect(m.role, GroupRole.member);
        expect(m.nickname, 'Tạp vụ');
        expect(m.cameraIds, ['cam_charger']);
        expect(m.invitedAt, DateTime.utc(2026, 11, 4, 12).toLocal());
      },
    );

    test('invite a manager: camera_ids null (every camera)', () async {
      server.on('POST', '/groups/$_gid/invitations', {
        'invitation_id': 'inv_new',
        'phone_number': '+84987654321',
        'role': 'MEMBER_MANAGER',
        'nickname': null,
        'status': 'PENDING',
        'created_at': '2026-11-04T12:00:00.000Z',
      }, status: 201);
      final m = await repo.inviteMember(
        groupId: _gid,
        phone: '0987654321',
        role: GroupRole.manager,
        cameraIds: ['cam_charger'],
      );
      expect(server.body('POST', '/groups/$_gid/invitations'), {
        'phone_number': '0987654321',
        'role': 'MEMBER_MANAGER',
        'nickname': null,
        'camera_ids': null,
      });
      expect(m.cameraIds, isNull);
    });

    test('invite errors: PHONE_NOT_REGISTERED, ALREADY_IN_GROUP', () async {
      Future<Member> invite() => repo.inviteMember(
        groupId: _gid,
        phone: '0911222333',
        role: GroupRole.member,
        cameraIds: const [],
      );
      server.fail(
        'POST',
        '/groups/$_gid/invitations',
        404,
        'PHONE_NOT_REGISTERED',
      );
      await expectLater(invite(), throwsA(isA<PhoneNotRegisteredException>()));
      server.fail('POST', '/groups/$_gid/invitations', 409, 'ALREADY_IN_GROUP');
      await expectLater(invite(), throwsA(isA<AlreadyInGroupException>()));
      server.fail(
        'POST',
        '/groups/$_gid/invitations',
        403,
        'PERMISSION_DENIED',
      );
      await expectLater(invite(), throwsA(isA<PermissionDeniedException>()));
    });

    test('set role: PATCH, then the member read back', () async {
      server
        ..on('PATCH', '/groups/$_gid/members/usr_tuan/role', {
          'user_id': 'usr_tuan',
          'role': 'NOTIFIER',
        })
        ..on('GET', '/groups/$_gid/members', _membersJson);
      final m = await repo.setRole(
        groupId: _gid,
        memberId: 'usr_tuan',
        role: GroupRole.alertsOnly,
      );
      expect(server.body('PATCH', '/groups/$_gid/members/usr_tuan/role'), {
        'role': 'NOTIFIER',
      });
      expect(server.calls.last, 'GET /groups/$_gid/members');
      expect(m.id, 'usr_tuan');
    });

    test('camera access: PUT one camera at a time', () async {
      server
        ..on('PUT', '/groups/$_gid/members/usr_tuan/cameras', {
          'user_id': 'usr_tuan',
          'camera_ids': ['cam_charger'],
        })
        ..on('GET', '/groups/$_gid/members', _membersJson);
      final m = await repo.setCameraAccess(
        groupId: _gid,
        memberId: 'usr_tuan',
        cameraId: 'cam_charger',
        enabled: true,
      );
      expect(server.body('PUT', '/groups/$_gid/members/usr_tuan/cameras'), {
        'camera_id': 'cam_charger',
        'enabled': true,
      });
      expect(m.cameraIds, ['cam_charger']);
    });

    test('nickname: a name, or null to use the real name', () async {
      server
        ..on('PATCH', '/groups/$_gid/members/usr_me/nickname', {
          'user_id': 'usr_me',
          'nickname': null,
        })
        ..on('GET', '/groups/$_gid/members', _membersJson);
      final m = await repo.setNickname(groupId: _gid, memberId: 'usr_me');
      expect(server.body('PATCH', '/groups/$_gid/members/usr_me/nickname'), {
        'nickname': null,
      });
      expect(m.nickname, isNull);
      expect(m.isYou, isTrue);
    });

    test('remove: DELETE the member', () async {
      server.on('DELETE', '/groups/$_gid/members/usr_bin', {
        'status': 'success',
      });
      await repo.removeMember(groupId: _gid, memberId: 'usr_bin');
      expect(server.calls, ['DELETE /groups/$_gid/members/usr_bin']);
    });
  });

  group('invitations', () {
    test('GET my-invitations (contract §6.2)', () async {
      server.on('GET', '/invitations/my-invitations', [_myInvitationJson]);
      final list = await repo.listMyInvitations();
      final inv = list.single;
      expect(inv.id, 'inv_987654');
      expect(inv.groupId, 'grp_sky_garden_01');
      expect(inv.groupName, 'Chung cư Sky Garden');
      expect(inv.groupAddress, '12 Nguyễn Văn Linh, Q.7, TP.HCM');
      expect(inv.inviterName, 'Trần Thị Lan');
      expect(inv.role, GroupRole.member);
      expect(inv.nickname, 'Anh Hùng Kỹ Thuật');
      expect(inv.cameraCount, 2);
      expect(inv.cameraNames, ['Hầm B1 · Khu sạc xe', 'Cổng chính']);
      expect(inv.createdAt, DateTime.utc(2026, 11, 4, 12).toLocal());
    });

    test('GET one; no created_at in the router reply', () async {
      server.on('GET', '/invitations/inv_987654', {
        ..._myInvitationJson,
        'created_at': null,
      });
      final inv = await repo.getInvitation('inv_987654');
      expect(inv.groupName, 'Chung cư Sky Garden');
      expect(inv.createdAt, isNull);
    });

    test(
      'member_count of the group (J7 "· 8 người"), null when absent',
      () async {
        server.on('GET', '/invitations/my-invitations', [
          {..._myInvitationJson, 'member_count': 8},
          _myInvitationJson,
        ]);
        final list = await repo.listMyInvitations();
        expect(list.first.memberCount, 8);
        expect(list.last.memberCount, isNull);
      },
    );

    test('INVITATION_UNAVAILABLE on get, accept and decline', () async {
      for (final (method, path) in [
        ('GET', '/invitations/inv_old'),
        ('POST', '/invitations/inv_old/accept'),
        ('POST', '/invitations/inv_old/decline'),
      ]) {
        server.fail(method, path, 410, 'INVITATION_UNAVAILABLE');
      }
      final matcher = throwsA(isA<InvitationUnavailableException>());
      await expectLater(repo.getInvitation('inv_old'), matcher);
      await expectLater(repo.acceptInvitation('inv_old'), matcher);
      await expectLater(repo.declineInvitation('inv_old'), matcher);
    });

    test('accept with a nickname → the joined group', () async {
      server.on('POST', '/invitations/inv_987654/accept', {
        'group_id': 'grp_sky_garden_01',
        'group_name': 'Chung cư Sky Garden',
        'is_personal': false,
        'address': '12 Nguyễn Văn Linh, Q.7, TP.HCM',
        'member_count': 5,
        'camera_count': 2,
        'my_role': 'MEMBER',
        'my_nickname': 'Hùng Kỹ Thuật',
      });
      final g = await repo.acceptInvitation(
        'inv_987654',
        nickname: 'Hùng Kỹ Thuật',
      );
      expect(server.body('POST', '/invitations/inv_987654/accept'), {
        'nickname': 'Hùng Kỹ Thuật',
      });
      expect(g.myRole, GroupRole.member);
      expect(g.myNickname, 'Hùng Kỹ Thuật');
      expect(g.memberCount, 5);
    });

    test('decline', () async {
      server.on('POST', '/invitations/inv_987654/decline', {
        'status': 'declined',
      });
      await repo.declineInvitation('inv_987654');
      expect(server.calls, ['POST /invitations/inv_987654/decline']);
    });
  });

  group('edit group (PATCH /groups/{id})', () {
    test('sends only the given fields, then reads the group back', () async {
      server
        ..on('PATCH', '/groups/$_gid', {
          'group_id': _gid,
          'group_name': 'Sky Garden 2',
          'is_personal': false,
          'address': '99 Nguyễn Văn Linh, Q.7',
          'member_count': 4,
          'camera_count': 2,
        })
        ..on('GET', '/groups', [
          {
            'group_id': 'grp_personal_usr_lan',
            'group_name': 'Nhóm Cá Nhân',
            'is_personal': true,
            'address': null,
            'member_count': 1,
            'camera_count': 0,
            'my_role': 'LEADER',
            'my_nickname': 'Tôi',
          },
          {
            'group_id': _gid,
            'group_name': 'Sky Garden 2',
            'is_personal': false,
            'address': '99 Nguyễn Văn Linh, Q.7',
            'member_count': 4,
            'camera_count': 2,
            'my_role': 'LEADER',
            'my_nickname': 'Chị Lan',
          },
        ]);
      final g = await repo.updateGroup(
        groupId: _gid,
        address: '99 Nguyễn Văn Linh, Q.7',
      );
      expect(server.calls, ['PATCH /groups/$_gid', 'GET /groups']);
      expect(server.body('PATCH', '/groups/$_gid'), {
        'address': '99 Nguyễn Văn Linh, Q.7',
      });
      expect(g.name, 'Sky Garden 2');
      expect(g.address, '99 Nguyễn Văn Linh, Q.7');
      expect(g.myRole, GroupRole.owner);
      expect(g.myNickname, 'Chị Lan');
    });

    test('not the owner: 403 → PermissionDeniedException', () async {
      server.fail('PATCH', '/groups/$_gid', 403, 'PERMISSION_DENIED');
      await expectLater(
        repo.updateGroup(groupId: _gid, name: 'Khác'),
        throwsA(isA<PermissionDeniedException>()),
      );
      expect(server.calls, ['PATCH /groups/$_gid']);
    });
  });

  test('revoke invitation → DELETE /groups/{g}/invitations/{id}', () async {
    server.on('DELETE', '/groups/$_gid/invitations/inv_555', {
      'status': 'success',
      'message': 'Đã thu hồi lời mời thành công',
    });
    await repo.revokeInvitation(groupId: _gid, invitationId: 'inv_555');
    expect(server.calls, ['DELETE /groups/$_gid/invitations/inv_555']);
  });

  group('audit log', () {
    test('GET …/audit-logs?limit=: items, newest first as sent', () async {
      server.on('GET', '/groups/$_gid/audit-logs', {
        'group_id': _gid,
        'items': [
          {
            'log_id': 'log_2',
            'action': 'CAMERA_DELETED',
            'actor_id': 'usr_lan',
            'target_entity': 'camera:cam_old',
            'details': {'cam_name': 'Cổng sau'},
            'created_at': '2026-11-05 08:30:00+00:00',
          },
          {
            'log_id': 'log_1',
            'action': 'MEMBER_INVITED',
            'actor_id': null,
            'target_entity': null,
            'details': null,
            'created_at': null,
          },
        ],
        'total': 2,
      });
      final log = await repo.listAuditLog(_gid, limit: 20);
      expect(
        server.request('GET', '/groups/$_gid/audit-logs').url.queryParameters,
        {'limit': '20'},
      );
      expect(log.map((e) => e.id), ['log_2', 'log_1']);
      final first = log.first;
      expect(first.action, 'CAMERA_DELETED');
      expect(first.actorId, 'usr_lan');
      expect(first.target, 'camera:cam_old');
      expect(first.details, {'cam_name': 'Cổng sau'});
      expect(first.createdAt, DateTime.utc(2026, 11, 5, 8, 30).toLocal());
      expect(log.last.details, isEmpty);
      expect(log.last.createdAt, isNull);
    });

    test('a member: 403 → PermissionDeniedException', () async {
      server.fail('GET', '/groups/$_gid/audit-logs', 403, 'PERMISSION_DENIED');
      await expectLater(
        repo.listAuditLog(_gid),
        throwsA(isA<PermissionDeniedException>()),
      );
    });
  });
}
