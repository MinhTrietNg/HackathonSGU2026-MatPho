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

enum AiMode { alwaysOn, scheduled, off }

final class AiPause {
  const AiPause({required this.from, required this.to, this.days = everyDay});

  static const everyDay = {1, 2, 3, 4, 5, 6, 7};

  final int from;
  final int to;

  final Set<int> days;

  AiPause copyWith({int? from, int? to, Set<int>? days}) => AiPause(
    from: from ?? this.from,
    to: to ?? this.to,
    days: days ?? this.days,
  );

  @override
  bool operator ==(Object other) =>
      other is AiPause &&
      other.from == from &&
      other.to == to &&
      other.days.length == days.length &&
      other.days.containsAll(days);

  @override
  int get hashCode => Object.hash(from, to, Object.hashAllUnordered(days));
}

final class CameraAi {
  const CameraAi({this.mode = AiMode.alwaysOn, this.pauses = const []});

  static const alwaysOn = CameraAi();
  static const off = CameraAi(mode: AiMode.off);

  final AiMode mode;

  final List<AiPause> pauses;

  @override
  bool operator ==(Object other) {
    if (other is! CameraAi ||
        other.mode != mode ||
        other.pauses.length != pauses.length) {
      return false;
    }
    for (var i = 0; i < pauses.length; i++) {
      if (other.pauses[i] != pauses[i]) return false;
    }
    return true;
  }

  @override
  int get hashCode => Object.hash(mode, Object.hashAll(pauses));
}

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
    this.ai = CameraAi.alwaysOn,
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

  final CameraAi ai;

  Camera copyWith({
    CameraStatus? status,
    DateTime? signalLostSince,
    String? liveStreamUrl,
    CameraAi? ai,
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
    ai: ai ?? this.ai,
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
      other.deviceName == deviceName &&
      other.ai == ai;

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
    ai,
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
