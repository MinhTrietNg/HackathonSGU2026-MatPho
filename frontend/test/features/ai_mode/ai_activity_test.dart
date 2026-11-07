import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/features/ai_mode/ai_mode_state.dart';

// 2025-10-20 is a Monday.
DateTime _at(int weekday, int hour, int minute) =>
    DateTime(2025, 10, 19 + weekday, hour, minute);

CameraAi _scheduled(List<AiPause> pauses) =>
    CameraAi(mode: AiMode.scheduled, pauses: pauses);

void main() {
  const cooking = AiPause(from: 17 * 60, to: 19 * 60 + 30);
  const night = AiPause(from: 22 * 60, to: 6 * 60, days: {DateTime.friday});

  test('always on scans and off is off, whatever the time', () {
    final now = _at(DateTime.thursday, 18, 0);
    expect(aiActivityAt(CameraAi.alwaysOn, now), AiActivity.scanning);
    expect(aiActivityAt(CameraAi.off, now), AiActivity.off);
    expect(
      aiActivityAt(const CameraAi(mode: AiMode.off, pauses: [cooking]), now),
      AiActivity.off,
    );
  });

  test('a same-day window pauses inside it, from inclusive, to exclusive', () {
    final ai = _scheduled([cooking]);
    expect(aiActivityAt(ai, _at(3, 16, 59)), AiActivity.scanning);
    expect(aiActivityAt(ai, _at(3, 17, 0)), AiActivity.paused);
    expect(aiActivityAt(ai, _at(3, 18, 15)), AiActivity.paused);
    expect(aiActivityAt(ai, _at(3, 19, 29)), AiActivity.paused);
    expect(aiActivityAt(ai, _at(3, 19, 30)), AiActivity.scanning);
  });

  test('a window only pauses on its days', () {
    final ai = _scheduled([
      cooking.copyWith(days: {DateTime.saturday, DateTime.sunday}),
    ]);
    expect(aiActivityAt(ai, _at(DateTime.friday, 18, 0)), AiActivity.scanning);
    expect(aiActivityAt(ai, _at(DateTime.saturday, 18, 0)), AiActivity.paused);
  });

  test('an overnight window runs from its day into the next morning', () {
    final ai = _scheduled([night]);
    expect(aiActivityAt(ai, _at(DateTime.friday, 21, 59)), AiActivity.scanning);
    expect(aiActivityAt(ai, _at(DateTime.friday, 22, 0)), AiActivity.paused);
    expect(aiActivityAt(ai, _at(DateTime.friday, 23, 59)), AiActivity.paused);
    expect(aiActivityAt(ai, _at(DateTime.saturday, 0, 0)), AiActivity.paused);
    expect(aiActivityAt(ai, _at(DateTime.saturday, 5, 59)), AiActivity.paused);
    expect(aiActivityAt(ai, _at(DateTime.saturday, 6, 0)), AiActivity.scanning);
    expect(
      aiActivityAt(ai, _at(DateTime.saturday, 22, 0)),
      AiActivity.scanning,
    );
    expect(aiActivityAt(ai, _at(DateTime.friday, 3, 0)), AiActivity.scanning);
  });

  test('a window starting Sunday night covers Monday morning', () {
    final ai = _scheduled([
      night.copyWith(days: {DateTime.sunday}),
    ]);
    expect(aiActivityAt(ai, _at(DateTime.sunday, 23, 0)), AiActivity.paused);
    expect(aiActivityAt(ai, _at(DateTime.monday, 3, 0)), AiActivity.paused);
    expect(aiActivityAt(ai, _at(DateTime.monday, 22, 0)), AiActivity.scanning);
    expect(aiActivityAt(ai, _at(DateTime.sunday, 3, 0)), AiActivity.scanning);
  });

  test('any of several windows pauses', () {
    final ai = _scheduled([cooking, const AiPause(from: 11 * 60, to: 13 * 60)]);
    expect(aiActivityAt(ai, _at(2, 12, 0)), AiActivity.paused);
    expect(aiActivityAt(ai, _at(2, 18, 0)), AiActivity.paused);
    expect(aiActivityAt(ai, _at(2, 14, 0)), AiActivity.scanning);
    expect(
      aiActivityAt(_scheduled(const []), _at(2, 12, 0)),
      AiActivity.scanning,
    );
  });
}
