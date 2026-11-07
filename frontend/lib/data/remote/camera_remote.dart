library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/camera.dart';
import '../repositories/camera_repository.dart';
import 'core/api_client.dart';
import 'core/json.dart';
import 'core/remote_providers.dart';

final class RemoteCameraRepository implements CameraRepository {
  RemoteCameraRepository(this._api);

  final ApiClient _api;

  @override
  Future<List<Camera>> listCameras(String groupId) async => [
    for (final (i, item) in asJsonList(
      await _api.get('/cameras', query: {'group_id': groupId}),
    ).indexed)
      parseCamera(asJsonMap(item, 'cameras[$i]')),
  ];

  @override
  Future<List<Area>> listAreas(String groupId) async => [
    for (final (i, item) in asJsonList(
      await _api.get('/groups/$groupId/subgroups'),
    ).indexed)
      _area(groupId, asJsonMap(item, 'subgroups[$i]')),
  ];

  @override
  Future<Area> createArea({
    required String groupId,
    required String name,
  }) async => _area(
    groupId,
    asJsonMap(
      await _api.post('/groups/$groupId/subgroups', body: {'name': name}),
    ),
  );

  @override
  Future<CameraProbe> connect(String rtspUrl) async {
    final json = asJsonMap(
      await _api.post('/cameras/probe', body: {'rtsp_url': rtspUrl}),
    );
    return CameraProbe(
      rtspUrl: rtspUrl,
      deviceName: readStringOrNull(json, 'device_name') ?? '',
      previewSnapshotUrl: readStringOrNull(json, 'preview_snapshot_url'),
    );
  }

  @override
  Future<Camera> saveCamera({
    required String groupId,
    required String rtspUrl,
    required String name,
    required String areaId,
    required WatchArea watchArea,
    String? deviceName,
  }) async => parseCamera(
    asJsonMap(
      await _api.post(
        '/cameras',
        body: {
          'group_id': groupId,
          'subgroup_id': areaId,
          'cam_name': name,
          'device_name': deviceName,
          'rtsp_url': rtspUrl,
          'watch_area': _watchAreaJson(watchArea),
        },
      ),
    ),
  );

  @override
  Future<Camera> reconnect(String cameraId) async {
    final json = asJsonMap(await _api.post('/cameras/$cameraId/reconnect'));
    if (json['group_id'] is String) return parseCamera(json);
    return getCamera(cameraId);
  }

  @override
  Future<Camera> getCamera(String cameraId) async =>
      parseCamera(asJsonMap(await _api.get('/cameras/$cameraId')));

  @override
  Future<Camera> updateCamera({
    required String cameraId,
    String? name,
    String? areaId,
    WatchArea? watchArea,
    bool? enabled,
  }) async => parseCamera(
    asJsonMap(
      await _api.patch(
        '/cameras/$cameraId',
        body: {
          'cam_name': ?name,
          'subgroup_id': ?areaId,
          if (watchArea != null) 'watch_area': _watchAreaJson(watchArea),
          'is_active': ?enabled,
        },
      ),
    ),
  );

  @override
  Future<void> deleteCamera(String cameraId) async {
    await _api.delete('/cameras/$cameraId');
  }

  @override
  Future<List<TrashedCamera>> listTrash(String groupId) async => [
    for (final (i, item) in asJsonList(
      await _api.get('/cameras/trash', query: {'group_id': groupId}),
    ).indexed)
      _trashed(asJsonMap(item, 'trash[$i]')),
  ];

  @override
  Future<Camera> restoreCamera(String cameraId) async {
    await _api.post('/cameras/$cameraId/restore');
    return getCamera(cameraId);
  }

  @override
  Future<void> deleteCameraForever(String cameraId) async {
    await _api.delete('/cameras/$cameraId/permanent');
  }

  @override
  Future<void> deleteArea({
    required String groupId,
    required String areaId,
  }) async {
    await _api.delete('/groups/$groupId/subgroups/$areaId');
  }
}

Map<String, Object?> _watchAreaJson(WatchArea area) => {
  'left': area.left,
  'top': area.top,
  'width': area.width,
  'height': area.height,
};

Camera parseCamera(Map<String, Object?> json) {
  final status = _status(readString(json, 'status'));
  final area = readMapOrNull(json, 'watch_area');
  return Camera(
    id: readString(json, 'cam_id'),
    groupId: readString(json, 'group_id'),
    areaId: readStringOrNull(json, 'subgroup_id'),
    name: readString(json, 'cam_name'),
    deviceName: readStringOrNull(json, 'device_name'),
    status: status,
    signalLostSince: status == CameraStatus.signalLost
        ? _time(json, 'last_seen_at')
        : null,
    liveStreamUrl: readStringOrNull(json, 'live_stream_url'),
    watchArea: area == null
        ? WatchArea.full
        : WatchArea(
            left: readDouble(area, 'left'),
            top: readDouble(area, 'top'),
            width: readDouble(area, 'width'),
            height: readDouble(area, 'height'),
          ),
  );
}

CameraStatus _status(String value) => switch (value) {
  'ONLINE' => CameraStatus.watching,
  'OFFLINE' || 'DISABLED' || 'SIGNAL_LOST' => CameraStatus.signalLost,
  _ => CameraStatus.signalLost,
};

DateTime? _time(Map<String, Object?> json, String key) {
  final value = json[key];
  return value is String ? tryParseServerTime(value) : null;
}

TrashedCamera _trashed(Map<String, Object?> json) => TrashedCamera(
  id: readString(json, 'cam_id'),
  groupId: readString(json, 'group_id'),
  name: readString(json, 'cam_name'),
  areaId: readStringOrNull(json, 'subgroup_id'),
  areaName: readStringOrNull(json, 'subgroup_name'),
  deviceName: readStringOrNull(json, 'device_name'),
  deletedAt: _time(json, 'deleted_at'),
  purgeAt: _time(json, 'purge_at'),
);

Area _area(String groupId, Map<String, Object?> json) => Area(
  id: readString(json, 'subgroup_id'),
  groupId: groupId,
  name: readString(json, 'name'),
);

final remoteCameraRepositoryProvider = Provider<CameraRepository>(
  (ref) => RemoteCameraRepository(ref.watch(apiClientProvider)),
);
