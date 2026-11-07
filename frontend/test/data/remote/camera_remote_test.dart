import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/data/remote/camera_remote.dart';

import 'group_camera_server.dart';

const _gid = 'grp_sky_garden_01';

const _detailJson = {
  'cam_id': 'cam_charger',
  'cam_name': 'Hầm B1 · Khu sạc xe',
  'group_id': 'grp_sky_garden_01',
  'subgroup_id': 'sub_b1',
  'subgroup_name': 'Hầm B1',
  'device_name': 'Hikvision DS-2CD2143G2-I',
  'status': 'ONLINE',
  'last_seen_at': '2026-11-04T12:00:00.000Z',
  'live_stream_url': 'https://stream.matpho.vn/live/cam_charger/index.m3u8',
  'watch_area': {'left': 0.15, 'top': 0.20, 'width': 0.70, 'height': 0.65},
  'notified_names': ['Trần Thị Lan', 'Bác Ba Bảo Vệ', 'Anh Hùng Kỹ Thuật'],
};

const _rtsp =
    'rtsp://admin:MatKhau123@192.168.1.100:554/Streaming/Channels/101';

void main() {
  late GroupCameraServer server;
  late RemoteCameraRepository repo;

  setUp(() {
    server = GroupCameraServer();
    repo = RemoteCameraRepository(server.api);
  });

  group('list cameras', () {
    test(
      'one GET /cameras?group_id=: status, last_seen_at, stream, box',
      () async {
        server.on('GET', '/cameras', camerasJson);
        final cameras = await repo.listCameras(_gid);
        expect(server.calls, ['GET /cameras']);
        expect(server.request('GET', '/cameras').url.queryParameters, {
          'group_id': _gid,
        });

        final charger = cameras.first;
        expect(charger.id, 'cam_charger');
        expect(charger.name, 'Hầm B1 · Khu sạc xe');
        expect(charger.groupId, _gid);
        expect(charger.areaId, 'sub_b1');
        expect(charger.deviceName, 'Hikvision DS-2CD2143G2-I');
        expect(charger.status, CameraStatus.watching);
        expect(charger.signalLostSince, isNull);
        expect(
          charger.liveStreamUrl,
          'https://stream.matpho.vn/live/cam_charger/index.m3u8',
        );
        expect(charger.rtspUrl, isNull);
        expect(
          charger.watchArea,
          const WatchArea(left: 0.15, top: 0.20, width: 0.70, height: 0.65),
        );

        final down = cameras.last;
        expect(down.status, CameraStatus.signalLost);
        expect(
          down.signalLostSince,
          DateTime.utc(2026, 11, 4, 14, 30).toLocal(),
        );
        expect(down.liveStreamUrl, isNull);
        expect(down.deviceName, isNull);
        expect(down.watchArea, WatchArea.full);
      },
    );

    test('"None" for a missing time is no time', () async {
      server.on('GET', '/cameras', [
        {...camerasJson.last, 'last_seen_at': 'None'},
      ]);
      final camera = (await repo.listCameras(_gid)).single;
      expect(camera.status, CameraStatus.signalLost);
      expect(camera.signalLostSince, isNull);
    });

    test('an unknown status reads as signal lost', () async {
      server.on('GET', '/cameras', [
        {...camerasJson.first, 'status': 'SLEEPING'},
      ]);
      final camera = (await repo.listCameras(_gid)).single;
      expect(camera.status, CameraStatus.signalLost);
    });

    test('PERMISSION_DENIED → PermissionDeniedException', () async {
      server.fail('GET', '/cameras', 403, 'PERMISSION_DENIED');
      await expectLater(
        repo.listCameras(_gid),
        throwsA(isA<PermissionDeniedException>()),
      );
    });
  });

  test('GET /cameras/{id} (contract §8.4)', () async {
    server.on('GET', '/cameras/cam_charger', _detailJson);
    final camera = await repo.getCamera('cam_charger');
    expect(server.calls, ['GET /cameras/cam_charger']);
    expect(camera.id, 'cam_charger');
    expect(camera.groupId, _gid);
    expect(camera.status, CameraStatus.watching);
    expect(camera.liveStreamUrl, isNotNull);
  });

  group('areas', () {
    test('GET subgroups → areas of the group', () async {
      server.on('GET', '/groups/$_gid/subgroups', [
        {
          'subgroup_id': 'sub_b1',
          'name': 'Hầm B1',
          'description': null,
          'camera_count': 2,
        },
        {
          'subgroup_id': 'sub_b2',
          'name': 'Hầm B2',
          'description': 'Tầng hầm 2',
          'camera_count': 1,
        },
      ]);
      final areas = await repo.listAreas(_gid);
      expect(areas, const [
        Area(id: 'sub_b1', groupId: _gid, name: 'Hầm B1'),
        Area(id: 'sub_b2', groupId: _gid, name: 'Hầm B2'),
      ]);
    });

    test('POST subgroups (I9)', () async {
      server.on('POST', '/groups/$_gid/subgroups', {
        'subgroup_id': 'sub_new',
        'name': 'Kho Nhiên Liệu',
        'description': null,
        'camera_count': 0,
      }, status: 201);
      final area = await repo.createArea(groupId: _gid, name: 'Kho Nhiên Liệu');
      expect(server.body('POST', '/groups/$_gid/subgroups'), {
        'name': 'Kho Nhiên Liệu',
      });
      expect(
        area,
        const Area(id: 'sub_new', groupId: _gid, name: 'Kho Nhiên Liệu'),
      );
    });
  });

  group('probe (I2 → I4 / I5)', () {
    test('200: device name and the preview picture', () async {
      server.on('POST', '/cameras/probe', {
        'device_name': 'Hikvision DS-2CD2143G2-I',
        'resolution': '1920x1080',
        'fps': 25,
        'preview_snapshot_url':
            'http://api.matpho.vn/snapshots/temp_probe_99a.jpg',
      });
      final probe = await repo.connect(_rtsp);
      expect(server.body('POST', '/cameras/probe'), {'rtsp_url': _rtsp});
      expect(probe.rtspUrl, _rtsp);
      expect(probe.deviceName, 'Hikvision DS-2CD2143G2-I');
      expect(
        probe.previewSnapshotUrl,
        'http://api.matpho.vn/snapshots/temp_probe_99a.jpg',
      );
    });

    test('the four I4 failures carry the device name, else the host', () async {
      final cases = <String, Matcher>{
        'CAMERA_NO_RESPONSE': isA<CameraNoResponseException>(),
        'CAMERA_AUTH_FAILED': isA<CameraAuthFailedException>(),
        'CAMERA_NOT_REACHABLE': isA<NotOnCompanyWifiException>(),
        'CAMERA_VENDOR_BLOCKED': isA<VendorBlockedException>(),
      };
      for (final MapEntry(key: code, value: kind) in cases.entries) {
        server.fail('POST', '/cameras/probe', 400, code, {
          'device_name': 'Hikvision',
          'host': '192.168.1.100',
        });
        await expectLater(
          repo.connect(_rtsp),
          throwsA(
            allOf(
              kind,
              isA<CameraConnectException>().having(
                (e) => e.cameraName,
                'cameraName',
                'Hikvision',
              ),
            ),
          ),
        );
      }
      server.fail('POST', '/cameras/probe', 400, 'CAMERA_NO_RESPONSE', {
        'host': '192.168.1.100',
      });
      await expectLater(
        repo.connect(_rtsp),
        throwsA(
          isA<CameraNoResponseException>().having(
            (e) => e.cameraName,
            'cameraName',
            '192.168.1.100',
          ),
        ),
      );
    });
  });

  test('save (I5): every field of contract §8.2', () async {
    server.on('POST', '/cameras', {
      ..._detailJson,
      'created_at': '2026-11-04T12:00:00.000Z',
    }, status: 201);
    final camera = await repo.saveCamera(
      groupId: _gid,
      rtspUrl: _rtsp,
      name: 'Hầm B1 · Khu sạc xe',
      areaId: 'sub_b1',
      watchArea: const WatchArea(
        left: 0.15,
        top: 0.2,
        width: 0.7,
        height: 0.65,
      ),
      deviceName: 'Hikvision DS-2CD2143G2-I',
    );
    expect(server.body('POST', '/cameras'), {
      'group_id': _gid,
      'subgroup_id': 'sub_b1',
      'cam_name': 'Hầm B1 · Khu sạc xe',
      'device_name': 'Hikvision DS-2CD2143G2-I',
      'rtsp_url': _rtsp,
      'watch_area': {'left': 0.15, 'top': 0.2, 'width': 0.7, 'height': 0.65},
    });
    expect(camera.id, 'cam_charger');
    expect(camera.areaId, 'sub_b1');
  });

  group('reconnect (I8)', () {
    test('a whole camera in the reply is used as is', () async {
      server.on('POST', '/cameras/cam_charger/reconnect', _detailJson);
      final camera = await repo.reconnect('cam_charger');
      expect(server.calls, ['POST /cameras/cam_charger/reconnect']);
      expect(camera.status, CameraStatus.watching);
    });

    test("the router's short reply: the camera is read again", () async {
      server
        ..on('POST', '/cameras/cam_down/reconnect', {
          'cam_id': 'cam_down',
          'cam_name': 'Lối xuống',
          'status': 'ONLINE',
          'live_stream_url': null,
        })
        ..on('GET', '/cameras/cam_down', camerasJson.last);
      final camera = await repo.reconnect('cam_down');
      expect(server.calls, [
        'POST /cameras/cam_down/reconnect',
        'GET /cameras/cam_down',
      ]);
      expect(camera.status, CameraStatus.signalLost);
    });

    test('still down: the error is thrown', () async {
      server.fail('POST', '/cameras/cam_down/reconnect', 503, 'MEDIAMTX_DOWN');
      await expectLater(
        repo.reconnect('cam_down'),
        throwsA(isA<ServerException>()),
      );
    });
  });

  group('edit (PATCH /cameras/{id})', () {
    test('sends only the given fields; the reply is the camera', () async {
      server.on('PATCH', '/cameras/cam_charger', {
        'cam_id': 'cam_charger',
        'cam_name': 'Khu sạc mới',
        'group_id': _gid,
        'subgroup_id': 'sub_b2',
        'subgroup_name': 'Hầm B2',
        'device_name': 'Hikvision DS-2CD2143G2-I',
        'status': 'ONLINE',
        'is_active': true,
        'is_ai_enabled': true,
        'watch_area': {'left': 0.1, 'top': 0.1, 'width': 0.5, 'height': 0.5},
        'live_stream_url':
            'https://stream.matpho.vn/live/cam_charger/index.m3u8',
      });
      const box = WatchArea(left: 0.1, top: 0.1, width: 0.5, height: 0.5);
      final camera = await repo.updateCamera(
        cameraId: 'cam_charger',
        name: 'Khu sạc mới',
        areaId: 'sub_b2',
        watchArea: box,
      );
      expect(server.body('PATCH', '/cameras/cam_charger'), {
        'cam_name': 'Khu sạc mới',
        'subgroup_id': 'sub_b2',
        'watch_area': {'left': 0.1, 'top': 0.1, 'width': 0.5, 'height': 0.5},
      });
      expect(camera.name, 'Khu sạc mới');
      expect(camera.areaId, 'sub_b2');
      expect(camera.watchArea, box);
    });

    test('enabled → is_active alone', () async {
      server.on('PATCH', '/cameras/cam_charger', _detailJson);
      await repo.updateCamera(cameraId: 'cam_charger', enabled: false);
      expect(server.body('PATCH', '/cameras/cam_charger'), {
        'is_active': false,
      });
    });

    test('a member: 403 → PermissionDeniedException', () async {
      server.fail('PATCH', '/cameras/cam_charger', 403, 'PERMISSION_DENIED');
      await expectLater(
        repo.updateCamera(cameraId: 'cam_charger', name: 'Cổng'),
        throwsA(isA<PermissionDeniedException>()),
      );
    });
  });

  group('trash', () {
    test('delete → DELETE /cameras/{id}', () async {
      server.on('DELETE', '/cameras/cam_charger', {
        'status': 'ok',
        'message': 'Đã xóa camera (chế độ lưu trữ 30 ngày)',
      });
      await repo.deleteCamera('cam_charger');
      expect(server.calls, ['DELETE /cameras/cam_charger']);
    });

    test('GET /cameras/trash?group_id=: name, area, purge date', () async {
      server.on('GET', '/cameras/trash', [
        {
          'cam_id': 'cam_old',
          'cam_name': 'Cổng sau',
          'group_id': _gid,
          'subgroup_id': 'sub_b1',
          'subgroup_name': 'Hầm B1',
          'device_name': null,
          'status': 'DELETED',
          'deleted_at': '2026-11-01T08:00:00.000Z',
          'purge_at': '2026-12-01T08:00:00.000Z',
        },
        {
          'cam_id': 'cam_older',
          'cam_name': 'Kho',
          'group_id': _gid,
          'subgroup_id': 'sub_b2',
          'subgroup_name': null,
          'device_name': 'Imou',
          'status': 'DELETED',
          'deleted_at': 'None',
          'purge_at': null,
        },
      ]);
      final trash = await repo.listTrash(_gid);
      expect(server.request('GET', '/cameras/trash').url.queryParameters, {
        'group_id': _gid,
      });
      expect(
        trash.first,
        TrashedCamera(
          id: 'cam_old',
          groupId: _gid,
          name: 'Cổng sau',
          areaId: 'sub_b1',
          areaName: 'Hầm B1',
          deletedAt: DateTime.utc(2026, 11, 1, 8).toLocal(),
          purgeAt: DateTime.utc(2026, 12, 1, 8).toLocal(),
        ),
      );
      expect(trash.last.deletedAt, isNull);
      expect(trash.last.purgeAt, isNull);
      expect(trash.last.deviceName, 'Imou');
    });

    test('a member: 403 → PermissionDeniedException', () async {
      server.fail('GET', '/cameras/trash', 403, 'PERMISSION_DENIED');
      await expectLater(
        repo.listTrash(_gid),
        throwsA(isA<PermissionDeniedException>()),
      );
    });

    test('restore posts …/restore, then reads the camera', () async {
      server
        ..on('POST', '/cameras/cam_charger/restore', {
          'status': 'ok',
          'message': 'Đã khôi phục camera thành công',
        })
        ..on('GET', '/cameras/cam_charger', _detailJson);
      final camera = await repo.restoreCamera('cam_charger');
      expect(server.calls, [
        'POST /cameras/cam_charger/restore',
        'GET /cameras/cam_charger',
      ]);
      expect(camera.id, 'cam_charger');
      expect(camera.status, CameraStatus.watching);
    });

    test('delete forever → DELETE …/permanent; a manager gets 403', () async {
      server.on('DELETE', '/cameras/cam_charger/permanent', {'status': 'ok'});
      await repo.deleteCameraForever('cam_charger');
      expect(server.calls, ['DELETE /cameras/cam_charger/permanent']);

      server.fail(
        'DELETE',
        '/cameras/cam_down/permanent',
        403,
        'PERMISSION_DENIED',
      );
      await expectLater(
        repo.deleteCameraForever('cam_down'),
        throwsA(isA<PermissionDeniedException>()),
      );
    });
  });

  group('delete area', () {
    test('DELETE /groups/{g}/subgroups/{s}', () async {
      server.on('DELETE', '/groups/$_gid/subgroups/sub_b2', {
        'status': 'success',
      });
      await repo.deleteArea(groupId: _gid, areaId: 'sub_b2');
      expect(server.calls, ['DELETE /groups/$_gid/subgroups/sub_b2']);
    });

    test('still has cameras → AreaNotEmptyException', () async {
      server.fail(
        'DELETE',
        '/groups/$_gid/subgroups/sub_b1',
        400,
        'SUBGROUP_HAS_CAMERAS',
      );
      await expectLater(
        repo.deleteArea(groupId: _gid, areaId: 'sub_b1'),
        throwsA(isA<AreaNotEmptyException>()),
      );
    });
  });
}
