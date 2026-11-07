library;

import 'dart:async';

import 'package:mat_pho/data/models/fire_event.dart';
import 'package:mat_pho/data/repositories/alert_repository.dart';
import 'package:mat_pho/data/services/push_source.dart';
import 'package:mat_pho/data/session/push_token_source.dart';

final class FakePushMessageSource implements PushMessageSource {
  final _received = StreamController<Map<String, Object?>>.broadcast();
  final _handled = StreamController<Map<String, Object?>>.broadcast();
  final _opened = StreamController<Map<String, Object?>>.broadcast();

  Map<String, Object?>? initial;

  void receive(Map<String, Object?> data) => _received.add(data);
  void handleInBackground(Map<String, Object?> data) => _handled.add(data);
  void open(Map<String, Object?> data) => _opened.add(data);

  @override
  Stream<Map<String, Object?>> get received => _received.stream;

  @override
  Stream<Map<String, Object?>> get handledInBackground => _handled.stream;

  @override
  Stream<Map<String, Object?>> get opened => _opened.stream;

  @override
  Future<Map<String, Object?>?> initialOpened() async => initial;
}

final class FakePushTokenSource implements PushTokenSource {
  FakePushTokenSource([this.current]);

  String? current;
  final _refresh = StreamController<String>.broadcast();

  void refresh(String token) {
    current = token;
    _refresh.add(token);
  }

  @override
  Future<String?> token() async => current;

  @override
  Stream<String> get onTokenRefresh => _refresh.stream;
}

class GetAlertRepository implements AlertRepository {
  GetAlertRepository({this.events = const {}, this.error});

  final Map<String, FireEvent> events;
  final Object? error;
  final fetched = <String>[];

  @override
  Future<FireEvent> getAlert(String eventId) async {
    fetched.add(eventId);
    final e = error;
    if (e != null) throw e;
    return events[eventId] ?? (throw StateError('No event $eventId'));
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
