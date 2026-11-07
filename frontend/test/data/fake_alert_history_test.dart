import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/errors.dart';
import '../fakes/fake_alert_repository.dart';
import '../fakes/fake_data.dart';
import '../fakes/fake_history_repository.dart';
import '../fakes/fake_scenario.dart';
import '../fakes/fake_world.dart';
import 'package:mat_pho/data/models/models.dart';

FakeWorld world([Set<FakeCase> cases = const {}]) =>
    FakeWorld(FakeScenario.test(cases: cases));

void main() {
  group('history (G1)', () {
    test('four rows verbatim, newest first', () async {
      final rows = await FakeHistoryRepository(world()).list();
      expect(rows.map((e) => e.summary), [
        'Lửa ở xe máy',
        'Đèn xe chiếu lên tường',
        'Khói mờ ở lối xuống',
        'Hơi nước từ ống xả',
      ]);
      expect(rows.map((e) => e.status), [
        EventStatus.fire,
        EventStatus.dismissed,
        EventStatus.unverified,
        EventStatus.falseAlarm,
      ]);
      expect(rows.map((e) => (e.detectedAt.hour, e.detectedAt.minute)), [
        (21, 47),
        (21, 40),
        (19, 2),
        (8, 15),
      ]);
      expect(rows.first.called114, isTrue);
      expect(rows.every((e) => e.locationName == 'Hầm xe'), isTrue);
    });

    test('filters (G1 · Lọc)', () async {
      final h = FakeHistoryRepository(world());
      Future<List<String>> titles(HistoryFilter f) async =>
          (await h.list(filter: f)).map((e) => e.summary).toList();
      expect(await titles(HistoryFilter.fire), ['Lửa ở xe máy']);
      expect(await titles(HistoryFilter.dismissed), ['Đèn xe chiếu lên tường']);
      expect(await titles(HistoryFilter.falseAlarm), ['Hơi nước từ ống xả']);
    });

    test('empty (G3) and errors (G8)', () async {
      expect(
        await FakeHistoryRepository(world({FakeCase.historyEmpty})).list(),
        isEmpty,
      );
      await expectLater(
        FakeHistoryRepository(world({FakeCase.historyNetworkError})).list(),
        throwsA(isA<NetworkException>()),
      );
      await expectLater(
        FakeHistoryRepository(
          world({FakeCase.historyServerError}),
        ).detail('evt-fire'),
        throwsA(isA<ServerException>()),
      );
    });

    test('G4 timeline proves < 10 s', () async {
      final e = await FakeHistoryRepository(world()).detail('evt-fire');
      expect(e.detectedAt, DateTime(2025, 10, 23, 21, 47, 31));
      expect(e.timeline, const [
        TimelineStep(TimelineStepKind.detected, Duration.zero),
        TimelineStep(TimelineStepKind.imageSent, Duration(milliseconds: 400)),
        TimelineStep(
          TimelineStepKind.confirmedFire,
          Duration(milliseconds: 5100),
        ),
        TimelineStep(TimelineStepKind.notified, Duration(milliseconds: 6800)),
      ]);
      expect(e.notifyLatency! < alertLatencyGoal, isTrue);
    });

    test('G5 dismissed detail', () async {
      final e = await FakeHistoryRepository(world()).detail('evt-dismissed');
      expect(e.detectedAt, DateTime(2025, 10, 23, 21, 40, 12));
      expect(e.detail, 'AI kiểm tra lại 2 lần, không thấy khói hay lửa.');
      expect(e.timeline.map((s) => (s.kind, s.offset)), [
        (TimelineStepKind.detected, Duration.zero),
        (TimelineStepKind.confirmedNotFire, const Duration(milliseconds: 4600)),
        (TimelineStepKind.notNotified, null),
      ]);
      expect(e.notifyLatency, isNull);
    });

    test('events older than 30 days are hidden', () async {
      final w = world()
        ..addEvent(
          FakeData.dismissedEvent(
            id: 'old',
            detectedAt: FakeData.demoNow.subtract(const Duration(days: 31)),
          ),
        );
      final rows = await FakeHistoryRepository(w).list();
      expect(rows.map((e) => e.id), isNot(contains('old')));
    });
  });

  group('alert actions (F2/F5/F9/K4/K5/G5)', () {
    late FakeWorld w;
    late FakeAlertRepository alerts;
    const id = 'live';

    setUp(() {
      w = world()..addEvent(FakeData.fireAlert(id: id));
      alerts = FakeAlertRepository(w);
    });

    test('F2 sample matches Figma', () async {
      final a = await alerts.getAlert(id);
      expect(a.detail, 'Lửa và khói ở xe máy bên trái');
      expect(a.confidence, 0.93);
      expect(a.checkCount, 2);
      expect(a.address, 'Hầm B1, chung cư Sky Garden, 12 Nguyễn Văn Linh, Q.7');
      expect(a.callScript, 'Cháy xe máy ở khu sạc');
      expect(a.resolved, isFalse);
    });

    test('resolve (undo is app-side)', () async {
      expect((await alerts.resolve(id)).resolved, isTrue);
      expect((await alerts.getAlert(id)).resolved, isTrue);
    });

    test('false alarm', () async {
      expect((await alerts.markFalseAlarm(id)).status, EventStatus.falseAlarm);
      expect(w.event(id).status, EventStatus.falseAlarm);
    });

    test('"Chỉ báo cháy" cannot close the incident', () async {
      final only = world({FakeCase.alertsOnlyRole})
        ..addEvent(FakeData.fireAlert(id: id));
      final repo = FakeAlertRepository(only);
      expect(
        only.groups.firstWhere((g) => g.id == FakeData.skyGarden.id).myRole,
        GroupRole.alertsOnly,
      );
      final me = only.me(FakeData.skyGarden.id);
      expect(me.role, GroupRole.alertsOnly);
      expect(me.cameraIds, ['cam-charger', 'cam-ramp', 'cam-down']);
      await expectLater(
        repo.resolve(id),
        throwsA(isA<PermissionDeniedException>()),
      );
      await expectLater(
        repo.markFalseAlarm(id),
        throwsA(isA<PermissionDeniedException>()),
      );
      expect(only.event(id).resolved, isFalse);
      expect(only.event(id).status, EventStatus.fire);
      expect((await repo.recordCall114(id)).called114, isTrue);
    });

    test('calling 114 marks the alert, not its timeline', () async {
      final before = (await alerts.getAlert(id)).timeline;
      final a = await alerts.recordCall114(id);
      expect(a.called114, isTrue);
      expect(a.timeline, before);
    });

    test('report a dismissed event as real fire (G5)', () async {
      final a = await alerts.reportRealFire('evt-dismissed');
      expect(a.status, EventStatus.fire);
    });
  });
}
