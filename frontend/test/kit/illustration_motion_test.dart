import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_animated_illustrations.dart';
import 'package:mat_pho/core/widgets/mp_illustration.dart';
import 'package:mat_pho/core/widgets/mp_illustration_motion.dart';
import 'package:mat_pho/core/widgets/mp_illustration_motions.dart';

import '../helpers/golden.dart';

Iterable<MpArtLayer> _layers(List<MpArtNode> nodes) sync* {
  for (final node in nodes) {
    if (node is MpArtLayer) {
      yield node;
      yield* _layers(node.children);
    }
  }
}

Iterable<String> _parts(List<MpArtNode> nodes) sync* {
  for (final node in nodes) {
    switch (node) {
      case MpArtPart(:final asset):
        yield asset;
      case MpArtLayer(:final children):
        yield* _parts(children);
    }
  }
}

MpArtLayer _layer(MpIllustrationMotion motion, String name) =>
    _layers(motion.parts).firstWhere((l) => l.name == name);

Future<void> _pumpPlaying(
  WidgetTester tester,
  Widget child, {
  ThemeData? theme,
  bool reduceMotion = false,
}) async {
  mpIllustrationMotionEnabled = true;
  addTearDown(() => mpIllustrationMotionEnabled = false);
  await tester.pumpWidget(
    MaterialApp(
      theme: theme ?? AppTheme.dark(),
      home: MediaQuery(
        data: MediaQueryData(disableAnimations: reduceMotion),
        child: Center(child: RepaintBoundary(child: child)),
      ),
    ),
  );
  await tester.runAsync(() => Future<void>.delayed(Duration.zero));
}

Future<void> _advanceTo(WidgetTester tester, Duration elapsed) async {
  await tester.pump(elapsed);
  await tester.runAsync(
    () => Future<void>.delayed(const Duration(milliseconds: 20)),
  );
  await tester.pump();
}

