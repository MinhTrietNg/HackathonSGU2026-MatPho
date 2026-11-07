import '../models/camera.dart';

abstract interface class CameraRepository {
  Future<List<Camera>> listCameras(String groupId);

  Future<List<Area>> listAreas(String groupId);

  Future<Area> createArea({required String groupId, required String name});

  Future<CameraProbe> connect(String rtspUrl);

  Future<Camera> saveCamera({
    required String groupId,
    required String rtspUrl,
    required String name,
    required String areaId,
    required WatchArea watchArea,
    String? deviceName,
  });

  Future<Camera> reconnect(String cameraId);

  Future<Camera> getCamera(String cameraId);

  Future<Camera> updateCamera({
    required String cameraId,
    String? name,
    String? areaId,
    WatchArea? watchArea,
    bool? enabled,
    String? rtspUrl,
    CameraAi? ai,
  });

  Future<void> deleteCamera(String cameraId);

  Future<List<TrashedCamera>> listTrash(String groupId);

  Future<Camera> restoreCamera(String cameraId);

  Future<void> deleteCameraForever(String cameraId);

  Future<void> deleteArea({required String groupId, required String areaId});
}
