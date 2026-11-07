import '../models/fire_event.dart';

abstract interface class HistoryRepository {
  Future<List<FireEvent>> list({HistoryFilter filter = HistoryFilter.all});

  Future<FireEvent> detail(String eventId);
}
