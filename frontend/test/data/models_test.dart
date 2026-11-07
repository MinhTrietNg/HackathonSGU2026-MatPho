import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/models/models.dart';

void main() {
  test('phone helpers (A5, B2, J1)', () {
    expect(isValidVnPhone('0912 345 678'), isTrue);
    expect(isValidVnPhone('912345678'), isFalse);
    expect(formatPhone('0912345678'), '0912 345 678');
    expect(maskPhone('0912345678'), '0912 ••• 678');
  });

  test('new password checklist (B5)', () {
    var c = checkNewPassword('abc', 'abc');
    expect((c.minLength, c.lettersAndDigits, c.match), (false, false, true));
    c = checkNewPassword('matkhau123', 'matkhau12');
    expect((c.minLength, c.lettersAndDigits, c.match), (true, true, false));
    expect(c.allMet, isFalse);
    expect(checkNewPassword('mậtkhẩu1', 'mậtkhẩu1').allMet, isTrue);
  });

  test('history filter: unverified only under "Tất cả"', () {
    for (final f in HistoryFilter.values) {
      expect(
        f.matches(EventStatus.unverified),
        f == HistoryFilter.all,
        reason: '$f',
      );
    }
  });

  test('camera AI: weekday order does not matter, window order does', () {
    const a = AiPause(from: 60, to: 120, days: {1, 7});
    const b = AiPause(from: 60, to: 120, days: {7, 1});
    const c = AiPause(from: 60, to: 180);
    expect(a, b);
    expect(a.hashCode, b.hashCode);
    expect(
      const CameraAi(mode: AiMode.scheduled, pauses: [a, c]),
      const CameraAi(mode: AiMode.scheduled, pauses: [b, c]),
    );
    expect(
      const CameraAi(mode: AiMode.scheduled, pauses: [a, c]),
      isNot(const CameraAi(mode: AiMode.scheduled, pauses: [c, a])),
    );
    expect(
      const Camera(id: 'c', name: 'n', groupId: 'g').ai,
      CameraAi.alwaysOn,
    );
  });

  test('role permissions', () {
    expect(GroupRole.owner.canManage, isTrue);
    expect(GroupRole.manager.canManage, isTrue);
    expect(GroupRole.member.canManage, isFalse);
    expect(GroupRole.alertsOnly.canManage, isFalse);
  });

  test('every state machine case is handled by an exhaustive switch', () {
    String describe(DetectionState s) => switch (s) {
      DetectionIdle() => 'idle',
      DetectionWatching() => 'E2',
      DetectionVerifying() => 'E2a–E2c',
      DetectionNotified() => 'E2d',
      DetectionDismissed() => 'E4',
      DetectionUnverified() => 'F4',
      DetectionOffline() => 'E5',
      DetectionDegraded() => 'E6',
    };
    expect(describe(const DetectionIdle()), 'idle');
    expect(describe(const DetectionWatching()), 'E2');
  });
}
