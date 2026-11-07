import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/fire_event.dart';
import 'package:mat_pho/data/repositories/history_repository.dart';
import 'fake_scenario.dart';
import 'fake_world.dart';

final class FakeHistoryRepository implements HistoryRepository {
  FakeHistoryRepository(this._world);

  final FakeWorld _world;

  @override
  Future<List<FireEvent>> list({
    HistoryFilter filter = HistoryFilter.all,
  }) async {
    await _load();
    final since = _world.now().subtract(historyRetention);
    final rows = [
      for (final e in _world.events)
        if (filter.matches(e.status) && e.detectedAt.isAfter(since)) e,
    ]..sort((a, b) => b.detectedAt.compareTo(a.detectedAt));
    return rows;
  }

  @override
  Future<FireEvent> detail(String eventId) async {
    await _load();
    return _world.event(eventId);
  }

  Future<void> _load() async {
    await _world.delay();
    final s = _world.scenario;
    if (s.has(FakeCase.historyNetworkError)) throw const NetworkException();
    if (s.has(FakeCase.historyServerError)) throw const ServerException();
  }
}