void main() {
  group('MpTrack', () {
    test('interpolates linearly between keyframes', () {
      const track = MpTrack([
        MpKeyframe(0, 0),
        MpKeyframe(0.5, 10),
        MpKeyframe(1, 10),
      ]);
      expect(track.valueAt(0), 0);
      expect(track.valueAt(0.25), 5);
      expect(track.valueAt(0.5), 10);
      expect(track.valueAt(0.75), 10);
      expect(track.valueAt(1), 10);
    });

    test('the ease of a keyframe shapes the segment after it', () {
      const track = MpTrack([
        MpKeyframe(0, 0, MpEase.easeOut),
        MpKeyframe(0.5, 1, MpEase.easeInOut),
        MpKeyframe(1, 0),
      ]);
      expect(
        track.valueAt(0.125),
        closeTo(Curves.easeOut.transform(0.25), 1e-9),
      );
      expect(
        track.valueAt(0.625),
        closeTo(1 - Curves.easeInOut.transform(0.25), 1e-9),
      );
    });

    test('the kit pop-in overshoots, step-end holds, constants stay', () {
      const pop = MpTrack([
        MpKeyframe(0, 0.01, MpEase.popIn),
        MpKeyframe(1, 1),
      ]);
      final peak = [
        for (var i = 1; i < 100; i++) pop.valueAt(i / 100),
      ].reduce((a, b) => a > b ? a : b);
      expect(peak, greaterThan(1.05));
      expect(pop.valueAt(1), 1);

      const step = MpTrack([
        MpKeyframe(0, 1, MpEase.stepEnd),
        MpKeyframe(0.36, 0),
        MpKeyframe(1, 0),
      ]);
      expect(step.valueAt(0.2), 1);
      expect(step.valueAt(0.359), 1);
      expect(step.valueAt(0.36), 0);

      expect(const MpTrack.constant(0.45).valueAt(0.7), 0.45);
    });
  });

  test('the opening plays once, then the loop repeats', () {
    const motion = MpIllustrationMotion(
      asset: MpIllustrations.logout,
      duration: Duration(milliseconds: 2800),
      parts: [],
    );
    expect(motion.phaseAt(Duration.zero), (MpMotionPhase.opening, 0.0));
    expect(motion.phaseAt(const Duration(milliseconds: 1400)), (
      MpMotionPhase.opening,
      0.5,
    ));
    expect(motion.phaseAt(const Duration(milliseconds: 2800)), (
      MpMotionPhase.loop,
      0.0,
    ));
    expect(motion.phaseAt(const Duration(milliseconds: 2800 * 7 + 700)), (
      MpMotionPhase.loop,
      0.25,
    ));
  });

  test('a layer pose transforms around the center of its Figma box', () {
    final door = _layer(MpIllustrationMotions.logout, 'a2');
    final pose = MpLayerPose.of(door, MpMotionPhase.loop, 0.5);
    expect((pose.scaleX, pose.scaleY), (0.5, 1.1));
    final m = pose.transform(door.box!.center);
    final hinge = MatrixUtils.transformPoint(m, Offset(160, door.box!.top));
    final latch = MatrixUtils.transformPoint(m, const Offset(104, 94));
    expect(hinge.dx, closeTo(160, 1e-9));
    expect(latch.dx, closeTo(132, 1e-9));

    final knob = MpLayerPose.of(
      _layer(MpIllustrationMotions.logout, 'a3'),
      MpMotionPhase.loop,
      0.5,
    );
    expect((knob.translateX, knob.scaleX), (23, 1.25));

    final frame = _layer(MpIllustrationMotions.logout, 'a0');
    expect(MpLayerPose.of(frame, MpMotionPhase.opening, 0).opacity, 0);
    expect(MpLayerPose.of(frame, MpMotionPhase.opening, 0.5).opacity, 1);
    expect(MpLayerPose.of(frame, MpMotionPhase.loop, 0.3).opacity, 1);
  });

  test('a layer without an opacity track keeps its own opacity', () {
    final lamp = _layer(MpIllustrationMotions.feed, 'a0');
    expect(lamp.opacity, 0.7);
    expect(MpLayerPose.of(lamp, MpMotionPhase.loop, 0).opacity, 0.7);
    expect(MpLayerPose.of(lamp, MpMotionPhase.loop, 0.1).opacity, 0.25);
  });

  group('data', () {
    for (final MapEntry(key: asset, value: motion)
        in MpIllustrationMotions.byAsset.entries) {
      test(asset, () {
        expect(motion.asset, asset);
        for (final part in _parts(motion.parts)) {
          expect(File(part).existsSync(), isTrue, reason: part);
          if (!motion.themed) continue;
          final svg = File(part).readAsStringSync();
          for (final m in RegExp(
            r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"',
          ).allMatches(svg)) {
            final color = Color(
              0xFF000000 | int.parse(m[1]!.substring(1), radix: 16),
            );
            expect(
              SvgSourceColors.illustration(
                MpColors.dark,
                color,
                groundShadow: false,
              ),
              isNotNull,
              reason: '$part: ${m[1]}',
            );
          }
          if (svg.contains('id="Vector_2"')) {
            expect(svg, contains('opacity="0.7"'), reason: part);
          }
        }
        for (final layer in _layers(motion.parts)) {
          for (final m in [layer.opening, layer.loop]) {
            for (final track in [
              m.opacity,
              m.scaleX,
              m.scaleY,
              m.translateX,
              m.translateY,
              m.rotate,
              m.trim,
            ].nonNulls.where((t) => t.keys.isNotEmpty)) {
              expect(track.keys.first.at, 0);
              expect(track.keys.last.at, 1);
              for (var i = 1; i < track.keys.length; i++) {
                expect(
                  track.keys[i].at,
                  greaterThanOrEqualTo(track.keys[i - 1].at),
                );
              }
            }
          }
          final transforms = [layer.opening, layer.loop].any(
            (m) =>
                m.scaleX != null ||
                m.translateX != null ||
                m.translateY != null ||
                m.rotate != null,
          );
          if (transforms || layer.reveal != null) {
            expect(layer.box, isNotNull, reason: layer.name);
          }
        }
      });
    }
  });

  group('MpIllustration', () {
    testWidgets('plays the motion: opening, then the loop', (tester) async {
      await _pumpPlaying(tester, const MpIllustration(MpIllustrations.logout));
      expect(find.byType(MpAnimatedIllustration), findsOneWidget);
      expect(
        find.descendant(
          of: find.byType(MpAnimatedIllustration),
          matching: find.byType(SvgPicture),
        ),
        findsNWidgets(6),
      );
      Opacity frameOpacity() =>
          tester.widgetList<Opacity>(find.byType(Opacity)).first;
      expect(frameOpacity().opacity, 0);
      await _advanceTo(tester, const Duration(milliseconds: 800));
      expect(frameOpacity().opacity, 1);
      expect(tester.binding.transientCallbackCount, 1);
      await tester.pumpWidget(const SizedBox());
      expect(tester.binding.transientCallbackCount, 0);
    });

    testWidgets('reduce motion shows the still artwork, no ticker', (
      tester,
    ) async {
      await _pumpPlaying(
        tester,
        const MpIllustration(MpIllustrations.logout),
        reduceMotion: true,
      );
      expect(find.byType(SvgPicture), findsOneWidget);
      expect(find.byType(Opacity), findsNothing);
      expect(tester.binding.transientCallbackCount, 0);
    });

    testWidgets('tests and goldens see the still artwork', (tester) async {
      expect(mpIllustrationMotionEnabled, isFalse);
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.dark(),
          home: const Column(
            children: [
              MpIllustration(MpIllustrations.share),
              MpOtpIllustration(size: Size(220, 141)),
              MpPermNotifyIllustration(),
            ],
          ),
        ),
      );
      expect(find.byType(SvgPicture), findsNWidgets(3));
      expect(tester.binding.transientCallbackCount, 0);
    });

    testWidgets('feeds play only where Figma uses the animated artwork', (
      tester,
    ) async {
      await _pumpPlaying(
        tester,
        const Column(
          children: [
            MpIllustration(MpIllustrations.feed, size: Size(140, 90)),
            MpIllustration(
              MpIllustrations.feedFire,
              size: Size(140, 90),
              animated: true,
            ),
          ],
        ),
      );
      expect(find.byType(MpAnimatedIllustration), findsOneWidget);
    });

    testWidgets('without backdrop, ill/blob is transparent (still, motion)', (
      tester,
    ) async {
      const blob = Color(0xFF142030);
      const ink = Color(0xFF080D13);
      final colors = MpColors.dark;
      final mapper = MpIllustration.colorMapper(
        MpIllustrations.camOffline,
        colors,
        backdrop: false,
      );
      expect(mapper.substitute(null, 'path', 'fill', blob).a, 0);
      expect(mapper.substitute(null, 'path', 'fill', ink), colors.illInk);
      expect(
        MpIllustration.colorMapper(
          MpIllustrations.camOffline,
          colors,
        ).substitute(null, 'path', 'fill', blob),
        colors.illBlob,
      );

      ColorMapper? mapperOf(SvgPicture svg) =>
          (svg.bytesLoader as SvgAssetLoader).colorMapper;
      Iterable<SvgPicture> svgs() =>
          tester.widgetList<SvgPicture>(find.byType(SvgPicture));

      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.dark(),
          home: const MpIllustration(
            MpIllustrations.camOffline,
            backdrop: false,
          ),
        ),
      );
      expect(
        mapperOf(svgs().single)!.substitute(null, 'path', 'fill', blob).a,
        0,
      );

      await _pumpPlaying(
        tester,
        const MpIllustration(MpIllustrations.camOffline, backdrop: false),
      );
      expect(find.byType(MpAnimatedIllustration), findsOneWidget);
      expect(svgs(), isNotEmpty);
      for (final svg in svgs()) {
        expect(mapperOf(svg)!.substitute(null, 'path', 'fill', blob).a, 0);
      }
      await tester.pumpWidget(const SizedBox());
    });
  });

  group('goldens', () {
    Future<void> golden(
      WidgetTester tester,
      Widget child,
      Duration at,
      String file, {
      ThemeData? theme,
    }) async {
      tester.view
        ..physicalSize = MpIllustration.figmaSize * kGoldenPixelRatio
        ..devicePixelRatio = kGoldenPixelRatio;
      addTearDown(tester.view.reset);
      await _pumpPlaying(tester, child, theme: theme);
      await _advanceTo(tester, at);
      await expectLater(
        find.byType(RepaintBoundary).first,
        matchesGoldenFile('../goldens/kit/motion/$file.png'),
      );
      await tester.pumpWidget(const SizedBox());
    }

    testWidgets('ill/logout · loop 50 %', (tester) async {
      await golden(
        tester,
        const MpIllustration(MpIllustrations.logout),
        const Duration(milliseconds: 2800 + 1400),
        'logout-loop-50',
      );
    });

    testWidgets('ill/logout · loop 50 % · Light', (tester) async {
      await golden(
        tester,
        const MpIllustration(MpIllustrations.logout),
        const Duration(milliseconds: 2800 + 1400),
        'logout-loop-50-light',
        theme: AppTheme.light(),
      );
    });

    testWidgets('ill/feed-fire · loop 25 %', (tester) async {
      await golden(
        tester,
        const MpIllustration(MpIllustrations.feedFire, animated: true),
        const Duration(milliseconds: 6800 + 1700),
        'feed-fire-loop-25',
      );
    });

    testWidgets('ill/dismissed · opening 35 % (check mark trimming in)', (
      tester,
    ) async {
      await golden(
        tester,
        const MpIllustration(MpIllustrations.dismissed),
        const Duration(milliseconds: 1260),
        'dismissed-opening-35',
      );
    });
  });
}
