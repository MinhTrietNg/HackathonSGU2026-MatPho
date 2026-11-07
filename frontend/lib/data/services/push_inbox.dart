library;

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'push_message.dart';
import 'push_source.dart';

final class PushInbox {
  PushInbox(this._source) {
    _subscriptions = [
      _pipe(_source.received, _received),
      _pipe(_source.handledInBackground, _handledInBackground),
      _pipe(_source.opened, _opened),
    ];
  }

  final PushMessageSource _source;
  late final List<StreamSubscription<Object?>> _subscriptions;
  final _received = StreamController<PushMessage>.broadcast();
  final _handledInBackground = StreamController<PushMessage>.broadcast();
  final _opened = StreamController<PushMessage>.broadcast();

  Stream<PushMessage> get received => _received.stream;

  Stream<PushMessage> get handledInBackground => _handledInBackground.stream;

  Stream<PushMessage> get opened => _opened.stream;

  Future<PushMessage?> initialOpened() async {
    final data = await _source.initialOpened();
    return data == null ? null : PushMessage.decode(data);
  }

  Stream<void> get testAlertPushes => _mergeTestAlerts();

  Stream<void> _mergeTestAlerts() {
    late final StreamController<void> out;
    final subscriptions = <StreamSubscription<PushMessage>>[];
    void forward(PushMessage m) {
      if (m is TestAlertPush) out.add(null);
    }

    out = StreamController<void>(
      onListen: () => subscriptions
        ..add(received.listen(forward))
        ..add(handledInBackground.listen(forward)),
      onCancel: () async {
        for (final s in subscriptions) {
          await s.cancel();
        }
        subscriptions.clear();
      },
    );
    return out.stream;
  }

  void dispose() {
    for (final s in _subscriptions) {
      unawaited(s.cancel());
    }
    _received.close();
    _handledInBackground.close();
    _opened.close();
  }

  static StreamSubscription<Object?> _pipe(
    Stream<Map<String, Object?>> from,
    StreamController<PushMessage> to,
  ) => from.listen((data) {
    final message = PushMessage.decode(data);
    if (message != null && !to.isClosed) to.add(message);
  }, onError: (Object _) {});
}

final pushMessageSourceProvider = Provider<PushMessageSource>(
  (ref) => const NoPushMessageSource(),
);

final pushInboxProvider = Provider<PushInbox>((ref) {
  final inbox = PushInbox(ref.watch(pushMessageSourceProvider));
  ref.onDispose(inbox.dispose);
  return inbox;
});
