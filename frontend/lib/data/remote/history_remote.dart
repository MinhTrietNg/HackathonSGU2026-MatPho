library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/fire_event.dart';
import '../repositories/history_repository.dart';
import 'alert_remote.dart' show parseFireEvent;
import 'core/api_client.dart';
import 'core/json.dart';
import 'core/remote_providers.dart';

final class RemoteHistoryRepository implements HistoryRepository {
  RemoteHistoryRepository(
    this._api, {
    this.pageSize = 20,
    this.maxPages = 10,
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now;

  final ApiClient _api;
  final DateTime Function() _now;

  final int pageSize;

  final int maxPages;

  @override
  Future<List<FireEvent>> list({
    HistoryFilter filter = HistoryFilter.all,
  }) async {
    final rows = <String, FireEvent>{};
    String? cursor;
    for (var page = 0; page < maxPages; page++) {
      final json = await _api.get(
        '/alerts',
        query: {'filter': _wire(filter), 'limit': pageSize, 'cursor': cursor},
      );
      final (items, next) = _page(json);
      var added = 0;
      for (final event in items) {
        if (rows.containsKey(event.id)) continue;
        rows[event.id] = event;
        added++;
      }
      if (next == null || next == cursor || added == 0) break;
      cursor = next;
    }
    final since = _now().subtract(historyRetention);
    final inWindow = [
      for (final event in rows.values)
        if (filter.matches(event.status) && event.detectedAt.isAfter(since))
          event,
    ];
    final items = inWindow.isNotEmpty
        ? inWindow
        : [
            for (final event in rows.values)
              if (filter.matches(event.status)) event,
          ];
    return items..sort((a, b) => b.detectedAt.compareTo(a.detectedAt));
  }

  @override
  Future<FireEvent> detail(String eventId) async => parseFireEvent(
    asJsonMap(await _api.get('/alerts/${Uri.encodeComponent(eventId)}')),
  );

  static (List<FireEvent>, String?) _page(Object? json) {
    if (json is List<Object?>) {
      return (
        [
          for (final (i, item) in json.indexed)
            parseFireEvent(asJsonMap(item, 'items[$i]')),
        ],
        null,
      );
    }
    final map = asJsonMap(json);
    return (
      readObjectList(map, 'items', parseFireEvent),
      readStringOrNull(map, 'next_cursor'),
    );
  }

  static String _wire(HistoryFilter filter) => switch (filter) {
    HistoryFilter.all => 'all',
    HistoryFilter.fire => 'fire',
    HistoryFilter.dismissed => 'dismissed',
    HistoryFilter.falseAlarm => 'false_alarm',
  };
}

final remoteHistoryRepositoryProvider = Provider<HistoryRepository>(
  (ref) => RemoteHistoryRepository(ref.watch(apiClientProvider)),
);
