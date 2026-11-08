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
          (
            group: group,
            cameras: [...cameras]..sort(_purgeFirst),
          ),
  ];
});

int _purgeFirst(TrashedCamera a, TrashedCamera b) =>
    (a.purgeAt ?? DateTime(0)).compareTo(b.purgeAt ?? DateTime(0));

final cameraActionsProvider = Provider<CameraActions>(CameraActions.new);

class CameraActions {
  CameraActions(this._ref);

  final Ref _ref;

  CameraRepository get _repo => _ref.read(cameraRepositoryProvider);

  Future<void> delete(Camera camera) async {
    await _repo.deleteCamera(camera.id);
    _refresh(camera);
  }

  Future<Camera> restore(String cameraId) async {
    final camera = await _repo.restoreCamera(cameraId);
    _refresh(camera);
    return camera;
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

/// I17 → E1 with an undo toast. Returns true once the camera is gone.
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
  try {
    await actions.delete(camera);
  } on MpException {
    if (context.mounted) showCameraActionFailedToast(context);
    return false;
  }
  // The toast lives in the root overlay, so it outlives this screen; shown
  // from here because the Navigator's own context has no overlay above it.
  if (context.mounted) {
    showCameraDeletedToast(
      context,
      cameraName: camera.name,
      onUndo: () => unawaited(
        actions.restore(camera.id).then((_) {}, onError: (Object _) {}),
      ),
    );
  }
  router.go(AppRoutes.monitor);
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

void showCameraActionFailedToast(BuildContext context) {
  final c = context.mpColors;
  showMpToast(
    context,
    MpToast(
      icon: MpDuotoneIcon(
        MpIcons.alert,
        outline: c.statusWarn,
        accent: c.statusWarn,
        size: 18,
      ),
      title: 'Chưa làm được. Kiểm tra kết nối rồi thử lại.',
    ),
    duration: const Duration(seconds: 4),
  );
}
