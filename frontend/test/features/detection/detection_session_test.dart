import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/features/detection/detection_controller.dart';

void main() {
  test('opening B while A is still there keeps the sessions apart', () async {
    final c = ProviderContainer.test(
      overrides: fakeOverrides([
        fakeScenarioProvider.overrideWithValue(const FakeScenario.test()),
      ]),
    );
    final a = FakeData.cameras.firstWhere((x) => x.id == 'cam-charger');
    final b = FakeData.cameras.firstWhere((x) => x.id == 'cam-ramp');

    final sawA = <DetectionState>[];
    final subA = c.listen(
      detectionControllerProvider(a.id),
      (_, next) => sawA.add(next),
    );
    c.read(detectionControllerProvider(a.id).notifier).start(a);
    await pumpEventQueue();

    final sawB = <DetectionState>[];
    c.listen(detectionControllerProvider(b.id), (_, next) => sawB.add(next));
    c.read(detectionControllerProvider(b.id).notifier).start(b);
    final aBefore = sawA.length;
    subA.close();
    await pumpEventQueue();

    expect(sawA.length, aBefore, reason: "B's states never reach A");
    expect(sawB, isNotEmpty, reason: 'A leaving does not stop B');
    expect(
      c.read(detectionControllerProvider(b.id)),
      isNot(isA<DetectionIdle>()),
    );
  });
}
