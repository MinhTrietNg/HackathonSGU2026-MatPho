import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/models.dart';
import '../../data/providers.dart';
import '../auth/auth_session.dart';
import '../groups/current_group.dart';
import '../groups/group_state.dart';

final aiGroupsProvider = FutureProvider<List<Group>>(
  (ref) async => [
    for (final g in await ref.watch(groupsProvider.future))
      if (!g.isPersonal || g.cameraCount > 0) g,
  ],
);

typedef AiGroupView = ({Group group, List<Camera> cameras, String? ownerName});

final aiGroupProvider = FutureProvider.family<AiGroupView, String>((
  ref,
  groupId,
) async {
  final groups = await ref.watch(groupsProvider.future);
  final group = groups.firstWhere(
    (g) => g.id == groupId,
    orElse: () => throw StateError('No group $groupId'),
  );
  final (cameras, members) = await (
    ref.watch(groupCamerasProvider(groupId).future),
    group.myRole.canManage
        ? Future.value(const <Member>[])
        : ref.watch(groupMembersProvider(groupId).future),
  ).wait;
  final owner = members.where((m) => m.role == GroupRole.owner).firstOrNull;
  return (group: group, cameras: cameras, ownerName: owner?.displayName);
});

typedef AiCamerasView = ({List<Group> groups, AiGroupView? selected});

// One provider for the whole H7 screen, watched from its first frame: the
// groups, the current group and the picked group's cameras load as one chain.
final aiCamerasViewProvider = FutureProvider.family<AiCamerasView, String?>((
  ref,
  pickedGroupId,
) async {
  final groups = await ref.watch(aiGroupsProvider.future);
  final id = pickedGroupId ?? (await ref.watch(currentGroupProvider.future)).id;
  final group =
      groups.where((g) => g.id == id).firstOrNull ?? groups.firstOrNull;
  return (
    groups: groups,
    selected: group == null
        ? null
        : await ref.watch(aiGroupProvider(group.id).future),
  );
});

typedef AiCameraView = ({Camera camera, Group group});

final aiCameraProvider = FutureProvider.autoDispose
    .family<AiCameraView, String>((ref, cameraId) async {
      ref.watch(sessionUserIdProvider);
      final camera = await ref
          .watch(cameraRepositoryProvider)
          .getCamera(cameraId);
      final groups = await ref.watch(groupsProvider.future);
      final group = groups.firstWhere(
        (g) => g.id == camera.groupId,
        orElse: () => throw StateError('No group has camera $cameraId'),
      );
      return (camera: camera, group: group);
    });

final aiModeActionsProvider = Provider<AiModeActions>(AiModeActions.new);

class AiModeActions {
  AiModeActions(this._ref);

  final Ref _ref;

  Future<Camera> save(Camera camera, CameraAi ai) async {
    final saved = await _ref
        .read(cameraRepositoryProvider)
        .updateCamera(cameraId: camera.id, ai: ai);
    _ref
      ..invalidate(groupCamerasProvider(camera.groupId))
      ..invalidate(aiCameraProvider(camera.id));
    return saved;
  }
}

const defaultAiPause = AiPause(from: 17 * 60, to: 19 * 60 + 30);

const extraAiPause = AiPause(from: 11 * 60, to: 13 * 60);

const maxAiPauses = 5;

const weekdayLabels = {
  DateTime.monday: 'T2',
  DateTime.tuesday: 'T3',
  DateTime.wednesday: 'T4',
  DateTime.thursday: 'T5',
  DateTime.friday: 'T6',
  DateTime.saturday: 'T7',
  DateTime.sunday: 'CN',
};

String formatClock(int minute) =>
    '${(minute ~/ 60).toString().padLeft(2, '0')}:'
    '${(minute % 60).toString().padLeft(2, '0')}';

String formatAiDays(Set<int> days) {
  bool exactly(Set<int> other) =>
      days.length == other.length && days.containsAll(other);
  if (exactly(AiPause.everyDay)) return 'mỗi ngày';
  if (exactly(const {DateTime.saturday, DateTime.sunday})) return 'cuối tuần';
  if (exactly(const {1, 2, 3, 4, 5})) return 'ngày thường';
  return [
    for (final MapEntry(key: day, value: name) in weekdayLabels.entries)
      if (days.contains(day)) name,
  ].join(', ');
}

String aiModeSummary(CameraAi ai, {bool locked = false}) => switch (ai.mode) {
  AiMode.alwaysOn => 'AI luôn bật · báo cháy 24/7',
  AiMode.scheduled => _pauseSummary(ai.pauses),
  AiMode.off => locked ? 'Chủ nhóm đã tắt AI' : 'Đã tắt AI · không báo cháy',
};

String _pauseSummary(List<AiPause> pauses) {
  final first = pauses.first;
  final more = pauses.length > 1 ? ' · +${pauses.length - 1} khung' : '';
  return 'Nghỉ AI ${formatClock(first.from)}–${formatClock(first.to)}'
      ' · ${formatAiDays(first.days)}$more';
}

String aiRolePhrase(GroupRole role) => switch (role) {
  GroupRole.owner => 'chủ nhóm',
  GroupRole.manager => 'quản lý',
  GroupRole.member => 'thành viên',
  GroupRole.alertsOnly => 'chỉ nhận báo cháy',
};

bool aiPauseValid(AiPause pause) =>
    pause.days.isNotEmpty && pause.from != pause.to;

enum AiActivity { scanning, paused, off }

// A window with from > to runs past midnight: `days` are the days it starts.
AiActivity aiActivityAt(CameraAi ai, DateTime now) {
  if (ai.mode == AiMode.off) return AiActivity.off;
  if (ai.mode == AiMode.alwaysOn) return AiActivity.scanning;
  final minute = now.hour * 60 + now.minute;
  final yesterday = now.weekday == DateTime.monday
      ? DateTime.sunday
      : now.weekday - 1;
  for (final p in ai.pauses) {
    final paused = p.from <= p.to
        ? p.days.contains(now.weekday) && minute >= p.from && minute < p.to
        : (p.days.contains(now.weekday) && minute >= p.from) ||
              (p.days.contains(yesterday) && minute < p.to);
    if (paused) return AiActivity.paused;
  }
  return AiActivity.scanning;
}

String aiActivityLabel(AiActivity activity) => switch (activity) {
  AiActivity.scanning => 'AI đang quét',
  AiActivity.paused => 'Nghỉ AI theo lịch',
  AiActivity.off => 'AI đã tắt',
};
