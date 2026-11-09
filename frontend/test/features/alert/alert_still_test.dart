import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/models/fire_event.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/repositories/alert_repository.dart';
import 'package:mat_pho/features/alert/alert_controller.dart';

import '../../fakes/fake_data.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_scenario.dart';

const _still = 'https://storage.example/evidence.jpg';

/// The server has no evidence picture until [stillAfter] fetches.
final class _LateStill implements AlertRepository {
  _LateStill(this.base, {required this.stillAfter});

  final FireEvent base;
  final int stillAfter;
  int fetches = 0;

  @override
  Future<FireEvent> getAlert(String eventId) async {
    fetches++;
    return fetches >= stillAfter ? base.copyWith(stillUrl: _still) : base;
  }

  @override
  Stream<FireEvent> incomingAlerts() => const Stream.empty();

  @override
  Stream<AlertUpdate> alertUpdates() => const Stream.empty();

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError();
}

ProviderContainer _container(AlertRepository alerts, String id) {
  final container = ProviderContainer(
    overrides: fakeOverrides([
      fakeScenarioProvider.overrideWithValue(const FakeScenario.test()),
      alertRepositoryProvider.overrideWithValue(alerts),
    ]),
  );
  container.listen(alertProvider(id), (_, _) {});
  return container;
}

void main() {
  final event = FakeData.unverifiedEvent(
    id: 'evt-late-still',
    detectedAt: DateTime.now(),
  );

  testWidgets('a picture that reaches the server late shows up on its own', (
    tester,
  ) async {
    final alerts = _LateStill(event, stillAfter: 3);
    final container = _container(alerts, event.id);
    addTearDown(container.dispose);

    await tester.pump();
    expect(container.read(alertProvider(event.id)).value?.event.stillUrl, isNull);

    await tester.pump(stillRetryEvery);
    expect(container.read(alertProvider(event.id)).value?.event.stillUrl, isNull);

    await tester.pump(stillRetryEvery);
    final shown = container.read(alertProvider(event.id)).value!.event;
    expect(shown.stillUrl, _still);
    expect(shown.status, event.status);

    final asked = alerts.fetches;
    await tester.pump(stillRetryEvery * 3);
    expect(alerts.fetches, asked, reason: 'stops asking once the picture is in');
  });

  testWidgets('gives up after the deadline', (tester) async {
    final alerts = _LateStill(event, stillAfter: 1 << 30);
    final container = _container(alerts, event.id);
    addTearDown(container.dispose);

    await tester.pump();
    await tester.pump(stillRetryFor + stillRetryEvery * 2);
    final asked = alerts.fetches;
    await tester.pump(stillRetryEvery * 3);
    expect(alerts.fetches, asked);
  });

  testWidgets('an old alert without a picture is not asked about', (
    tester,
  ) async {
    final old = FakeData.unverifiedEvent(
      id: 'evt-old',
      detectedAt: DateTime.now().subtract(stillMaxAge * 2),
    );
    final alerts = _LateStill(old, stillAfter: 1);
    final container = _container(alerts, old.id);
    addTearDown(container.dispose);

    await tester.pump();
    final asked = alerts.fetches;
    await tester.pump(stillRetryEvery * 3);
    expect(alerts.fetches, asked);
  });

  testWidgets('an alert that already has its picture never asks again', (
    tester,
  ) async {
    final alerts = _LateStill(event.copyWith(stillUrl: _still), stillAfter: 1);
    final container = _container(alerts, event.id);
    addTearDown(container.dispose);

    await tester.pump();
    final asked = alerts.fetches;
    await tester.pump(stillRetryEvery * 3);
    expect(alerts.fetches, asked);
  });
}
