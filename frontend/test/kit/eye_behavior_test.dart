import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_eye.dart';
import 'package:mat_pho/core/widgets/mp_login_form.dart';

const _frame = Duration(milliseconds: 16);

Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  bool reduceMotion = false,
}) {
  return tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.dark(),
      home: MediaQuery(
        data: MediaQueryData(disableAnimations: reduceMotion),
        child: Scaffold(
          body: Padding(padding: const EdgeInsets.all(20), child: child),
        ),
      ),
    ),
  );
}

MpEyePose _pose(WidgetTester tester) =>
    MpEye.debugPoseOf(tester.element(find.byType(MpEye)));

Future<void> _run(WidgetTester tester, Duration duration) async {
  for (var t = Duration.zero; t < duration; t += _frame) {
    await tester.pump(_frame);
    _expectSane(_pose(tester));
  }
}

Future<Duration> _runUntil(
  WidgetTester tester,
  bool Function(MpEyePose pose) done, {
  Duration max = const Duration(seconds: 10),
}) async {
  var t = Duration.zero;
  while (!done(_pose(tester))) {
    expect(t, lessThan(max), reason: 'gave up waiting');
    await tester.pump(_frame);
    t += _frame;
    _expectSane(_pose(tester));
  }
  return t;
}

void _expectSane(MpEyePose p) {
  expect(p.dx, inInclusiveRange(-20, 20));
  expect(p.dy, inInclusiveRange(0, 9));
  expect(p.pupilDy, inInclusiveRange(0, 3));
  expect(p.open, inInclusiveRange(0, 1));
  expect(p.iris, inInclusiveRange(0, 1));
  expect(p.lashes, inInclusiveRange(0, 1));
  expect(p.iris, lessThanOrEqualTo(p.open + 1e-9), reason: '$p');
}

Duration _ms(int ms) => Duration(milliseconds: ms);

