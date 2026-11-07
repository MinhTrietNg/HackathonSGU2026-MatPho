import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/camera.dart';
import 'package:mat_pho/data/models/group.dart';
import 'package:mat_pho/data/repositories/camera_repository.dart';
import 'fake_data.dart';
import 'fake_scenario.dart';
import 'fake_world.dart';

final class FakeCameraRepository implements CameraRepository {
  FakeCameraRepository(this._world);

  final FakeWorld _world;

  FakeScenario get _s => _world.scenario;

  @override
  Future<List<Camera>> listCameras(String groupId) async {
    await _world.delay();
    final me = _world.me(groupId);
    final visible = me.cameraIds;
    return [
      for (final c in _world.cameras)
        if (c.groupId == groupId && (visible == null || visible.contains(c.id)))
          _seenByMe(c),
    ];
  }

  Camera _seenByMe(Camera c) {
    final me = _world.me(c.groupId);
    if (me.role != GroupRole.member) return c;
    final ids = me.cameraIds;
    if (ids != null && !ids.contains(c.id)) return c;
    return c.copyWith(liveStreamUrl: 'https://stream.test/live/${c.id}.m3u8');
  }

  @override
  Future<List<Area>> listAreas(String groupId) async {
    await _world.delay();
    return [
      for (final a in _world.areas)
        if (a.groupId == groupId) a,
    ];
  }

  @override
  Future<Area> createArea({
    required String groupId,
    required String name,
  }) async {
    await _world.delay();
    _requireManager(groupId);
    final area = Area(id: _world.newId('a'), groupId: groupId, name: name);
    _world.areas.add(area);
    return area;
  }

  @override
  Future<CameraProbe> connect(String rtspUrl) async {
    await _world.delay(const Duration(seconds: 2));
    const name = FakeData.probedDeviceName;
    if (_s.has(FakeCase.cameraNoResponse)) {
      throw const CameraNoResponseException(cameraName: name);
    }
    if (_s.has(FakeCase.cameraAuthFailed)) {
      throw const CameraAuthFailedException(cameraName: name);
    }
    if (_s.has(FakeCase.cameraNotOnCompanyWifi)) {
      throw const NotOnCompanyWifiException(cameraName: name);
    }
    if (_s.has(FakeCase.cameraVendorBlocked)) {
      throw const VendorBlockedException(cameraName: name);
    }
    return CameraProbe(rtspUrl: rtspUrl, deviceName: name);
  }

  @override
  Future<Camera> saveCamera({
    required String groupId,
    required String rtspUrl,
    required String name,
    required String areaId,
    required WatchArea watchArea,
    String? deviceName,
  }) async {
    await _world.delay();
    _requireManager(groupId);
    final camera = Camera(
      id: _world.newId('cam'),
      groupId: groupId,
      areaId: areaId,
      name: name,
      rtspUrl: rtspUrl,
      watchArea: watchArea,
      deviceName: deviceName,
    );
    _world.cameras.add(camera);
    final group = _world.group(groupId);
    _world.replaceGroup(group.copyWith(cameraCount: group.cameraCount + 1));
    return camera;
  }

  @override
  Future<Camera> reconnect(String cameraId) async {
    await _world.delay(const Duration(seconds: 2));
    final camera = _camera(cameraId);
    if (_s.has(FakeCase.cameraReconnectFails)) {
      throw CameraNoResponseException(cameraName: camera.name);
    }
    final fixed = camera.copyWith(status: CameraStatus.watching);
    _world.cameras[_world.cameras.indexOf(camera)] = fixed;
    return fixed;
  }

  @override
  Future<Camera> getCamera(String cameraId) async {
    await _world.delay();
    return _seenByMe(_camera(cameraId));
  }

