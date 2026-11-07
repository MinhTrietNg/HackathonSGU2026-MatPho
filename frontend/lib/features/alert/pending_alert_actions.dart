import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/errors.dart';
import '../../data/models/fire_event.dart';
import '../../data/providers.dart';
import '../../data/repositories/alert_repository.dart';
import '../auth/auth_session.dart';
import '../history/history_state.dart' show historyListProvider;

enum AlertOutcome { resolved, falseAlarm }

final pendingAlertActionsProvider = NotifierProvider<PendingAlertActions, void>(
  PendingAlertActions.new,
);

class PendingAlertActions extends Notifier<void> {
  final _pending = <String, ({AlertOutcome outcome, Timer timer})>{};
  AlertRepository? _repository;
  var _live = false;

  @override
  void build() {
    ref.watch(sessionUserIdProvider);
    final previous = _repository;
    if (previous != null) {
      for (final MapEntry(key: eventId, value: action) in _pending.entries) {
        unawaited(_send(previous, eventId, action.outcome));
      }
    }
    _pending.clear();
    _repository = ref.watch(alertRepositoryProvider);
    _live = true;
    final beforeLogout = ref.read(beforeLogoutProvider)..add(flushAll);
    ref.onDispose(() {
      _live = false;
      beforeLogout.remove(flushAll);
      for (final action in _pending.values) {
        action.timer.cancel();
      }
    });
  }

  void schedule(String eventId, AlertOutcome outcome) {
    _pending.remove(eventId)?.timer.cancel();
    _pending[eventId] = (
      outcome: outcome,
      timer: Timer(undoWindow, () => unawaited(flush(eventId))),
    );
  }

  bool cancel(String eventId) {
    final action = _pending.remove(eventId);
    action?.timer.cancel();
    return action != null;
  }

  Future<void> flush(String eventId) async {
    final repository = _repository;
    if (!_live || repository == null) return;
    final action = _pending.remove(eventId);
    if (action == null) return;
    action.timer.cancel();
    await _send(repository, eventId, action.outcome);
    if (_live) ref.invalidate(historyListProvider);
  }

  Future<void> flushAll() => Future.wait([
    for (final eventId in [..._pending.keys]) flush(eventId),
  ]);
}

Future<void> _send(
  AlertRepository repository,
  String eventId,
  AlertOutcome outcome,
) async {
  try {
    await switch (outcome) {
      AlertOutcome.resolved => repository.resolve(eventId),
      AlertOutcome.falseAlarm => repository.markFalseAlarm(eventId),
    };
  } on MpException {
    // The alert has left the screen: nothing is there to show it.
  }
}
