library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../session/auth_token_source.dart';
import '../../session/push_token_source.dart';
import '../../session/session_store.dart';
import 'api_client.dart';
import 'api_config.dart';
import 'ws_client.dart';

final apiConfigProvider = Provider<ApiConfig>(
  (ref) => const ApiConfig.fromEnvironment(),
);

final authTokenSourceProvider = Provider<AuthTokenSource>(
  (ref) => FirebaseAuthTokenSource(),
);

final sessionStoreProvider = Provider<SessionStore>(
  (ref) => SecureSessionStore(),
);

final pushTokenSourceProvider = Provider<PushTokenSource>(
  (ref) => const NoPushTokenSource(),
);

final apiClientProvider = Provider<ApiClient>((ref) {
  final client = ApiClient(
    config: ref.watch(apiConfigProvider),
    tokens: ref.watch(authTokenSourceProvider),
  );
  ref.onDispose(client.close);
  return client;
});

final wsClientProvider = Provider<WsClient>((ref) {
  final client = WsClient(
    config: ref.watch(apiConfigProvider),
    tokens: ref.watch(authTokenSourceProvider),
  );
  ref.onDispose(client.dispose);
  return client;
});

final sessionExpiredProvider = Provider<Stream<void>>(
  (ref) => ref.watch(apiClientProvider).sessionExpired,
);
