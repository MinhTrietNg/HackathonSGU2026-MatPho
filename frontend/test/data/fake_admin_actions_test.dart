library;

import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/models.dart';

import '../fakes/fake_alert_repository.dart';
import '../fakes/fake_camera_repository.dart';
import '../fakes/fake_data.dart';
import '../fakes/fake_group_repository.dart';
import '../fakes/fake_scenario.dart';
import '../fakes/fake_world.dart';

const _sky = 'g-sky';
const _office = 'g-office';

FakeWorld _world() => FakeWorld(const FakeScenario.test());

void main() {
  group('cameras', () {
    test('edit changes only the given fields', () async {
      final world = _world();
      final r = FakeCameraRepository(world);
      final before = await r.getCamera('cam-charger');
      final after = await r.updateCamera(
        cameraId: 'cam-charger',
        name: 'Khu sạc mới',
        areaId: 'a-lobby',
      );
      expect(after.name, 'Khu sạc mới');
      expect(after.areaId, 'a-lobby');
      expect(after.watchArea, before.watchArea);
      expect((await r.getCamera('cam-charger')).name, 'Khu sạc mới');
    });

    test('the AI mode is saved and kept on the next read', () async {
      final r = FakeCameraRepository(_world());
      expect((await r.getCamera('cam-living')).ai, CameraAi.alwaysOn);
      expect((await r.getCamera('cam-kitchen')).ai, FakeData.cookingPause);

      final after = await r.updateCamera(
        cameraId: 'cam-living',
        ai: CameraAi.off,
      );
      expect(after.ai, CameraAi.off);
      expect((await r.getCamera('cam-living')).ai, CameraAi.off);

      final renamed = await r.updateCamera(cameraId: 'cam-kitchen', name: 'X');
      expect(renamed.ai, FakeData.cookingPause);
    });

    test('a member cannot edit, delete or open the trash', () async {
      final r = FakeCameraRepository(_world());
      await expectLater(
        r.updateCamera(cameraId: 'cam-store', name: 'X'),
        throwsA(isA<PermissionDeniedException>()),
      );
      await expectLater(
        r.deleteCamera('cam-store'),
        throwsA(isA<PermissionDeniedException>()),
      );
      await expectLater(
        r.listTrash(_office),
        throwsA(isA<PermissionDeniedException>()),
      );
    });

    test('delete → trash (30 days) → restore', () async {
      final world = _world();
      final r = FakeCameraRepository(world);
      final count = world.group(_sky).cameraCount;

      await r.deleteCamera('cam-down');
      expect(
        (await r.listCameras(_sky)).map((c) => c.id),
        isNot(contains('cam-down')),
      );
      expect(world.group(_sky).cameraCount, count - 1);
      final trashed = (await r.listTrash(_sky)).single;
      expect(trashed.id, 'cam-down');
      expect(trashed.areaName, 'Hầm B2');
      expect(trashed.purgeAt, trashed.deletedAt!.add(const Duration(days: 30)));

      final back = await r.restoreCamera('cam-down');
      expect(back.areaId, 'a-b2');
      expect(await r.listTrash(_sky), isEmpty);
      expect(
        (await r.listCameras(_sky)).map((c) => c.id),
        contains('cam-down'),
      );
      expect(world.group(_sky).cameraCount, count);
    });

    test('delete forever: owner only, from the trash or not', () async {
      final world = _world();
      final r = FakeCameraRepository(world);
      await r.deleteCamera('cam-down');
      await r.deleteCameraForever('cam-down');
      expect(await r.listTrash(_sky), isEmpty);

      await r.deleteCameraForever('cam-ramp');
      expect(
        (await r.listCameras(_sky)).map((c) => c.id),
        isNot(contains('cam-ramp')),
      );

      await expectLater(
        r.deleteCameraForever('cam-store'),
        throwsA(isA<PermissionDeniedException>()),
      );
    });

    test('an area is deleted only once empty', () async {
      final r = FakeCameraRepository(_world());
      await expectLater(
        r.deleteArea(groupId: _sky, areaId: 'a-b1'),
        throwsA(isA<AreaNotEmptyException>()),
      );
      await r.deleteArea(groupId: _sky, areaId: 'a-lobby');
      expect(
        (await r.listAreas(_sky)).map((a) => a.id),
        isNot(contains('a-lobby')),
      );
    });
  });

  group('groups', () {
    test('the owner renames the place and sets its address', () async {
      final world = _world();
      final r = FakeGroupRepository(world);
      final g = await r.updateGroup(
        groupId: _sky,
        address: '12 Nguyễn Văn Linh, Q.7',
      );
      expect(g.name, FakeData.skyGarden.name);
      expect(g.address, '12 Nguyễn Văn Linh, Q.7');
      expect(world.group(_sky).address, '12 Nguyễn Văn Linh, Q.7');

      await expectLater(
        r.updateGroup(groupId: _office, name: 'Khác'),
        throwsA(isA<PermissionDeniedException>()),
      );
    });

    test('revoke withdraws a pending invitation only', () async {
      final world = _world();
      final r = FakeGroupRepository(world);
      final count = world.group(_sky).memberCount;
      await r.revokeInvitation(groupId: _sky, invitationId: 'm-pending');
      expect(
        (await r.listMembers(_sky)).map((m) => m.id),
        isNot(contains('m-pending')),
      );
      expect(world.group(_sky).memberCount, count - 1);

      await expectLater(
        r.revokeInvitation(groupId: _sky, invitationId: 'm-tuan'),
        throwsA(isA<ServerException>()),
      );
    });
  });

  group('alerts', () {
    FireEvent alertAgo(FakeWorld world, Duration ago) {
      final e = FireEvent(
        id: 'evt-open',
        cameraId: 'cam-charger',
        locationName: 'Hầm B1',
        status: EventStatus.fire,
        detectedAt: world.now().subtract(ago),
        summary: 'Lửa ở xe máy',
      );
      world.addEvent(e);
      return e;
    }

    test('escalation counts down 60 s, then everyone is rung', () async {
      final world = _world();
      final r = FakeAlertRepository(world);
      alertAgo(world, const Duration(seconds: 20));
      expect(
        await r.escalationStatus('evt-open'),
        const EscalationStatus(
          eventId: 'evt-open',
          timerActive: true,
          remaining: Duration(seconds: 40),
          level: 0,
        ),
      );

      world.events.clear();
      alertAgo(world, const Duration(seconds: 90));
      final late = await r.escalationStatus('evt-open');
      expect(late.timerActive, isFalse);
      expect(late.remaining, Duration.zero);
      expect(late.level, 1);
    });

    test('calling 114 stops the countdown', () async {
      final world = _world();
      final r = FakeAlertRepository(world);
      alertAgo(world, const Duration(seconds: 5));
      await r.recordCall114('evt-open');
      expect((await r.escalationStatus('evt-open')).timerActive, isFalse);
    });

    test('dispatch info: the place and its owner / managers', () async {
      final world = _world();
      final r = FakeAlertRepository(world);
      alertAgo(world, const Duration(seconds: 5));
      final d = await r.dispatchInfo('evt-open');
      expect(d.facilityName, FakeData.skyGarden.name);
      expect(d.locationName, 'Hầm B1');
      expect(d.cameraName, 'Khu sạc xe');
      expect(d.callScript, contains('Hầm B1'));
      expect(d.contacts.map((c) => c.role), [
        GroupRole.owner,
        GroupRole.manager,
      ]);
    });
  });
}
