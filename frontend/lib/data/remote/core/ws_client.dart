library;

import 'dart:async';
import 'dart:convert';
import 'dart:io' show WebSocketException;
import 'dart:math' as math;

import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../../session/auth_token_source.dart';
import 'api_config.dart';

enum WsConnectionState { connected, disconnected }

final class WsMessage {
  const WsMessage(this.type, this.json);

  final String type;
  final Map<String, Object?> json;

  @override
  String toString() => 'WsMessage($type)';
}

typedef WsChannelFactory =
    WebSocketChannel Function(Uri uri, Map<String, String> headers);

final class WsClient {
  WsClient({
    required this._config,
    required this._tokens,
    WsChannelFactory? channelFactory,
    this.minBackoff = const Duration(seconds: 1),
    this.maxBackoff = const Duration(seconds: 30),
  }) : _factory = channelFactory ?? _ioChannel;

  final ApiConfig _config;
  final AuthTokenSource _tokens;
  final WsChannelFactory _factory;

  final Duration minBackoff;

  final Duration maxBackoff;

  final _messages = StreamController<WsMessage>.broadcast();
  final _states = StreamController<WsConnectionState>.broadcast();

  WsConnectionState _state = WsConnectionState.disconnected;
  bool _wanted = false;
  int _generation = 0;
  WebSocketChannel? _channel;
  StreamSubscription<Object?>? _subscription;
  Timer? _retry;
  int _failures = 0;
  bool _queryToken = false;
  bool _forceRefresh = false;

  Stream<WsMessage> get messages => _messages.stream;

  Stream<WsMessage> ofType(String type) =>
      messages.where((message) => message.type == type);

  Stream<WsConnectionState> get states => _states.stream;

  WsConnectionState get state => _state;

  void connect() {
    if (_wanted) return;
    _config.wsUri; // Fail here, not inside the reconnect loop.
    _wanted = true;
    unawaited(_open(_generation));
  }

  Future<void> disconnect() async {
    _wanted = false;
    _generation++;
    _retry?.cancel();
    _retry = null;
    _failures = 0;
    _queryToken = false;
    _forceRefresh = false;
    final channel = _channel;
    _channel = null;
    await _subscription?.cancel();
    _subscription = null;
    _setState(WsConnectionState.disconnected);
    _close(channel);
  }

  Future<void> dispose() async {
    await disconnect();
    await _messages.close();
    await _states.close();
  }

  Future<void> _open(int generation) async {
    bool stale() => generation != _generation || !_wanted;

    String? token;
    try {
      token = await _tokens.idToken(forceRefresh: _forceRefresh);
    } on Object {
      token = null;
    }
    if (stale()) return;
    if (token == null) {
      _scheduleRetry();
      return;
    }
    _forceRefresh = false;

    final viaQuery = _queryToken;
    final WebSocketChannel channel;
    try {
      final base = _config.wsUri;
      // Bearer header first; after a refused handshake, retry with ?token=.
      channel = viaQuery
          ? _factory(
              base.replace(
                queryParameters: {...base.queryParameters, 'token': token},
              ),
              const {},
            )
          : _factory(base, {'Authorization': 'Bearer $token'});
      _channel = channel;
      await channel.ready;
    } on Object catch (e) {
      if (stale()) return;
      _channel = null;
      if (_refused(e)) {
        _forceRefresh = true;
        _queryToken = !viaQuery;
        if (!viaQuery) return _open(generation);
      }
      _scheduleRetry();
      return;
    }

    if (stale()) {
      _close(channel);
      return;
    }
    _failures = 0;
    _subscription = channel.stream.listen(
      _onData,
      onError: (Object _) {},
      onDone: () => _onDone(generation, channel),
    );
    _setState(WsConnectionState.connected);
  }

  void _onData(Object? data) {
    if (data is! String) return;
    final Object? decoded;
    try {
      decoded = jsonDecode(data);
    } on FormatException {
      return;
    }
    if (decoded is Map<String, Object?> && decoded['type'] is String) {
      _messages.add(WsMessage(decoded['type'] as String, decoded));
    }
  }

  void _onDone(int generation, WebSocketChannel channel) {
    if (generation != _generation || !identical(channel, _channel)) return;
    _channel = null;
    _subscription = null;
    _setState(WsConnectionState.disconnected);
    if (channel.closeCode == 1008) _forceRefresh = true;
    _scheduleRetry();
  }

  void _scheduleRetry() {
    if (!_wanted) return;
    final factor = math.pow(2, math.min(_failures, 16)).toInt();
    final delay = minBackoff * factor;
    _failures++;
    final generation = _generation;
    _retry = Timer(
      delay < maxBackoff ? delay : maxBackoff,
      () => unawaited(_open(generation)),
    );
  }

  void _setState(WsConnectionState next) {
    if (next == _state) return;
    _state = next;
    if (!_states.isClosed) _states.add(next);
  }

  static bool _refused(Object error) =>
      error is WebSocketChannelException && error.inner is WebSocketException;

  static void _close(WebSocketChannel? channel) {
    if (channel == null) return;
    unawaited(
      Future.sync(channel.sink.close).then((_) {}, onError: (Object _) {}),
    );
  }

  static WebSocketChannel _ioChannel(Uri uri, Map<String, String> headers) =>
      IOWebSocketChannel.connect(
        uri,
        headers: headers,
        pingInterval: const Duration(seconds: 20),
        connectTimeout: const Duration(seconds: 15),
      );
}
