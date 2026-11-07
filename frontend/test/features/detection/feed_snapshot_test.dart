import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/features/detection/feed_snapshot.dart';
import 'package:video_player/video_player.dart';

const _playing = VideoPlayerValue(
  duration: Duration.zero,
  isInitialized: true,
  size: Size(1280, 720),
  position: Duration(milliseconds: 800),
);

ByteData _frame(int pixels, {int lit = 0, int value = 255}) {
  final data = ByteData(pixels * 4);
  for (var i = 0; i < lit; i++) {
    final o = i * 4;
    data
      ..setUint8(o, value)
      ..setUint8(o + 1, value)
      ..setUint8(o + 2, value)
      ..setUint8(o + 3, 255);
  }
  return data;
}

void main() {
  group('ready: the player shows a real frame', () {
    test('playing past the start', () {
      expect(feedShowsFrame(_playing), isTrue);
    });

    test('still connecting, at the start, or broken: not ready', () {
      expect(feedShowsFrame(VideoPlayerValue.uninitialized()), isFalse);
      expect(
        feedShowsFrame(_playing.copyWith(position: Duration.zero)),
        isFalse,
      );
      expect(feedShowsFrame(_playing.copyWith(size: Size.zero)), isFalse);
      expect(
        feedShowsFrame(_playing.copyWith(errorDescription: 'HLS failed')),
        isFalse,
      );
    });
  });

  group('near-black', () {
    test('all black, or transparent, is near-black', () {
      expect(isNearBlack(_frame(320 * 180)), isTrue);
    });

    test('a few bright pixels on black is still near-black', () {
      expect(isNearBlack(_frame(1000, lit: 10), step: 1), isTrue);
    });

    test('a dim gray frame is not', () {
      expect(isNearBlack(_frame(1000, lit: 1000, value: 60), step: 1), isFalse);
    });

    test('a dark scene with 5% lit is not', () {
      expect(isNearBlack(_frame(1000, lit: 50), step: 1), isFalse);
    });
  });

  group('snapshotFeed', () {
    Future<FeedSnapshotTarget> pump(WidgetTester tester, Color color) async {
      final target = FeedSnapshotTarget();
      await tester.pumpWidget(
        Center(
          child: SizedBox(
            width: 640,
            height: 360,
            child: FeedSnapshotBoundary(
              target: target,
              child: ColoredBox(color: color),
            ),
          ),
        ),
      );
      return target;
    }

    testWidgets('a frame becomes a ≈320×180 PNG', (tester) async {
      final target = await pump(tester, Colors.orange);
      await tester.runAsync(() async {
        final png = await snapshotFeed(target.boundary!);
        expect(png, isNotNull);
        final codec = await ui.instantiateImageCodec(png!);
        final image = (await codec.getNextFrame()).image;
        expect((image.width, image.height), (320, 180));
        image.dispose();
      });
    });

    testWidgets('a black frame is skipped', (tester) async {
      final target = await pump(tester, Colors.black);
      await tester.runAsync(() async {
        expect(await snapshotFeed(target.boundary!), isNull);
      });
    });

    testWidgets('the target follows the feed on screen', (tester) async {
      final target = await pump(tester, Colors.orange);
      expect(target.boundary, isNotNull);
      await tester.pumpWidget(const SizedBox());
      expect(target.boundary, isNull);
    });
  });
}
