import '../models/settings.dart';

abstract interface class SettingsRepository {
  Future<bool> loudWhenSilent();
  Future<void> setLoudWhenSilent(bool enabled);

  Future<TestAlertResult> sendTestAlert();

  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  });

  Future<void> logout();
}
