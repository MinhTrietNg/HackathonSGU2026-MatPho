import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/errors.dart';
import '../../data/models/models.dart';
import '../../data/providers.dart';
import '../auth/auth_session.dart';
import '../groups/current_group.dart';
import '../groups/group_state.dart'
    show groupAreasProvider, groupCamerasProvider, groupMembersProvider;

typedef CameraPlace = ({Group group, int cameraCount});

final cameraPlacesProvider = FutureProvider<List<CameraPlace>>((ref) async {
  final all = await ref.watch(groupsProvider.future);
  final groups = [
    ...all.where((g) => g.isPersonal),
    ...all.where((g) => !g.isPersonal),
  ];
  final counts = await Future.wait([
    for (final g in groups) ref.watch(groupCamerasProvider(g.id).future),
  ]);
  return [
    for (final (i, g) in groups.indexed)
      (group: g, cameraCount: counts[i].length),
  ];
});

final currentPlaceProvider = FutureProvider<Group>(
  (ref) => ref.watch(currentGroupProvider.future),
);

const noLiveViewNote = 'Vai trò "Chỉ báo cháy" không xem được camera.';

typedef CameraSection = ({Area? area, List<Camera> cameras});

/// Deletes and undos made on this phone, shown before the server confirms
/// them and before the place reloads (groups, then cameras: ~3s).
typedef CameraListEdits = ({Set<String> hidden, Map<String, Camera> shown});

final cameraListEditsProvider =
    NotifierProvider<CameraListEditsNotifier, CameraListEdits>(
      CameraListEditsNotifier.new,
    );

class CameraListEditsNotifier extends Notifier<CameraListEdits> {
  @override
  CameraListEdits build() {
    ref.watch(sessionUserIdProvider);
    return (hidden: const {}, shown: const {});
  }

  void hide(Camera camera) => state = (
    hidden: {...state.hidden, camera.id},
    shown: {...state.shown}..remove(camera.id),
  );

  /// Back in the list even while the server still has it in the trash.
  void show(Camera camera) => state = (
    hidden: {...state.hidden}..remove(camera.id),
    shown: {...state.shown, camera.id: camera},
  );

  /// The server's list has [cameraId] again: its own copy takes over.
  void settle(String cameraId) {
    if (!state.shown.containsKey(cameraId)) return;
    state = (hidden: state.hidden, shown: {...state.shown}..remove(cameraId));
  }
}

/// E1's list: the server's sections with this phone's edits on top. Plain
/// (not async), so a delete or an undo shows on the next frame even while
/// [placeCamerasProvider] is reloading.
final shownPlaceCamerasProvider = Provider<List<CameraSection>?>((ref) {
  final sections = ref.watch(placeCamerasProvider).value;
  if (sections == null) return null;
  final edits = ref.watch(cameraListEditsProvider);
  if (edits.hidden.isEmpty && edits.shown.isEmpty) return sections;
  final listed = [for (final s in sections) ...s.cameras];
  final groupId =
      listed.firstOrNull?.groupId ?? ref.watch(currentPlaceProvider).value?.id;
  if (groupId == null) return sections;
  final ids = {for (final c in listed) c.id};
  final areas =
      ref.watch(groupAreasProvider(groupId)).value ??
      [for (final s in sections) ?s.area];
  return _sectionsOf(areas, [
    for (final c in listed)
      if (!edits.hidden.contains(c.id)) c,
    for (final c in edits.shown.values)
      if (c.groupId == groupId && !ids.contains(c.id)) c,
  ]);
});

final placeCamerasProvider = FutureProvider<List<CameraSection>>((ref) async {
  final group = await ref.watch(currentPlaceProvider.future);
  final (areas, cameras) = await (
    ref.watch(groupAreasProvider(group.id).future),
    ref.watch(groupCamerasProvider(group.id).future),
  ).wait;
  return _sectionsOf(areas, cameras);
});

List<CameraSection> _sectionsOf(List<Area> areas, List<Camera> cameras) {
  final sections = <CameraSection>[
    for (final area in areas)
      (
        area: area,
        cameras: [
          for (final c in cameras)
            if (c.areaId == area.id) c,
        ],
      ),
  ];
  final areaIds = {for (final a in areas) a.id};
  final loose = [
    for (final c in cameras)
      if (!areaIds.contains(c.areaId)) c,
  ];
  return [
    for (final s in sections)
      if (s.cameras.isNotEmpty) s,
    if (loose.isNotEmpty) (area: null, cameras: loose),
  ];
}

final addCameraPlaceProvider = FutureProvider<Group>((ref) async {
  final groupId = ref.watch(
    addCameraProvider.select((s) => s.replacing?.groupId),
  );
  if (groupId == null) return ref.watch(currentPlaceProvider.future);
  final groups = await ref.watch(groupsProvider.future);
  return groups.firstWhere(
    (g) => g.id == groupId,
    orElse: () => throw StateError('No place $groupId'),
  );
});

final placeAreasProvider = FutureProvider<List<Area>>((ref) async {
  final group = await ref.watch(addCameraPlaceProvider.future);
  return ref.watch(groupAreasProvider(group.id).future);
});

final class CameraDetail {
  const CameraDetail({
    required this.camera,
    required this.group,
    required this.areaName,
    required this.notifiedNames,
  });

  final Camera camera;
  final Group group;

  final String? areaName;

  final List<String> notifiedNames;

  String get title =>
      areaName == null ? camera.name : '$areaName · ${camera.name}';
}