void main() {
  group('variants match Figma mp/Eye', () {
    test('glances are ±20 px, down is 9 + 3 px, blink and closed hide the '
        'iris', () {
      expect(MpEyePose.of(MpEyeLook.left), const MpEyePose(dx: -20));
      expect(MpEyePose.of(MpEyeLook.right), const MpEyePose(dx: 20));
      expect(MpEyePose.of(MpEyeLook.down), const MpEyePose(dy: 9, pupilDy: 3));
      expect(MpEyePose.of(MpEyeLook.blink), const MpEyePose(open: 0, iris: 0));
      expect(
        MpEyePose.of(MpEyeLook.closed),
        const MpEyePose(open: 0, iris: 0, lashes: 1),
      );
    });
  });

  testWidgets('the idle loop lands exactly on each variant, in order', (
    tester,
  ) async {
    await _pump(tester, const MpEye());
    expect(_pose(tester), MpEyePose.of(MpEyeLook.idle));

    var previous = MpEyePose.of(MpEyeLook.idle);
    for (var round = 0; round < 2; round++) {
      for (final (i, (look, move, hold)) in MpEye.idleLoopSteps.indexed) {
        final target = MpEyePose.of(look);
        if (round > 0 || i > 0) {
          final took = await _runUntil(tester, (p) => p != previous);
          final moved = await _runUntil(tester, (p) => p == target);
          expect(moved, lessThanOrEqualTo(move + _frame), reason: '$i');
          expect(
            took,
            lessThanOrEqualTo(MpEye.idleLoopSteps[(i + 4) % 5].$3 + _frame * 2),
          );
        }
        if (hold > _frame * 2) {
          await _run(tester, hold - _frame * 2);
          expect(_pose(tester), target, reason: 'hold $round $i');
        }
        previous = target;
      }
    }
    expect(tester.binding.transientCallbackCount, lessThanOrEqualTo(1));
  });

  testWidgets('the blink closes the lid completely, then reopens', (
    tester,
  ) async {
    await _pump(tester, const MpEye());
    var minOpen = 1.0;
    for (var t = Duration.zero; t < _ms(6500); t += _frame) {
      await tester.pump(_frame);
      final p = _pose(tester);
      _expectSane(p);
      if (p.open < minOpen) minOpen = p.open;
    }
    expect(minOpen, 0);
    expect(_pose(tester).open, 1);
  });

  group('focus changes at awkward moments', () {
    Future<void> pumpForm(WidgetTester tester) =>
        _pump(tester, const SingleChildScrollView(child: MpLoginForm()));

    Future<void> focus(WidgetTester tester, int field) async {
      await tester.tap(find.byType(TextField).at(field));
      await tester.pump();
    }

    Future<void> unfocus(WidgetTester tester) async {
      FocusManager.instance.primaryFocus?.unfocus();
      await tester.pump();
    }

    testWidgets('phone mid-glance, password mid-move, none mid-move', (
      tester,
    ) async {
      await pumpForm(tester);
      await _runUntil(tester, (p) => p.dx < -8);
      expect(_pose(tester).dx, inExclusiveRange(-20, 0));

      await focus(tester, 0);
      await _run(tester, _ms(150));
      expect(_pose(tester).dy, inExclusiveRange(0, 9));
      await focus(tester, 1);
      await _run(tester, _ms(320));
      expect(_pose(tester), MpEyePose.of(MpEyeLook.closed));

      await unfocus(tester);
      await _run(tester, _ms(320));
      expect(_pose(tester), MpEyePose.of(MpEyeLook.idle));
      expect(tester.binding.transientCallbackCount, 0);

      await _run(tester, _ms(2300));
      expect(_pose(tester), MpEyePose.of(MpEyeLook.idle));
      await _run(tester, _ms(450));
      expect(_pose(tester), MpEyePose.of(MpEyeLook.left));
    });

    testWidgets('password mid-blink, back to none mid-close', (tester) async {
      await pumpForm(tester);
      await _runUntil(tester, (p) => p.open < 0.6);
      expect(_pose(tester).open, inExclusiveRange(0, 1));

      await focus(tester, 1);
      await _run(tester, _ms(120));
      await unfocus(tester);
      await _run(tester, _ms(320));
      expect(_pose(tester), MpEyePose.of(MpEyeLook.idle));
      await _run(tester, _ms(2300));
      expect(_pose(tester), MpEyePose.of(MpEyeLook.idle));
    });

    testWidgets('phone mid-right-glance, then none: no stuck pose', (
      tester,
    ) async {
      await pumpForm(tester);
      await _runUntil(tester, (p) => p.dx > 8);
      await focus(tester, 0);
      await _run(tester, _ms(320));
      expect(_pose(tester), MpEyePose.of(MpEyeLook.down));
      await unfocus(tester);
      await _run(tester, _ms(320));
      expect(_pose(tester), MpEyePose.of(MpEyeLook.idle));
    });
  });

  testWidgets('idleLoop: false stays on its variant without ticking', (
    tester,
  ) async {
    await _pump(tester, const MpEye(idleLoop: false));
    await tester.pump(_ms(10000));
    expect(_pose(tester), MpEyePose.of(MpEyeLook.idle));
    expect(tester.binding.transientCallbackCount, 0);
  });

  testWidgets('reduce motion: no loop, look changes jump', (tester) async {
    await _pump(tester, const MpEye(), reduceMotion: true);
    await tester.pump(_ms(6000));
    expect(_pose(tester), MpEyePose.of(MpEyeLook.idle));
    expect(tester.binding.transientCallbackCount, 0);
    await _pump(tester, const MpEye(look: MpEyeLook.down), reduceMotion: true);
    expect(_pose(tester), MpEyePose.of(MpEyeLook.down));
  });

  testWidgets('disposing mid-move leaves no timer or ticker behind', (
    tester,
  ) async {
    await _pump(tester, const MpEye());
    await tester.pump(_ms(2500));
    await tester.pumpWidget(const SizedBox());
    expect(tester.binding.transientCallbackCount, 0);
  });
}
