import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/group.dart';
import '../../data/providers.dart';
import '../auth/auth_session.dart';

final currentGroupIdProvider = NotifierProvider<CurrentGroup, String?>(
  CurrentGroup.new,
);

class CurrentGroup extends Notifier<String?> {
  @override
  String? build() {
    ref.watch(sessionUserIdProvider);
    return null;
  }

  void select(String groupId) => state = groupId;

  void clear() => state = null;
}

final groupsProvider = FutureProvider<List<Group>>((ref) {
  ref.watch(sessionUserIdProvider);
  return ref.watch(groupRepositoryProvider).listGroups();
});

Group defaultGroup(List<Group> groups) =>
    groups.where((g) => !g.isPersonal && g.cameraCount > 0).firstOrNull ??
    groups.firstWhere((g) => g.isPersonal);

final currentGroupProvider = FutureProvider<Group>((ref) async {
  final groups = await ref.watch(groupsProvider.future);
  final id = ref.watch(currentGroupIdProvider);
  return groups.where((g) => g.id == id).firstOrNull ?? defaultGroup(groups);
});
