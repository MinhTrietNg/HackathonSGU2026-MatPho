library;

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_toast.dart';
import '../../data/errors.dart';
import '../../data/models/models.dart';
import '../../data/providers.dart';
import '../../data/repositories/camera_repository.dart';
import '../groups/current_group.dart' show groupsProvider;
import '../groups/group_state.dart' show groupCamerasProvider;
import 'camera_actions_sheet.dart';
import 'camera_dialogs.dart';
import 'camera_state.dart';

/// Deleted cameras of one place, oldest purge first.
typedef TrashedPlace = ({Group group, List<TrashedCamera> cameras});

// Every place the user manages, since only owners and managers may restore.
final cameraTrashProvider = FutureProvider.autoDispose<List<TrashedPlace>>((
  ref,
) async {
  final repository = ref.watch(cameraRepositoryProvider);
  final groups = await ref.watch(groupsProvider.future);
  return [
    for (final group in groups)
      if (group.myRole.canManage)
        if (await repository.listTrash(group.id) case final cameras
            when cameras.isNotEmpty)
          (group: group, cameras: [...cameras]..sort(_purgeFirst)),
  ];
});

int _purgeFirst(TrashedCamera a, TrashedCamera b) =>
    (a.purgeAt ?? DateTime(0)).compareTo(b.purgeAt ?? DateTime(0));

final cameraActionsProvider = Provider<CameraActions>(CameraActions.new);

class CameraActions {
  CameraActions(this._ref);

  final Ref _ref;

  CameraRepository get _repo => _ref.read(cameraRepositoryProvider);

  CameraListEditsNotifier get _edits =>
      _ref.read(cameraListEditsProvider.notifier);

  // Deletes still in flight (true once done), so an undo tapped right away
  // restores only after its delete has landed.
  final _deleting = <String, Future<bool>>{};

  /// Leaves E1 at once (synchronously, before the request); comes back if
  /// the server refuses.
  Future<void> delete(Camera camera) async {
    _edits.hide(camera);
    final done = Completer<bool>();
    _deleting[camera.id] = done.future;
    try {
      await _repo.deleteCamera(camera.id);
      done.complete(true);
    } on Object {
      done.complete(false);
      _edits
        ..show(camera)
        ..settle(camera.id);
      rethrow;
    } finally {
      if (identical(_deleting[camera.id], done.future)) {
        _deleting.remove(camera.id);
      }
    }
    _refresh(camera);
  }

  /// With [camera] (the undo toast), it is back in E1 at once, before the
  /// restore is sent; it leaves again if the server refuses.
  Future<Camera> restore(String cameraId, {Camera? camera}) async {
    if (camera != null) _edits.show(camera);
    if (await _deleting[cameraId] == false) {
      // The delete never happened: nothing to restore.
      return camera ?? await _repo.getCamera(cameraId);
    }
    final Camera restored;
    try {
      restored = await _repo.restoreCamera(cameraId);
    } on Object {
      if (camera != null) _edits.hide(camera);
      rethrow;
    }
    _refresh(restored);
    if (camera != null) unawaited(_settle(restored));
    return restored;
  }

  // The local copy stays until the reloaded list has the camera again, so
  // it never blinks out in between.
  Future<void> _settle(Camera camera) async {
    try {
      await _ref.read(groupCamerasProvider(camera.groupId).future);
      await _ref.read(placeCamerasProvider.future);
    } on Object {
      return; // Kept: the server's copy wins once a reload has it.
    }
    _edits.settle(camera.id);
  }

  Future<void> deleteForever(String cameraId) async {
    await _repo.deleteCameraForever(cameraId);
    _ref.invalidate(cameraTrashProvider);
  }

  Future<Camera> removeRtsp(Camera camera) async {
    final updated = await _repo.removeRtsp(camera.id);
    _refresh(updated);
    return updated;
  }

  // The lists that show this camera, and the place's camera count.
  void _refresh(Camera camera) => _ref
    ..invalidate(groupsProvider)
    ..invalidate(groupCamerasProvider(camera.groupId))
    ..invalidate(placeCamerasProvider)
    ..invalidate(cameraDetailProvider(camera.id))
    ..invalidate(cameraTrashProvider);
}

