library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../errors.dart';
import '../remote/core/api_client.dart';
import '../remote/core/remote_providers.dart';
import '../session/push_token_source.dart';

final class PushTokenRegistrar {
  PushTokenRegistrar({required this._api, required this._tokens});

  final ApiClient _api;
  final PushTokenSource _tokens;

  static const path = '/users/me/fcm-tokens';

  StreamSubscription<String>? _refreshes;

  int _session = 0;

  Future<void> start() async {
    stop();
    final session = _session;
    _refreshes = _tokens.onTokenRefresh.listen(
      (token) => unawaited(_send(token, session)),
      onError: (Object _) {},
    );
    final token = await _tokens.token();
    if (token != null) await _send(token, session);
  }

  void stop() {
    _session++;
    unawaited(_refreshes?.cancel());
    _refreshes = null;
  }

  Future<void> _send(String token, int session) async {
    if (session != _session || token.isEmpty) return;
    try {
      await _api.post(path, body: {'fcm_token': token});
    } on MpException catch (error) {
      debugPrint('Push token not registered: $error');
    }
  }
}

final pushTokenRegistrarProvider = Provider<PushTokenRegistrar>((ref) {
  final registrar = PushTokenRegistrar(
    api: ref.watch(apiClientProvider),
    tokens: ref.watch(pushTokenSourceProvider),
  );
  ref.onDispose(registrar.stop);
  return registrar;
});