  @override
  Future<Camera> updateCamera({
    required String cameraId,
    String? name,
    String? areaId,
    WatchArea? watchArea,
    bool? enabled,
    String? rtspUrl,
    CameraAi? ai,
  }) async {
    await _world.delay();
    final before = _camera(cameraId);
    _requireManager(before.groupId);
    if (_s.has(FakeCase.cameraUpdateFails)) {
      throw const ServerException();
    }
    final after = Camera(
      id: before.id,
      groupId: before.groupId,
      areaId: areaId ?? before.areaId,
      name: name ?? before.name,
      rtspUrl: rtspUrl ?? before.rtspUrl,
      watchArea: watchArea ?? before.watchArea,
      status: rtspUrl != null ? CameraStatus.watching : before.status,
      signalLostSince: rtspUrl != null ? null : before.signalLostSince,
      liveStreamUrl: before.liveStreamUrl,
      deviceName: before.deviceName,
      ai: ai ?? before.ai,
    );
    _world.cameras[_world.cameras.indexOf(before)] = after;
    return _seenByMe(after);
  }

  @override
  Future<void> deleteCamera(String cameraId) async {
    await _world.delay();
    final camera = _camera(cameraId);
    _requireManager(camera.groupId);
    final now = _world.now();
    _world.cameras.remove(camera);
    _world.trash.add((
      entry: TrashedCamera(
        id: camera.id,
        groupId: camera.groupId,
        name: camera.name,
        areaId: camera.areaId,
        areaName: _areaName(camera.areaId),
        deviceName: camera.deviceName,
        deletedAt: now,
        purgeAt: now.add(FakeWorld.trashRetention),
      ),
      camera: camera,
    ));
    _bumpCameraCount(camera.groupId, -1);
  }

  @override
  Future<List<TrashedCamera>> listTrash(String groupId) async {
    await _world.delay();
    _requireManager(groupId);
    return [
      for (final t in _world.trash)
        if (t.entry.groupId == groupId) t.entry,
    ];
  }

  @override
  Future<Camera> restoreCamera(String cameraId) async {
    await _world.delay();
    final trashed = _trashed(cameraId);
    _requireManager(trashed.camera.groupId);
    _world.trash.remove(trashed);
    _world.cameras.add(trashed.camera);
    _bumpCameraCount(trashed.camera.groupId, 1);
    return _seenByMe(trashed.camera);
  }

  @override
  Future<void> deleteCameraForever(String cameraId) async {
    await _world.delay();
    final live = _world.cameras.where((c) => c.id == cameraId).firstOrNull;
    final groupId = live?.groupId ?? _trashed(cameraId).camera.groupId;
    _requireOwner(groupId);
    if (live != null) {
      _world.cameras.remove(live);
      _bumpCameraCount(groupId, -1);
    } else {
      _world.trash.removeWhere((t) => t.entry.id == cameraId);
    }
  }

  @override
  Future<void> deleteArea({
    required String groupId,
    required String areaId,
  }) async {
    await _world.delay();
    _requireOwner(groupId);
    if (_world.cameras.any((c) => c.groupId == groupId && c.areaId == areaId)) {
      throw const AreaNotEmptyException();
    }
    _world.areas.removeWhere((a) => a.groupId == groupId && a.id == areaId);
  }

  ({TrashedCamera entry, Camera camera}) _trashed(String id) =>
      _world.trash.firstWhere(
        (t) => t.entry.id == id,
        orElse: () => throw const ServerException(code: 'NOT_FOUND'),
      );

  String? _areaName(String? areaId) =>
      _world.areas.where((a) => a.id == areaId).firstOrNull?.name;

  void _bumpCameraCount(String groupId, int delta) {
    final group = _world.group(groupId);
    _world.replaceGroup(group.copyWith(cameraCount: group.cameraCount + delta));
  }

  void _requireOwner(String groupId) {
    if (_world.group(groupId).myRole != GroupRole.owner) {
      throw const PermissionDeniedException();
    }
  }

  Camera _camera(String id) => _world.cameras.firstWhere(
    (c) => c.id == id,
    orElse: () => throw StateError('No camera $id'),
  );

  void _requireManager(String groupId) {
    if (!_world.group(groupId).myRole.canManage) {
      throw const PermissionDeniedException();
    }
  }
}
