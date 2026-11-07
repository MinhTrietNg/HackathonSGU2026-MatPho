library;

import 'dart:async';
import 'dart:isolate';
import 'dart:ui' show IsolateNameServer;

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import '../session/push_token_source.dart';

final class FirebasePushTokenSource implements PushTokenSource {
  FirebasePushTokenSource([FirebaseMessaging? messaging])
    : _injected = messaging;

  final FirebaseMessaging? _injected;

  FirebaseMessaging get _messaging => _injected ?? FirebaseMessaging.instance;

  @override
  Future<String?> token() async {
    try {
      // ignore: deprecated_member_use
      final token = await _messaging.getToken();
      return token == null || token.isEmpty ? null : token;
    } on Object catch (error) {
      debugPrint('Push token unavailable: ${error.runtimeType}');
      return null;
    }
  }

  @override
  Stream<String> get onTokenRefresh {
    try {
      // ignore: deprecated_member_use
      return _messaging.onTokenRefresh;
    } on Object catch (error) {
      debugPrint('Push token refresh unavailable: ${error.runtimeType}');
      return const Stream.empty();
    }
  }
}

abstract interface class PushMessageSource {
  Stream<Map<String, Object?>> get received;

  Stream<Map<String, Object?>> get handledInBackground;

  Stream<Map<String, Object?>> get opened;

  Future<Map<String, Object?>?> initialOpened();
}

final class NoPushMessageSource implements PushMessageSource {
  const NoPushMessageSource();

  @override
  Stream<Map<String, Object?>> get received => const Stream.empty();

  @override
  Stream<Map<String, Object?>> get handledInBackground => const Stream.empty();

  @override
  Stream<Map<String, Object?>> get opened => const Stream.empty();

  @override
  Future<Map<String, Object?>?> initialOpened() async => null;
}

final class FirebasePushMessageSource implements PushMessageSource {
  FirebasePushMessageSource([FirebaseMessaging? messaging])
    : _injected = messaging {
    _appIsolate = this;
    IsolateNameServer.removePortNameMapping(_portName);
    IsolateNameServer.registerPortWithName(_port.sendPort, _portName);
  }

  final FirebaseMessaging? _injected;

  FirebaseMessaging get _messaging => _injected ?? FirebaseMessaging.instance;

  static const _portName = 'mp.push.handled_in_background';

  static FirebasePushMessageSource? _appIsolate;

  final _port = ReceivePort();

  final _local = StreamController<Map<String, Object?>>();

  static bool deliverInAppIsolate(Map<String, Object?> data) {
    final source = _appIsolate;
    if (source == null) return false;
    source._local.add(data);
    return true;
  }

  static void relayFromBackground(Map<String, String> data) {
    IsolateNameServer.lookupPortByName(_portName)?.send(data);
  }

  @override
  late final Stream<Map<String, Object?>> received = () {
    final out = StreamController<Map<String, Object?>>.broadcast();
    StreamSubscription<Object?>? fcm;
    StreamSubscription<Object?>? local;
    out.onListen = () {
      fcm ??= FirebaseMessaging.onMessage.listen(
        (m) => out.add(m.data),
        onError: (Object _) {},
      );
      local ??= _local.stream.listen(out.add);
    };
    return out.stream;
  }();

  @override
  late final Stream<Map<String, Object?>> handledInBackground = _port
      .where((m) => m is Map)
      .map((m) => Map<String, Object?>.from(m as Map))
      .asBroadcastStream();

  @override
  late final Stream<Map<String, Object?>> opened = FirebaseMessaging
      .onMessageOpenedApp
      .map((m) => m.data)
      .handleError((Object _) {})
      .asBroadcastStream();

  @override
  Future<Map<String, Object?>?> initialOpened() async {
    try {
      return (await _messaging.getInitialMessage())?.data;
    } on Object catch (error) {
      debugPrint('Initial push unavailable: ${error.runtimeType}');
      return null;
    }
  }
}