final cameraDetailProvider = FutureProvider.autoDispose
    .family<CameraDetail, String>((ref, cameraId) async {
      ref.watch(sessionUserIdProvider);
      final camera = await ref
          .watch(cameraRepositoryProvider)
          .getCamera(cameraId);
      final groups = await ref.watch(groupsProvider.future);
      final group = groups.where((g) => g.id == camera.groupId).firstOrNull;
      if (group == null) throw StateError('No place has camera $cameraId');
      final areas = await ref.watch(groupAreasProvider(group.id).future);
      final area = areas.where((a) => a.id == camera.areaId).firstOrNull;
      return CameraDetail(
        camera: camera,
        group: group,
        areaName: area?.name,
        notifiedNames: await _notified(ref, group.id),
      );
    });

Future<List<String>> _notified(Ref ref, String groupId) async {
  try {
    final members = await ref.watch(groupMembersProvider(groupId).future);
    return [
      for (final m in members)
        if (!m.isYou && !m.pending && m.role.canManage) m.displayName,
    ];
  } on MpException {
    return const [];
  }
}

final watchCameraProvider = Provider.autoDispose
    .family<AsyncValue<CameraDetail>, String>((ref, cameraId) {
      final detail = ref.watch(cameraDetailProvider(cameraId));
      if (detail.hasValue || detail.hasError) return detail;
      final place = ref.watch(currentPlaceProvider).value;
      for (final section in ref.watch(shownPlaceCamerasProvider) ?? const []) {
        for (final camera in section.cameras) {
          // Right after a switch the sections can still be the previous
          // place's: never pair a camera with a place it isn't in.
          if (camera.id != cameraId ||
              place == null ||
              camera.groupId != place.id) {
            continue;
          }
          return AsyncData(
            CameraDetail(
              camera: camera,
              group: place,
              areaName: section.area?.name,
              notifiedNames: const [],
            ),
          );
        }
      }
      return detail;
    });

final class AddCameraState {
  const AddCameraState({
    this.replacing,
    this.rtspUrl = '',
    this.probe,
    this.error,
    this.busy = false,
    this.name = '',
    this.areaId,
  });

  final Camera? replacing;

  final String rtspUrl;

  final CameraProbe? probe;

  final CameraConnectException? error;

  final bool busy;

  final String name;

  final String? areaId;

  AddCameraState copyWith({
    String? rtspUrl,
    CameraProbe? probe,
    CameraConnectException? error,
    bool clearError = false,
    bool? busy,
    String? name,
    String? areaId,
  }) => AddCameraState(
    replacing: replacing,
    rtspUrl: rtspUrl ?? this.rtspUrl,
    probe: probe ?? this.probe,
    error: clearError ? null : error ?? this.error,
    busy: busy ?? this.busy,
    name: name ?? this.name,
    areaId: areaId ?? this.areaId,
  );
}

class AddCameraNotifier extends Notifier<AddCameraState> {
  @override
  AddCameraState build() {
    ref.watch(sessionUserIdProvider);
    return const AddCameraState();
  }

  void start() => state = const AddCameraState();

  // I8 "Thêm lại RTSP": I2 starts empty (the server never sends the old link
  // back); I5 keeps the camera's name and area, in its place.
  void startReplace(Camera camera) => state = AddCameraState(
    replacing: camera,
    name: camera.name,
    areaId: camera.areaId,
  );

  Future<CameraConnectException?> connect(String rtspUrl) async {
    state = state.copyWith(rtspUrl: rtspUrl, busy: true);
    try {
      final probe = await ref.read(cameraRepositoryProvider).connect(rtspUrl);
      state = state.copyWith(probe: probe, clearError: true, busy: false);
      return null;
    } on CameraConnectException catch (e) {
      state = state.copyWith(error: e, busy: false);
      return e;
    } on MpException {
      state = state.copyWith(busy: false);
      rethrow;
    }
  }

  void setName(String name) => state = state.copyWith(name: name);

  void selectArea(String areaId) => state = state.copyWith(areaId: areaId);

  // A replacing flow (I8) sends the new link to the same camera
  // (PATCH /cameras/{cam_id} with rtsp_url): its id, history and member
  // access stay.
  Future<Camera> save({required String areaId}) async {
    state = state.copyWith(busy: true);
    final repository = ref.read(cameraRepositoryProvider);
    final rtspUrl = state.probe?.rtspUrl ?? state.rtspUrl;
    try {
      final Camera camera;
      if (state.replacing case final old?) {
        camera = await repository.updateCamera(
          cameraId: old.id,
          rtspUrl: rtspUrl,
          name: state.name.trim(),
          areaId: areaId,
        );
        ref
          ..read(currentGroupIdProvider.notifier).select(old.groupId)
          ..invalidate(cameraDetailProvider(old.id));
      } else {
        final group = await ref.read(currentPlaceProvider.future);
        camera = await repository.saveCamera(
          groupId: group.id,
          rtspUrl: rtspUrl,
          name: state.name.trim(),
          areaId: areaId,
          watchArea: WatchArea.full,
          deviceName: state.probe?.deviceName,
        );
      }
      ref.invalidate(groupCamerasProvider(camera.groupId));
      if (state.replacing == null) {
        // The watch screen draws a new camera from this list while its own
        // detail still loads (camera, then the reloading groups: ~3s of a
        // blank screen). So wait here, with the button busy, for the list to
        // hold it; the groups reload (camera counts) comes after.
        try {
          await ref.read(placeCamerasProvider.future);
        } on Object {
          // The watch screen loads the camera on its own.
        }
        ref.invalidate(groupsProvider);
      }
      return camera;
    } finally {
      state = state.copyWith(busy: false);
    }
  }
}

final addCameraProvider = NotifierProvider<AddCameraNotifier, AddCameraState>(
  AddCameraNotifier.new,
);
