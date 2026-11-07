import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/errors.dart';
import '../fakes/fake_camera_repository.dart';
import '../fakes/fake_data.dart';
import '../fakes/fake_group_repository.dart';
import '../fakes/fake_scenario.dart';
import '../fakes/fake_world.dart';
import 'package:mat_pho/data/models/models.dart';

FakeWorld world([Set<FakeCase> cases = const {}]) =>
    FakeWorld(FakeScenario.test(cases: cases));

void main() {
  test('my groups (J7 / I13)', () async {
    final groups = await FakeGroupRepository(world()).listGroups();
    expect(groups.map((g) => (g.name, g.myNickname, g.myRole)), [
      ('Chung cư Sky Garden', 'Minh Anh', GroupRole.owner),
      ('Nhà mình', 'Ba', GroupRole.owner),
      ('Văn phòng công ty', 'Minh Anh', GroupRole.member),
      ('Cá Nhân', 'Nguyễn Minh Anh', GroupRole.owner),
    ]);
    expect(groups.map((g) => (g.cameraCount, g.memberCount)), [
      (5, 4),
      (3, 4),
      (2, 3),
      (0, 1),
    ]);
    expect(groups.map((g) => g.isPersonal), [false, false, false, true]);
    expect(groups.last, FakeData.personalGroupOf(FakeData.user));
    expect(groups.last.id, 'g-personal-u-minh-anh');
  });

  group('the personal group', () {
    const id = 'g-personal-u-minh-anh';

    test('only you are in it, with no area', () async {
      final w = world();
      final members = await FakeGroupRepository(w).listMembers(id);
      expect(members.map((m) => (m.displayName, m.role, m.isYou)), [
        ('Nguyễn Minh Anh', GroupRole.owner, true),
      ]);
      expect(await FakeCameraRepository(w).listAreas(id), isEmpty);
    });

    test('cannot be invited into, left or dissolved', () async {
      final r = FakeGroupRepository(world());
      for (final change in [
        () => r.inviteMember(
          groupId: id,
          phone: '0987654321',
          role: GroupRole.member,
          cameraIds: const [],
        ),
        () => r.leaveGroup(id),
        () => r.dissolveGroup(id),
      ]) {
        await expectLater(change(), throwsA(isA<PermissionDeniedException>()));
      }
      expect((await r.listGroups()).last.id, id);
      expect(await r.listMembers(id), hasLength(1));
    });

    test('a camera can be saved into it after I9', () async {
      final cameras = FakeCameraRepository(world());
      final area = await cameras.createArea(groupId: id, name: 'Phòng khách');
      final camera = await cameras.saveCamera(
        groupId: id,
        rtspUrl: 'rtsp://10.0.0.9:554/stream1',
        name: 'Cửa chính',
        areaId: area.id,
        watchArea: WatchArea.full,
      );
      expect(camera.groupId, id);
      expect((await cameras.listCameras(id)).single.name, 'Cửa chính');
    });
  });

  test('members verbatim (J1, J6, J13)', () async {
    final r = FakeGroupRepository(world());
    final sky = await r.listMembers('g-sky');
    expect(sky.map((m) => m.displayName), [
      'Minh Anh',
      'Phạm Thị Lan',
      'Chú Tuấn bảo vệ',
      'Bảo vệ ca đêm',
    ]);
    expect(maskPhone(sky.last.phone), '0903 ••• 112');
    expect(sky.last.pending, isTrue);
    expect(sky.last.nickname, 'Bảo vệ ca đêm');
    expect(sky.first.isYou, isTrue);

    final home = await r.listMembers('g-home');
    expect(home.map((m) => (m.displayName, m.role)), [
      ('Ba', GroupRole.owner),
      ('Mẹ', GroupRole.manager),
      ('Bin (con)', GroupRole.alertsOnly),
      ('Bé Na (con)', GroupRole.member),
    ]);

    final office = await r.listMembers('g-office');
    expect(office.map((m) => (m.displayName, m.note)), [
      ('Anh Long', 'Giám đốc'),
      ('Chị Mai', 'Phụ trách IT'),
      ('Minh Anh', null),
    ]);
  });

  test('invite (J2) adds a pending member and bumps the count', () async {
    final r = FakeGroupRepository(world());
    final m = await r.inviteMember(
      groupId: 'g-sky',
      phone: '0909 000 001',
      role: GroupRole.member,
      cameraIds: ['cam-charger'],
    );
    expect(m.pending, isTrue);
    expect(m.phone, '0909000001');
    expect(m.nickname, isNull);
    final named = await r.inviteMember(
      groupId: 'g-sky',
      phone: '0987654321',
      role: GroupRole.member,
      cameraIds: ['cam-charger'],
      nickname: 'Bảo vệ ca đêm',
    );
    expect(named.nickname, 'Bảo vệ ca đêm');
    expect((await r.listGroups()).first.memberCount, 6);
  });

  test('a member cannot invite or dissolve; owner cannot leave', () async {
    final r = FakeGroupRepository(world());
    await expectLater(
      r.inviteMember(
        groupId: 'g-office',
        phone: '0903456112',
        role: GroupRole.member,
        cameraIds: const [],
      ),
      throwsA(isA<PermissionDeniedException>()),
    );
    await expectLater(
      r.dissolveGroup('g-office'),
      throwsA(isA<PermissionDeniedException>()),
    );
    await expectLater(
      r.leaveGroup('g-sky'),
      throwsA(isA<PermissionDeniedException>()),
    );
  });

  test('leave (J14) and dissolve (J15)', () async {
    final r = FakeGroupRepository(world());
    await r.leaveGroup('g-office');
    await r.dissolveGroup('g-home');
    expect((await r.listGroups()).map((g) => g.name), [
      'Chung cư Sky Garden',
      'Cá Nhân',
    ]);
  });

  test('roles and per-camera access (J4)', () async {
    final r = FakeGroupRepository(world());
    var tuan = await r.setCameraAccess(
      groupId: 'g-sky',
      memberId: 'm-tuan',
      cameraId: 'cam-down',
      enabled: false,
    );
    expect(tuan.cameraIds, ['cam-charger', 'cam-ramp']);
    tuan = await r.setRole(
      groupId: 'g-sky',
      memberId: 'm-tuan',
      role: GroupRole.manager,
    );
    expect(tuan.role, GroupRole.manager);
    expect(tuan.cameraIds, isNull);
    await expectLater(
      r.setCameraAccess(
        groupId: 'g-sky',
        memberId: 'm-tuan',
        cameraId: 'cam-ramp',
        enabled: false,
      ),
      throwsA(isA<PermissionDeniedException>()),
    );
  });

  test('revoke (J5)', () async {
    final r = FakeGroupRepository(world());
    await r.removeMember(groupId: 'g-sky', memberId: 'm-tuan');
    final names = (await r.listMembers('g-sky')).map((m) => m.displayName);
    expect(names, isNot(contains('Chú Tuấn bảo vệ')));
    expect((await r.listGroups()).first.memberCount, 3);
  });

  test('nicknames (J11, J12)', () async {
    final r = FakeGroupRepository(world());
    final tuan = await r.setNickname(
      groupId: 'g-sky',
      memberId: 'm-tuan',
      nickname: null,
    );
    expect(tuan.displayName, 'Trần Anh Tuấn');
    await r.setNickname(
      groupId: 'g-sky',
      memberId: 'm-you-sky',
      nickname: 'Chị Minh Anh',
    );
    expect((await r.listGroups()).first.myNickname, 'Chị Minh Anh');
  });

  test('J11: only the owner renames someone else; J12: anyone, self', () async {
    final w = world();
    w.replaceGroup(
      const Group(
        id: 'g-sky',
        name: 'Chung cư Sky Garden',
        myRole: GroupRole.manager,
        myNickname: 'Minh Anh',
        cameraCount: 5,
        memberCount: 4,
      ),
    );
    final r = FakeGroupRepository(w);
    await expectLater(
      r.setNickname(groupId: 'g-sky', memberId: 'm-tuan', nickname: 'Tuấn'),
      throwsA(isA<PermissionDeniedException>()),
    );
    await expectLater(
      r.setNickname(groupId: 'g-office', memberId: 'm-mai', nickname: 'Mai'),
      throwsA(isA<PermissionDeniedException>()),
    );
    final me = await r.setNickname(
      groupId: 'g-sky',
      memberId: 'm-you-sky',
      nickname: 'Chị Minh Anh',
    );
    expect(me.displayName, 'Chị Minh Anh');
    final office = await r.setNickname(
      groupId: 'g-office',
      memberId: 'm-me-office',
      nickname: 'Anh Minh',
    );
    expect(office.displayName, 'Anh Minh');
  });

  test('create group (J8): empty, owned by you', () async {
    final w = world();
    final r = FakeGroupRepository(w);
    final g = await r.createGroup(name: 'Nhà mới');
    expect(g.myRole, GroupRole.owner);
    expect(g.myNickname, 'Nguyễn Minh Anh');
    expect(g.cameraCount, 0);
    expect(g.isPersonal, isFalse);
    expect(await FakeCameraRepository(w).listCameras(g.id), isEmpty);
    final named = await r.createGroup(name: 'Cửa hàng', myNickname: 'Chủ');
    expect(named.myNickname, 'Chủ');
    expect((await r.listMembers(named.id)).single.displayName, 'Chủ');
  });

  test('invitation (J3)', () async {
    final r = FakeGroupRepository(world());
    final inv = await r.getInvitation('inv-riverside');
    expect(inv.inviterName, 'Chị Hoa');
    expect(inv.groupName, 'Chung cư Riverside');
    expect(inv.role, GroupRole.member);
    expect(inv.nickname, 'Minh Anh tầng 5');
    expect(inv.cameraNames, ['Hầm B1', 'Hầm B2']);
    expect((await r.acceptInvitation('inv-riverside')).id, 'g-riverside');
    await r.declineInvitation('inv-riverside');
  });

  test("accepting (J3) without a name takes the inviter's", () async {
    final w = world();
    final r = FakeGroupRepository(w);
    final g = await r.acceptInvitation('inv-riverside');
    expect(g.myNickname, 'Minh Anh tầng 5');
    expect((await r.listMembers(g.id)).single.displayName, 'Minh Anh tầng 5');
  });

  test('accepting (J3) gives only the invited role, never all cameras', () {
    final r = FakeGroupRepository(world());
    return r.acceptInvitation('inv-riverside').then((g) async {
      expect(g.myRole, GroupRole.member);
      final me = (await r.listMembers(g.id)).single;
      expect(me.cameraIds, isEmpty);
      await expectLater(
        r.acceptInvitation('inv-riverside'),
        throwsA(isA<InvitationUnavailableException>()),
      );
    });
  });

  group('J4 / J5 rules', () {
    test('nobody becomes a second owner', () async {
      final r = FakeGroupRepository(world());
      await expectLater(
        r.setRole(groupId: 'g-sky', memberId: 'm-lan', role: GroupRole.owner),
        throwsA(isA<PermissionDeniedException>()),
      );
    });

    test('the owner and yourself are not changed or removed', () async {
      final r = FakeGroupRepository(world());
      for (final change in [
        () => r.setRole(
          groupId: 'g-sky',
          memberId: 'm-you-sky',
          role: GroupRole.member,
        ),
        () => r.removeMember(groupId: 'g-sky', memberId: 'm-you-sky'),
        () => r.setRole(
          groupId: 'g-office',
          memberId: 'm-long',
          role: GroupRole.member,
        ),
      ]) {
        await expectLater(change(), throwsA(isA<PermissionDeniedException>()));
      }
      expect((await r.listMembers('g-sky')).first.isYou, isTrue);
    });

    test('a demoted manager keeps today\'s cameras as a list', () async {
      final r = FakeGroupRepository(world());
      final lan = await r.setRole(
        groupId: 'g-sky',
        memberId: 'm-lan',
        role: GroupRole.member,
      );
      expect(lan.cameraIds, ['cam-charger', 'cam-ramp', 'cam-down']);
    });

    test('a manager has every camera: nothing to toggle', () async {
      final r = FakeGroupRepository(world());
      await expectLater(
        r.setCameraAccess(
          groupId: 'g-sky',
          memberId: 'm-lan',
          cameraId: 'cam-charger',
          enabled: false,
        ),
        throwsA(isA<PermissionDeniedException>()),
      );
    });

    test('a pending invite can be withdrawn', () async {
      final r = FakeGroupRepository(world());
      await r.removeMember(groupId: 'g-sky', memberId: 'm-pending');
      expect((await r.listGroups()).first.memberCount, 3);
    });

    test('invite: a manager is stored with every camera', () async {
      final r = FakeGroupRepository(world());
      final m = await r.inviteMember(
        groupId: 'g-sky',
        phone: '0987654321',
        role: GroupRole.manager,
        cameraIds: const ['cam-charger'],
      );
      expect(m.cameraIds, isNull);
    });
  });

  test('accepting (J3) with a name of your own keeps it', () async {
    final w = world();
    final r = FakeGroupRepository(w);
    final g = await r.acceptInvitation('inv-riverside', nickname: 'Anh Ba');
    expect(g.myNickname, 'Anh Ba');
  });
}
