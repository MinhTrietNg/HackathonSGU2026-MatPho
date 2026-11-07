library;

import 'dart:async';
import 'dart:io' show WebSocketException;

import 'package:mat_pho/data/remote/core/api_config.dart';
import 'package:mat_pho/data/session/auth_token_source.dart';
import 'package:mat_pho/data/session/session_store.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

const testApiConfig = ApiConfig(
  baseUrl: 'https://api.test/api/v1',
  wsUrl: 'wss://api.test/api/v1/ws',
);

final class FakeAuthTokenSource implements AuthTokenSource {
  FakeAuthTokenSource({this.token, this.refreshedToken});

  String? token;

  String? refreshedToken;

  int refreshCount = 0;
  final customTokens = <String>[];

  @override
  Future<void> signInWithCustomToken(String customToken) async {
    customTokens.add(customToken);
    token = 'id-for-$customToken';
  }

  @override
  Future<String?> idToken({bool forceRefresh = false}) async {
    if (forceRefresh) {
      refreshCount++;
      if (refreshedToken != null) token = refreshedToken;
    }
    return token;
  }

  @override
  Future<void> signOut() async => token = null;

  @override
  bool get isSignedIn => token != null;
}

final class MemorySessionStore implements SessionStore {
  Map<String, Object?>? user;

  @override
  Future<void> save(Map<String, Object?> user) async => this.user = user;

  @override
  Future<Map<String, Object?>?> read() async => user;

  @override
  Future<void> clear() async => user = null;
}

final class FakeWsChannel implements WebSocketChannel {
  FakeWsChannel(this.uri, this.headers);

  final Uri uri;
  final Map<String, String> headers;

  final _ready = Completer<void>();
  final _incoming = StreamController<Object?>();
  late final _sink = _FakeSink(this);

  bool closedByClient = false;
  int? _closeCode;

  void accept() => _ready.complete();

  void refuse({bool refused = true}) => _ready.completeError(
    WebSocketChannelException.from(
      refused
          ? const WebSocketException('not upgraded, HTTP status code: 403')
          : Exception('no network'),
    ),
  );

  void serverSends(Object? data) => _incoming.add(data);

  void serverCloses([int? code]) {
    _closeCode = code;
    _incoming.close();
  }

  @override
  Future<void> get ready => _ready.future;

  @override
  Stream<Object?> get stream => _incoming.stream;

  @override
  WebSocketSink get sink => _sink;

  @override
  int? get closeCode => _closeCode;

  @override
  String? get closeReason => null;

  @override
  String? get protocol => null;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

final class _FakeSink implements WebSocketSink {
  _FakeSink(this._channel);

  final FakeWsChannel _channel;

  @override
  Future<void> close([int? closeCode, String? closeReason]) async {
    _channel.closedByClient = true;
    if (!_channel._incoming.isClosed) unawaited(_channel._incoming.close());
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
