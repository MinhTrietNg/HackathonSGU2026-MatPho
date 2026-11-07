import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/errors.dart';
import '../fakes/fake_auth_repository.dart';
import '../fakes/fake_data.dart';
import '../fakes/fake_scenario.dart';
import '../fakes/fake_settings_repository.dart';
import '../fakes/fake_world.dart';

FakeWorld world([Set<FakeCase> cases = const {}]) =>
    FakeWorld(FakeScenario.test(cases: cases));

void main() {
  test('loud when silent toggle (H1)', () async {
    final s = FakeSettingsRepository(world());
    expect(await s.loudWhenSilent(), isTrue);
    await s.setLoudWhenSilent(false);
    expect(await s.loudWhenSilent(), isFalse);
  });

  test('test alert received after 1,2 s (H4)', () async {
    final r = await FakeSettingsRepository(world()).sendTestAlert();
    expect(r.receivedAfter, const Duration(milliseconds: 1200));
    expect(r.loudWhenSilent, isTrue);
  });

  test('change password needs the current one (H5)', () async {
    final w = world();
    final s = FakeSettingsRepository(w);
    await expectLater(
      s.changePassword(currentPassword: 'sai', newPassword: 'moi12345'),
      throwsA(isA<WrongPasswordException>()),
    );
    await s.changePassword(
      currentPassword: FakeData.password,
      newPassword: 'moi12345',
    );
    final user = await FakeAuthRepository(
      w,
    ).login(phone: FakeData.user.phone, password: 'moi12345');
    expect(user, FakeData.user);
  });

  test('logout ends the session (H6)', () async {
    final w = world();
    await FakeSettingsRepository(w).logout();
    expect(await FakeAuthRepository(w).restoreSession(), isNull);
  });
}
