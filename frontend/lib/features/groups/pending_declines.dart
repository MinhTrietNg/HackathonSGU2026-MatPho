import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/widgets/mp_toast.dart';
import '../../data/errors.dart';
import '../../data/providers.dart';
import '../../data/repositories/group_repository.dart';
import '../auth/auth_session.dart';
import 'group_state.dart' show myInvitationsProvider;

final pendingDeclinesProvider = NotifierProvider<PendingDeclines, Set<String>>(
  PendingDeclines.new,
);

class PendingDeclines extends Notifier<Set<String>> {
  final _timers = <String, Timer>{};
  GroupRepository? _repository;
  var _live = false;

  @override
  Set<String> build() {
    ref.watch(sessionUserIdProvider);
    final previous = _repository;
    if (previous != null) {
      for (final invitationId in _timers.keys) {
        unawaited(_send(previous, invitationId));
      }
    }
    _timers.clear();
    _repository = ref.watch(groupRepositoryProvider);
    _live = true;
    final beforeLogout = ref.read(beforeLogoutProvider)..add(flushAll);
    ref.onDispose(() {
      _live = false;
      beforeLogout.remove(flushAll);
      for (final timer in _timers.values) {
        timer.cancel();
      }
    });
    return const {};
  }

  void schedule(String invitationId) {
    _timers.remove(invitationId)?.cancel();
    _timers[invitationId] = Timer(
      MpToast.undoDuration,
      () => unawaited(flush(invitationId)),
    );
    state = {...state, invitationId};
  }

  bool cancel(String invitationId) {
    final timer = _timers.remove(invitationId);
    timer?.cancel();
    if (timer != null) state = {...state}..remove(invitationId);
    return timer != null;
  }

  Future<void> flush(String invitationId) async {
    final repository = _repository;
    if (!_live || repository == null) return;
    final timer = _timers.remove(invitationId);
    if (timer == null) return;
    timer.cancel();
    await _send(repository, invitationId);
    if (!_live) return;
    ref.invalidate(myInvitationsProvider);
    state = {...state}..remove(invitationId);
  }

  Future<void> flushAll() => Future.wait([
    for (final invitationId in [..._timers.keys]) flush(invitationId),
  ]);
}

Future<void> _send(GroupRepository repository, String invitationId) async {
  try {
    await repository.declineInvitation(invitationId);
  } on MpException {
    // Already answered or withdrawn, or offline: the reload shows what the
    // server has.
  }
}
