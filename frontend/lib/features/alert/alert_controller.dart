import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show ProviderListenable;

import '../../data/models/models.dart';
import '../../data/providers.dart';
import '../../data/repositories/alert_repository.dart';
import '../groups/current_group.dart' show groupsProvider;
import '../groups/group_state.dart' show groupCamerasProvider;
import 'pending_alert_actions.dart';

final class AlertState {
  const AlertState(
    this.event, {
    this.closing = AlertClosing.unknown,
    this.canUndo = false,
  });

  final FireEvent event;
  final AlertClosing closing;
  final bool canUndo;
}

enum AlertClosing { unknown, denied, allowed }

/// Still to be handled: the siren rings and F2/F4 holds the user until
/// "Gọi 114", "Đã xử lý" or "Báo nhầm" (or someone else closes it).
bool alertStillOpen(FireEvent event) =>
    !event.resolved &&
    (event.status == EventStatus.fire ||
        event.status == EventStatus.unverified);

/// FIRE_ALERT events already received over the WebSocket, by id. F2/F4 shows
/// one at once instead of a blank screen, and keeps it if the fetch fails.
final receivedAlertsProvider =
    NotifierProvider<ReceivedAlerts, Map<String, FireEvent>>(
      ReceivedAlerts.new,
    );

class ReceivedAlerts extends Notifier<Map<String, FireEvent>> {
  @override
  Map<String, FireEvent> build() => const {};

  void remember(FireEvent event) => state = {...state, event.id: event};
}

final alertProvider = AsyncNotifierProvider.autoDispose
    .family<AlertNotifier, AlertState, String>(AlertNotifier.new);

class AlertNotifier extends AsyncNotifier<AlertState> {
  AlertNotifier(this.eventId);

  final String eventId;
  Timer? _undoTimer;
  var _generation = 0;

  ({PendingAlertActions sender, FireEvent before})? _resolving;

  @override
  Future<AlertState> build() async {
    final generation = ++_generation;
    // A reload keeps the actions on screen until the role is read again.
    final closing = state.value?.closing ?? AlertClosing.unknown;
    ref.onDispose(() {
      _undoTimer?.cancel();
      final resolving = _resolving;
      _resolving = null;
      if (resolving != null) unawaited(resolving.sender.flush(eventId));
    });
    final repository = ref.watch(alertRepositoryProvider);
    final updates = repository
        .alertUpdates()
        .where((update) => update.eventId == eventId)
        .listen(_onUpdate);
    ref.onDispose(updates.cancel);
    final received = ref.read(receivedAlertsProvider)[eventId];
    if (received != null) {
      unawaited(_refetch(repository, received, generation));
      unawaited(_loadRole(received.cameraId, generation));
      return AlertState(received, closing: closing);
    }
    final event = await repository.getAlert(eventId);
    unawaited(_loadRole(event.cameraId, generation));
    return AlertState(event, closing: closing);
  }

  // Swaps the WebSocket copy for the server's once it arrives, unless the
  // screen already moved on (resolved, false alarm). A failed fetch keeps it.
  Future<void> _refetch(
    AlertRepository repository,
    FireEvent received,
    int generation,
  ) async {
    final FireEvent event;
    try {
      event = await repository.getAlert(eventId);
    } on Object {
      return;
    }
    if (!ref.mounted || generation != _generation) return;
    await future;
    final now = state.value;
    if (now == null || !ref.mounted || generation != _generation) return;
    if (!identical(now.event, received)) return;
    state = AsyncData(
      AlertState(event, closing: now.closing, canUndo: now.canUndo),
    );
  }

  void _onUpdate(AlertUpdate update) {
    final now = state.value;
    if (now == null) return;
    _undoTimer?.cancel();
    _resolving = null;
    final event = switch (update.outcome) {
      AlertUpdateOutcome.falseAlarm => now.event.copyWith(
        status: EventStatus.falseAlarm,
      ),
      AlertUpdateOutcome.resolved => now.event.copyWith(
        resolved: true,
        resolvedByName: update.resolvedByName,
      ),
    };
    state = AsyncData(AlertState(event, closing: now.closing));
  }

  Future<void> _loadRole(String cameraId, int generation) async {
    final closing = await _canClose(cameraId)
        ? AlertClosing.allowed
        : AlertClosing.denied;
    if (!ref.mounted || generation != _generation) return;
    await future;
    final now = state.value;
    if (now == null || !ref.mounted || generation != _generation) return;
    state = AsyncData(
      AlertState(now.event, closing: closing, canUndo: now.canUndo),
    );
  }

  Future<bool> _canClose(String cameraId) async {
    final holds = <ProviderSubscription<Object?>>[];
    try {
      for (final group in await _load(groupsProvider, holds)) {
        final cameras = await _load(groupCamerasProvider(group.id), holds);
        if (cameras.any((c) => c.id == cameraId)) {
          return group.myRole != GroupRole.alertsOnly;
        }
      }
      return true;
    } on Object {
      return true;
    } finally {
      for (final hold in holds) {
        hold.close();
      }
    }
  }

  Future<T> _load<T>(
    ProviderListenable<AsyncValue<T>> provider,
    List<ProviderSubscription<Object?>> holds,
  ) {
    if (!ref.mounted) return Future.error(StateError('Alert disposed'));
    final done = Completer<T>();
    holds.add(
      ref.listen<AsyncValue<T>>(provider, (_, next) {
        if (done.isCompleted) return;
        if (next.hasError) {
          done.completeError(next.error!);
        } else if (next.hasValue) {
          done.complete(next.requireValue);
        }
      }, fireImmediately: true),
    );
    return done.future;
  }

  // "Đã xử lý" → F5 at once with "Hoàn tác"; the server is told only when the
  // undo window ends or F5 is left (pending_alert_actions.dart).
  void resolve() {
    final current = state.value;
    if (current == null ||
        current.closing != AlertClosing.allowed ||
        current.event.resolved) {
      return;
    }
    final sender = ref.read(pendingAlertActionsProvider.notifier)
      ..schedule(eventId, AlertOutcome.resolved);
    _resolving = (sender: sender, before: current.event);
    _undoTimer?.cancel();
    _undoTimer = Timer(undoWindow, () {
      _resolving = null;
      final now = state.value;
      if (now != null) {
        state = AsyncData(AlertState(now.event, closing: now.closing));
      }
    });
    state = AsyncData(
      AlertState(
        current.event.copyWith(resolved: true),
        closing: AlertClosing.allowed,
        canUndo: true,
      ),
    );
  }

  void undo() {
    final resolving = _resolving;
    if (resolving == null || !resolving.sender.cancel(eventId)) return;
    _resolving = null;
    _undoTimer?.cancel();
    state = AsyncData(
      AlertState(resolving.before, closing: AlertClosing.allowed),
    );
  }
}