/// The trash button on E2 and I8: I20, then the chosen flow.
Future<void> cameraActionsMenu(
  BuildContext context,
  WidgetRef ref,
  Camera camera,
) async {
  final action = await showCameraActionsSheet(context, camera);
  if (action == null || !context.mounted) return;
  switch (action) {
    case CameraSheetAction.removeRtsp:
      await removeRtspFlow(context, ref, camera);
    case CameraSheetAction.delete:
      await deleteCameraFlow(context, ref, camera);
  }
}

/// I21 → I8 "Chưa có đường dẫn RTSP". Returns true once the link is gone.
Future<bool> removeRtspFlow(
  BuildContext context,
  WidgetRef ref,
  Camera camera,
) async {
  if (!await confirmRemoveRtsp(context, camera.name) || !context.mounted) {
    return false;
  }
  final router = GoRouter.of(context);
  try {
    await ref.read(cameraActionsProvider).removeRtsp(camera);
  } on MpException {
    if (context.mounted) showCameraActionFailedToast(context);
    return false;
  }
  if (context.mounted) {
    showCameraPlainToast(context, 'Đã gỡ RTSP · ${camera.name}');
  }
  final lost = AppRoutes.signalLost(camera.id);
  if (router.state.uri.path != lost) router.go(lost);
  return true;
}

/// I17 → E1 with an undo toast, at once: the camera leaves the list and E1
/// opens before the server answers, and "Hoàn tác" brings it back before
/// the restore is sent. A refused request puts things back, with a toast.
/// Returns true once the server has deleted the camera.
Future<bool> deleteCameraFlow(
  BuildContext context,
  WidgetRef ref,
  Camera camera,
) async {
  if (!await confirmDeleteCamera(context, camera.name) || !context.mounted) {
    return false;
  }
  final router = GoRouter.of(context);
  final actions = ref.read(cameraActionsProvider);
  // This screen is gone by the time the server answers; the root overlay
  // (where toasts live) and the colors are not.
  final overlay = Overlay.of(context, rootOverlay: true);
  final colors = context.mpColors;
  void failed() => showMpToastIn(
    overlay,
    _actionFailedToast(colors),
    duration: _failedToastDuration,
  );

  final deleting = actions.delete(camera);
  showCameraDeletedToast(
    context,
    cameraName: camera.name,
    onUndo: () => unawaited(
      actions
          .restore(camera.id, camera: camera)
          .then((_) {}, onError: (Object _) => failed()),
    ),
  );
  router.go(AppRoutes.monitor);
  try {
    await deleting;
  } on MpException {
    failed();
    return false;
  }
  return true;
}

void showCameraDeletedToast(
  BuildContext context, {
  required String cameraName,
  required VoidCallback onUndo,
  Duration? duration = MpToast.undoDuration,
}) {
  final c = context.mpColors;
  showMpToast(
    context,
    MpToast(
      icon: MpDuotoneIcon(
        MpIcons.trash,
        outline: c.textPrimary,
        accent: c.textPrimary,
        size: 18,
      ),
      title: 'Đã xoá camera · $cameraName',
      actionLabel: 'Hoàn tác',
      onAction: onUndo,
    ),
    duration: duration,
  );
}

void showCameraPlainToast(BuildContext context, String title) {
  final c = context.mpColors;
  showMpToast(
    context,
    MpToast(
      icon: MpDuotoneIcon(
        MpIcons.check,
        outline: c.statusOk,
        accent: c.statusOk,
        size: 18,
      ),
      title: title,
    ),
    duration: const Duration(seconds: 4),
  );
}

void showCameraActionFailedToast(BuildContext context) => showMpToast(
  context,
  _actionFailedToast(context.mpColors),
  duration: _failedToastDuration,
);

const _failedToastDuration = Duration(seconds: 4);

MpToast _actionFailedToast(MpColors c) => MpToast(
  icon: MpDuotoneIcon(
    MpIcons.alert,
    outline: c.statusWarn,
    accent: c.statusWarn,
    size: 18,
  ),
  title: 'Chưa làm được. Kiểm tra kết nối rồi thử lại.',
);
