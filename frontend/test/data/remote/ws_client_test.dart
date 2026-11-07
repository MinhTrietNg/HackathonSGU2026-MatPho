import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/remote/core/api_config.dart';
import 'package:mat_pho/data/remote/core/ws_client.dart';

import '../../fakes/remote_doubles.dart';

void main() {
  late FakeAuthTokenSource tokens;
  late List<FakeWsChannel> channels;
  late WsClient ws;
  late List<WsConnectionState> states;

  Future<FakeWsChannel> channel(int index) async {
    for (var i = 0; channels.length <= index; i++) {
      if (i > 500) fail('channel $index never opened');
      await Future<void>.delayed(const Duration(milliseconds: 1));
    }
    return channels[index];
  }

  setUp(() {
    tokens = FakeAuthTokenSource(token: 'tok-1');
    channels = [];
    states = [];
    ws = WsClient(
      config: testApiConfig,
      tokens: tokens,
      minBackoff: const Duration(milliseconds: 1),
      maxBackoff: const Duration(milliseconds: 4),
      channelFactory: (uri, headers) {
        final c = FakeWsChannel(uri, headers);
        channels.add(c);
        return c;
      },
    );
    ws.states.listen(states.add);
  });

  tearDown(() => ws.dispose());

  test('handshake sends the token in the Authorization header', () async {
    ws.connect();
    final c = await channel(0);
    expect(c.uri.toString(), 'wss://api.test/api/v1/ws');
    expect(c.headers, {'Authorization': 'Bearer tok-1'});
    expect(ws.state, WsConnectionState.disconnected);

    c.accept();
    await pumpEventQueue();
    expect(ws.state, WsConnectionState.connected);
  });

  test('messages are decoded by type; malformed ones dropped', () async {
    final received = <WsMessage>[];
    final alerts = <WsMessage>[];
    ws.messages.listen(received.add);
    ws.ofType('FIRE_ALERT').listen(alerts.add);
    ws.connect();
    final c = await channel(0);
    c.accept();
    await pumpEventQueue();

    c.serverSends(
      jsonEncode({
        'type': 'CAMERA_HEARTBEAT',
        'cam_id': 'cam_charger',
        'status': 'ONLINE',
        'fps': 5,
      }),
    );
    c.serverSends('not json');
    c.serverSends(jsonEncode({'no_type': 1}));
    c.serverSends(jsonEncode([1, 2]));
    c.serverSends(jsonEncode({'type': 'FIRE_ALERT', 'alert_id': 'alt_1001'}));
    await pumpEventQueue();

    expect(received.map((m) => m.type), ['CAMERA_HEARTBEAT', 'FIRE_ALERT']);
    expect(received.first.json['cam_id'], 'cam_charger');
    expect(alerts.single.json['alert_id'], 'alt_1001');
  });

  test('reconnects after a drop; the state stream follows', () async {
    ws.connect();
    (await channel(0)).accept();
    await pumpEventQueue();

    channels[0].serverCloses();
    await pumpEventQueue();
    expect(ws.state, WsConnectionState.disconnected);

    final second = await channel(1);
    expect(second.headers, {'Authorization': 'Bearer tok-1'});
    second.accept();
    await pumpEventQueue();

    expect(ws.state, WsConnectionState.connected);
    expect(states, [
      WsConnectionState.connected,
      WsConnectionState.disconnected,
      WsConnectionState.connected,
    ]);
  });

  test('retries a failed connection (no network) with the header', () async {
    ws.connect();
    (await channel(0)).refuse(refused: false);
    final second = await channel(1);
    expect(second.headers, {'Authorization': 'Bearer tok-1'});
    expect(second.uri.queryParameters, isEmpty);
    expect(tokens.refreshCount, 0);
  });

  test('a refused header handshake falls back to ?token=', () async {
    tokens.refreshedToken = 'tok-2';
    ws.connect();
    (await channel(0)).refuse();

    final viaQuery = await channel(1);
    expect(viaQuery.headers, isEmpty);
    expect(viaQuery.uri.queryParameters, {'token': 'tok-2'});
    expect(tokens.refreshCount, 1);

    viaQuery.refuse();
    final third = await channel(2);
    expect(third.headers, {'Authorization': 'Bearer tok-2'});
    expect(third.uri.queryParameters, isEmpty);
  });

  test('close code 1008 refreshes the token before reconnecting', () async {
    tokens.refreshedToken = 'tok-2';
    ws.connect();
    (await channel(0)).accept();
    await pumpEventQueue();
    channels[0].serverCloses(1008);

    final second = await channel(1);
    expect(second.headers, {'Authorization': 'Bearer tok-2'});
    expect(tokens.refreshCount, 1);
  });

  test('disconnect closes the socket and stops reconnecting', () async {
    ws.connect();
    final c = await channel(0);
    c.accept();
    await pumpEventQueue();

    await ws.disconnect();
    expect(c.closedByClient, isTrue);
    expect(ws.state, WsConnectionState.disconnected);
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(channels, hasLength(1));

    ws.connect();
    (await channel(1)).accept();
    await pumpEventQueue();
    expect(ws.state, WsConnectionState.connected);
  });

  test('disconnect during the handshake drops that attempt', () async {
    ws.connect();
    final c = await channel(0);
    await ws.disconnect();
    c.accept();
    await Future<void>.delayed(const Duration(milliseconds: 20));
    expect(ws.state, WsConnectionState.disconnected);
    expect(states, isEmpty);
    expect(channels, hasLength(1));
  });

  test('signed out: no socket until a token exists', () async {
    tokens.token = null;
    ws.connect();
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(channels, isEmpty);

    tokens.token = 'tok-3';
    final c = await channel(0);
    expect(c.headers, {'Authorization': 'Bearer tok-3'});
  });

  test('connect() twice opens one socket', () async {
    ws.connect();
    ws.connect();
    (await channel(0)).accept();
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(channels, hasLength(1));
  });

  test('missing WS_URL fails at connect()', () {
    final unconfigured = WsClient(
      config: const ApiConfig(),
      tokens: tokens,
      channelFactory: (uri, headers) => fail('should not connect'),
    );
    expect(unconfigured.connect, throwsA(isA<StateError>()));
  });
}
