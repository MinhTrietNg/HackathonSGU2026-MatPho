import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/theme/theme.dart';
import '../../fakes/fake_overrides.dart';
import '../../fakes/fake_data.dart';
import '../../fakes/fake_scenario.dart';
import 'package:mat_pho/data/models/fire_event.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/repositories/history_repository.dart';
import 'package:mat_pho/features/history/evidence_slideshow.dart';
import 'package:mat_pho/features/history/history_detail_screen.dart';

final class _ServerHistory implements HistoryRepository {
  _ServerHistory(this.event);

  final FireEvent event;

  @override
  Future<List<FireEvent>> list({
    HistoryFilter filter = HistoryFilter.all,
  }) async => [event];

  @override
  Future<FireEvent> detail(String eventId) async => event;
}

void main() {
  final fire = FakeData.fireAlert(id: 'alt_1001');
  final event = FireEvent(
    id: fire.id,
    cameraId: fire.cameraId,
    locationName: fire.locationName,
    status: fire.status,
    detectedAt: fire.detectedAt,
    summary: fire.summary,
    sign: DetectedSign.fire,
    confidence: 0.93,
    timeline: fire.timeline,
    stillUrl: 'https://storage.test/alt_1001.jpg',
    snapshots: const [
      EvidenceSnapshot(
        url: 'https://storage.test/t0.jpg',
        box: (left: 0.2, top: 0.3, right: 0.4, bottom: 0.6),
      ),
      EvidenceSnapshot(
        url: 'https://storage.test/t1.jpg',
        box: (left: 0.5, top: 0.1, right: 0.9, bottom: 0.5),
      ),
    ],
  );

  Future<void> pump(WidgetTester tester, FireEvent event) async {
    tester.view
      ..physicalSize = const Size(360, 780)
      ..devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ProviderScope(
        overrides: fakeOverrides([
          fakeScenarioProvider.overrideWithValue(FakeScenario.test()),
          historyRepositoryProvider.overrideWithValue(_ServerHistory(event)),
        ]),
        child: MaterialApp(
          theme: AppTheme.dark(),
          home: HistoryDetailScreen(eventId: event.id),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
  }

  Rect expected(WidgetTester tester, EvidenceBox box) {
    final card = tester.getRect(find.byType(EvidenceSlideshow));
    return Rect.fromLTRB(
      card.left + box.left * card.width,
      card.top + box.top * card.height,
      card.left + box.right * card.width,
      card.top + box.bottom * card.height,
    );
  }

  testWidgets('G4 plays the snapshots with the AI box in place', (
    tester,
  ) async {
    await pump(tester, event);

    final card = tester.getRect(find.byType(EvidenceSlideshow));
    expect(card.width, 320);
    expect(card.height, closeTo(180, 0.01));

    final box = find.byKey(EvidenceBoxOverlay.rectKey);
    expect(
      tester.getRect(box),
      rectMoreOrLessEquals(expected(tester, event.snapshots[0].box!)),
    );
    expect(find.text('CHÁY · 0,93'), findsOneWidget);

    await tester.pump(EvidenceSlideshow.frameDuration);
    expect(
      tester.getRect(box),
      rectMoreOrLessEquals(expected(tester, event.snapshots[1].box!)),
    );
    await tester.pump(EvidenceSlideshow.frameDuration);
    expect(
      tester.getRect(box),
      rectMoreOrLessEquals(expected(tester, event.snapshots[0].box!)),
    );

    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('no snapshots: no slideshow, the still then the artwork', (
    tester,
  ) async {
    await pump(
      tester,
      FireEvent(
        id: event.id,
        cameraId: event.cameraId,
        locationName: event.locationName,
        status: event.status,
        detectedAt: event.detectedAt,
        summary: event.summary,
        sign: DetectedSign.fire,
      ),
    );
    expect(find.byType(EvidenceSlideshow), findsNothing);
    expect(find.byKey(EvidenceBoxOverlay.rectKey), findsNothing);
  });
}
