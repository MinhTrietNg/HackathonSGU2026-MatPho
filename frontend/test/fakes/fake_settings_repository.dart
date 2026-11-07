import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/models/settings.dart';
import 'package:mat_pho/data/repositories/settings_repository.dart';
import 'fake_data.dart';
import 'fake_world.dart';

final class FakeSettingsRepository implements SettingsRepository {
  FakeSettingsRepository(this._world);

  final FakeWorld _world;

  @override
  Future<bool> loudWhenSilent() async {
    await _world.delay(Duration.zero);
    return _world.loudWhenSilent;
  }

  @override
  Future<void> setLoudWhenSilent(bool enabled) async {
    await _world.delay();
    _world.loudWhenSilent = enabled;
  }

  @override
  Future<TestAlertResult> sendTestAlert() async {
    await _world.delay(FakeData.testAlertReceivedAfter);
    return TestAlertResult(
      receivedAfter: FakeData.testAlertReceivedAfter,
      loudWhenSilent: _world.loudWhenSilent,
    );
  }

  @override
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    await _world.delay();
    if (currentPassword != _world.password) {
      throw const WrongPasswordException();
    }
    _world.password = newPassword;
  }

  @override
  Future<void> logout() async {
    await _world.delay();
    _world.signedIn = false;
  }
}
