library;

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mat_pho/data/remote/auth_remote.dart';
import 'package:mat_pho/data/remote/core/api_client.dart';
import 'package:mat_pho/data/remote/core/ws_client.dart';
import 'package:mat_pho/data/remote/settings_remote.dart';
import 'package:mat_pho/data/session/push_token_source.dart';

import '../../fakes/remote_doubles.dart';

http.Response jsonResponse(Object? json, [int status = 200]) => http.Response(
  jsonEncode(json),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

http.Response errorResponse(
  int status,
  String code, [
  Map<String, Object?>? details,
]) => jsonResponse({
  'error': {'code': code, 'message': code, 'details': ?details},
}, status);

const contractUser = {
  'user_id': 'usr_abc123',
  'phone_number': '+84912345678',
  'full_name': 'Nguyễn Minh Anh',
  'loud_when_silent': true,
  'personal_group_id': 'grp_personal_usr_abc123',
};

final class FixedPushTokenSource implements PushTokenSource {
  FixedPushTokenSource([this.value]);

  String? value;

  @override
  Future<String?> token() async => value;

  @override
  Stream<String> get onTokenRefresh => const Stream.empty();
}

typedef Route = FutureOr<http.Response> Function(http.Request request);

final class RemoteHarness {
  RemoteHarness({
    String? idToken,
    String? pushToken = 'fcm_device_token_xyz',
    Duration apiTimeout = const Duration(seconds: 15),
  }) : tokens = FakeAuthTokenSource(token: idToken),
       push = FixedPushTokenSource(pushToken) {
    api = ApiClient(
      config: testApiConfig,
      tokens: tokens,
      timeout: apiTimeout,
      httpClient: MockClient((request) async {
        requests.add(request);
        final route = routes['${request.method} ${request.url.path}'];
        if (route == null) {
          return errorResponse(404, 'NOT_FOUND');
        }
        return route(request);
      }),
    );
    ws = WsClient(
      config: testApiConfig,
      tokens: tokens,
      minBackoff: const Duration(milliseconds: 1),
      maxBackoff: const Duration(milliseconds: 4),
      channelFactory: (uri, headers) {
        final channel = FakeWsChannel(uri, headers);
        channels.add(channel);
        return channel;
      },
    );
    session = RemoteSession(tokens: tokens, store: store, ws: ws);
  }

  final FakeAuthTokenSource tokens;
  final FixedPushTokenSource push;
  final store = MemorySessionStore();
  final requests = <http.Request>[];
  final channels = <FakeWsChannel>[];

  final routes = <String, Route>{};

  late final ApiClient api;
  late final WsClient ws;
  late final RemoteSession session;

  void on(String method, String path, Route route) =>
      routes['$method /api/v1$path'] = route;

  RemoteAuthRepository auth({
    DateTime Function()? now,
    Duration restoreWait = const Duration(seconds: 1),
  }) => RemoteAuthRepository(
    api: api,
    session: session,
    push: push,
    now: now ?? () => DateTime.utc(2026, 11, 4, 12),
    restoreWait: restoreWait,
  );

  RemoteSettingsRepository settings({
    Stream<void> testAlertPushes = const Stream.empty(),
    Duration testAlertTimeout = const Duration(seconds: 20),
  }) => RemoteSettingsRepository(
    api: api,
    session: session,
    push: push,
    testAlertPushes: testAlertPushes,
    testAlertTimeout: testAlertTimeout,
  );

  http.Request get last => requests.last;

  Map<String, Object?> bodyOf(http.Request request) =>
      jsonDecode(request.body) as Map<String, Object?>;

  Future<void> dispose() async {
    await ws.dispose();
    api.close();
  }
}
