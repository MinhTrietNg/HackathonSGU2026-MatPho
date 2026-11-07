final class Area {
  const Area({required this.id, required this.groupId, required this.name});

  final String id;
  final String groupId;
  final String name;

  @override
  bool operator ==(Object other) =>
      other is Area &&
      other.id == id &&
      other.groupId == groupId &&
      other.name == name;

  @override
  int get hashCode => Object.hash(id, groupId, name);
}

final class WatchArea {
  const WatchArea({
    required this.left,
    required this.top,
    required this.width,
    required this.height,
  });

  static const full = WatchArea(left: 0, top: 0, width: 1, height: 1);

  final double left;
  final double top;
  final double width;
  final double height;

  @override
  bool operator ==(Object other) =>
      other is WatchArea &&
      other.left == left &&
      other.top == top &&
      other.width == width &&
      other.height == height;

  @override
  int get hashCode => Object.hash(left, top, width, height);
}

enum CameraStatus { watching, signalLost }

final class Camera {
  const Camera({
    required this.id,
    required this.name,
    required this.groupId,
    this.rtspUrl,
    this.areaId,
    this.watchArea = WatchArea.full,
    this.status = CameraStatus.watching,
    this.signalLostSince,
    this.liveStreamUrl,
    this.deviceName,
  });

  final String id;

  final String groupId;

  final String? areaId;

  final String name;

  final String? rtspUrl;
  final WatchArea watchArea;
  final CameraStatus status;

  final DateTime? signalLostSince;

  final String? liveStreamUrl;

  final String? deviceName;

  Camera copyWith({
    CameraStatus? status,
    DateTime? signalLostSince,
    String? liveStreamUrl,
  }) => Camera(
    id: id,
    groupId: groupId,
    areaId: areaId,
    name: name,
    rtspUrl: rtspUrl,
    watchArea: watchArea,
    status: status ?? this.status,
    signalLostSince: status == CameraStatus.watching
        ? null
        : signalLostSince ?? this.signalLostSince,
    liveStreamUrl: liveStreamUrl ?? this.liveStreamUrl,
    deviceName: deviceName,
  );

  @override
  bool operator ==(Object other) =>
      other is Camera &&
      other.id == id &&
      other.groupId == groupId &&
      other.areaId == areaId &&
      other.name == name &&
      other.rtspUrl == rtspUrl &&
      other.watchArea == watchArea &&
      other.status == status &&
      other.signalLostSince == signalLostSince &&
      other.liveStreamUrl == liveStreamUrl &&
      other.deviceName == deviceName;

  @override
  int get hashCode => Object.hash(
    id,
    groupId,
    areaId,
    name,
    rtspUrl,
    watchArea,
    status,
    signalLostSince,
    liveStreamUrl,
    deviceName,
  );
}

final class CameraProbe {
  const CameraProbe({
    required this.rtspUrl,
    required this.deviceName,
    this.previewSnapshotUrl,
  });

  final String rtspUrl;

  final String deviceName;

  final String? previewSnapshotUrl;
}

final class TrashedCamera {
  const TrashedCamera({
    required this.id,
    required this.groupId,
    required this.name,
    this.areaId,
    this.areaName,
    this.deviceName,
    this.deletedAt,
    this.purgeAt,
  });

  final String id;
  final String groupId;
  final String name;
  final String? areaId;

  final String? areaName;
  final String? deviceName;
  final DateTime? deletedAt;

  final DateTime? purgeAt;

  @override
  bool operator ==(Object other) =>
      other is TrashedCamera &&
      other.id == id &&
      other.groupId == groupId &&
      other.name == name &&
      other.areaId == areaId &&
      other.areaName == areaName &&
      other.deviceName == deviceName &&
      other.deletedAt == deletedAt &&
      other.purgeAt == purgeAt;

  @override
  int get hashCode => Object.hash(
    id,
    groupId,
    name,
    areaId,
    areaName,
    deviceName,
    deletedAt,
    purgeAt,
  );
}
