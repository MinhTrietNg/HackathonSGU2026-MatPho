import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/widgets/mp_feed_tag.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_illustration.dart';
import 'package:mat_pho/core/widgets/mp_still.dart';
import 'package:mat_pho/data/models/models.dart';
import 'package:mat_pho/features/detection/feed_player.dart';
import 'package:mat_pho/features/detection/watch_widgets.dart';
import 'package:video_player/video_player.dart';

import '../../fakes/fake_overrides.dart';

class _StillBundle extends CachingAssetBundle {
  static final _png = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA'
    '60e6kgAAAABJRU5ErkJggg==',
  );

  @override
  Future<ByteData> load(String key) async =>
      key.endsWith('.jpg') ? ByteData.sublistView(_png) : rootBundle.load(key);
}

class _FakePlayer extends VideoPlayerController {
  _FakePlayer() : super.asset('assets/demo_clips/x.mp4');

  final seeks = <Duration>[];
  int plays = 0;

  @override
  Future<void> seekTo(Duration position) async {
    seeks.add(position);
    value = value.copyWith(position: position, isCompleted: false);
  }

  @override
  Future<void> play() async {
    plays++;
    value = value.copyWith(isPlaying: true);
  }

  void at(Duration position, {bool completed = false}) =>
      value = value.copyWith(
        isInitialized: true,
        duration: const Duration(seconds: 98),
        size: const Size(16, 9),
        position: position,
        isPlaying: !completed,
        isCompleted: completed,
      );
}

const FeedSource _segment = (
  uri: 'assets/demo_clips/x.mp4',
  start: Duration(seconds: 45),
  end: Duration(milliseconds: 51800),
);

void main() {
  group('evidence segment', () {
    test('plays start → end, then jumps back to the start', () async {
      final player = _FakePlayer();
      loopFeedSegment(
        player,
        start: _segment.start,
        end: _segment.end!,
        disposed: () => false,
      );
      player.at(const Duration(seconds: 45));
      player.at(const Duration(seconds: 51));
      expect(player.seeks, isEmpty);

      player.at(const Duration(milliseconds: 51900));
      await pumpEventQueue();
      expect(player.seeks, [_segment.start]);
      expect(player.plays, 1);
      expect(player.value.position, _segment.start);
    });

    test('a clip that ends before the segment does also loops', () async {
      final player = _FakePlayer();
      loopFeedSegment(
        player,
        start: const Duration(seconds: 4),
        end: const Duration(seconds: 30),
        disposed: () => false,
      );
      player.at(const Duration(seconds: 16), completed: true);
      await pumpEventQueue();
      expect(player.seeks, [const Duration(seconds: 4)]);
      expect(player.value.isPlaying, isTrue);
    });

    test('stops with the player', () async {
      final player = _FakePlayer();
      var disposed = false;
      loopFeedSegment(
        player,
        start: _segment.start,
        end: _segment.end!,
        disposed: () => disposed,
      );
      disposed = true;
      player.at(const Duration(seconds: 60));
      await pumpEventQueue();
      expect(player.seeks, isEmpty);
    });
  });

  group('live feed retry', () {
    testWidgets('an error rebuilds the player once, after the delay', (
      tester,
    ) async {
      final player = _FakePlayer();
      addTearDown(player.dispose);
      var retries = 0;
      retryFeedOnError(player, retry: () => retries++, disposed: () => false);

      player.value = player.value.copyWith(errorDescription: 'no stream');
      player.value = player.value.copyWith(errorDescription: 'still none');
      await tester.pump(feedRetryDelay - const Duration(milliseconds: 1));
      expect(retries, 0);
      await tester.pump(const Duration(milliseconds: 1));
      expect(retries, 1);
    });

    testWidgets('a failed initialize schedules the same retry', (tester) async {
      final player = _FakePlayer();
      addTearDown(player.dispose);
      var retries = 0;
      final schedule = retryFeedOnError(
        player,
        retry: () => retries++,
        disposed: () => false,
      );
      schedule();
      schedule();
      await tester.pump(feedRetryDelay);
      expect(retries, 1);
    });

    testWidgets('no retry once the player is gone', (tester) async {
      final player = _FakePlayer();
      addTearDown(player.dispose);
      var disposed = false;
      var retries = 0;
      retryFeedOnError(
        player,
        retry: () => retries++,
        disposed: () => disposed,
      );
      player.value = player.value.copyWith(errorDescription: 'no stream');
      disposed = true;
      await tester.pump(feedRetryDelay);
      expect(retries, 0);
    });
  });

  group('FeedVideo / WatchFeedPicture', () {
    late _FakePlayer player;

    Future<void> pump(WidgetTester tester, Widget child) {
      player = _FakePlayer();
      addTearDown(player.dispose);
      return tester.pumpWidget(
        ProviderScope(
          overrides: fakeOverrides([
            feedPlayerProvider.overrideWith((ref, _) => player),
          ]),
          child: MaterialApp(
            theme: AppTheme.dark(),
            home: DefaultAssetBundle(
              bundle: _StillBundle(),
              child: SizedBox(width: 318, height: 220, child: child),
            ),
          ),
        ),
      );
    }

    const art = (art: MpIllustrations.feed, overlay: null, overlayOpacity: 1.0);

    testWidgets('with a clip: the still until the first frame, no artwork', (
      tester,
    ) async {
      await pump(
        tester,
        const WatchFeedPicture(
          art: art,
          video: _segment,
          still: AssetImage('assets/demo_clips/x_thumb.jpg'),
        ),
      );
      expect(find.byType(MpStill), findsOneWidget);
      expect(find.byType(MpIllustration), findsNothing);

      player.value = player.value.copyWith(
        isInitialized: true,
        size: const Size(16, 9),
      );
      await tester.pump();
      expect(find.byType(MpStill), findsOneWidget);

      player.at(_segment.start);
      await tester.pump();
      expect(find.byType(VideoPlayer), findsOneWidget);
      expect(find.byType(MpStill), findsNothing);
    });

    testWidgets('with a clip and no still: a plain fill, no artwork', (
      tester,
    ) async {
      await pump(tester, const WatchFeedPicture(art: art, video: _segment));
      expect(find.byType(MpStill), findsNothing);
      expect(find.byType(MpIllustration), findsNothing);
      expect(find.byType(VideoPlayer), findsNothing);
    });

    testWidgets('no clip at all (tests, public builds): the artwork', (
      tester,
    ) async {
      await pump(tester, const WatchFeedPicture(art: art));
      expect(find.byType(MpIllustration), findsOneWidget);
    });
  });

  test('the feed clock reads like a CCTV overlay', () {
    expect(
      formatFeedTime(DateTime(2026, 11, 3, 13, 30, 36)),
      '03/11/2026 13:30:36',
    );
  });
}
