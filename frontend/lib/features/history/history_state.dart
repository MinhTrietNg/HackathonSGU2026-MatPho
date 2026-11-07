import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/errors.dart';
import '../../data/models/fire_event.dart';
import '../../data/providers.dart';
import '../auth/auth_session.dart';

final historyFilterProvider =
    NotifierProvider<HistoryFilterNotifier, HistoryFilter>(
      HistoryFilterNotifier.new,
    );

class HistoryFilterNotifier extends Notifier<HistoryFilter> {
  HistoryFilterNotifier([this.initial = HistoryFilter.all]);

  final HistoryFilter initial;

  @override
  HistoryFilter build() {
    ref.watch(sessionUserIdProvider);
    return initial;
  }

  void select(HistoryFilter filter) => state = filter;
}

final historyListProvider =
    FutureProvider.family<List<FireEvent>, HistoryFilter>((ref, filter) {
      ref.watch(sessionUserIdProvider);
      return _withTimeout(
        ref,
        ref.watch(historyRepositoryProvider).list(filter: filter),
      );
    }, retry: _noRetry);

final historyDetailProvider = FutureProvider.autoDispose
    .family<FireEvent, String>(
      (ref, eventId) => _withTimeout(
        ref,
        ref.watch(historyRepositoryProvider).detail(eventId),
      ),
      retry: _noRetry,
    );

Duration? _noRetry(int retryCount, Object error) => null;

Future<T> _withTimeout<T>(Ref ref, Future<T> load) {
  final result = Completer<T>();
  final timer = Timer(historyLoadTimeout, () {
    if (!result.isCompleted) result.completeError(const ServerException());
  });
  ref.onDispose(timer.cancel);
  load.then(
    (value) {
      timer.cancel();
      if (!result.isCompleted) result.complete(value);
    },
    onError: (Object error, StackTrace stack) {
      timer.cancel();
      if (!result.isCompleted) result.completeError(error, stack);
    },
  );
  return result.future;
}
