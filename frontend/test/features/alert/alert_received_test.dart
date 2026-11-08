import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/models/fire_event.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/repositories/alert_repository.dart';
import 'package:mat_pho/features/alert/alert_controller.dart';

import '../../fakes/fake_data.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_scenario.dart';

/// getAlert answers only when the test says so.
final class _SlowAlerts implements AlertRepository {
  final fetch = Completer<FireEvent>();

  @override
  Future<FireEvent> getAlert(String eventId) => fetch.future;

  @override
  Stream<FireEvent> incomingAlerts() => const Stream.empty();

  @override
  Stream<AlertUpdate> alertUpdates() => const Stream.empty();

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError();
}

final _received = FakeData.unverifiedEvent(id: 'evt-ws');

(ProviderContainer, _SlowAlerts) _container() {
  final alerts = _SlowAlerts();
  final container = ProviderContainer(
    overrides: fakeOverrides([
      fakeScenarioProvider.overrideWithValue(const FakeScenario.test()),
      alertRepositoryProvider.overrideWithValue(alerts),
    ]),
  );
  addTearDown(container.dispose);
  container.read(receivedAlertsProvider.notifier).remember(_received);
  container.listen(alertProvider(_received.id), (_, _) {});
  return (container, alerts);
}

Future<void> _settle() => Future<void>.delayed(Duration.zero);

void main() {
  test('a WebSocket alert shows at once, before the fetch answers', () async {
    final (container, _) = _container();

    final state = await container.read(alertProvider(_received.id).future);

    expect(state.event, same(_received));
  });

  test('a failed fetch keeps the WebSocket alert on screen', () async {
    final (container, alerts) = _container();
    await container.read(alertProvider(_received.id).future);

    alerts.fetch.completeError(StateError('503'));
    await _settle();

    final alert = container.read(alertProvider(_received.id));
    expect(alert.hasError, isFalse);
    expect(alert.value?.event, same(_received));
  });

  test("the server's copy replaces the WebSocket one", () async {
    final (container, alerts) = _container();
    await container.read(alertProvider(_received.id).future);

    final fetched = FakeData.unverifiedEvent(id: _received.id);
    alerts.fetch.complete(fetched);
    await _settle();

    expect(
      container.read(alertProvider(_received.id)).value?.event,
      same(fetched),
    );
  });
}
