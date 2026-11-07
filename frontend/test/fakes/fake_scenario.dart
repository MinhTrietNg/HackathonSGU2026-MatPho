import 'fake_data.dart';

enum FakeCase {
  signedOut,

  wrongPassword,

  accountLocked,

  loginNetworkError,

  phoneExists,

  phoneNotRegistered,

  otpWrong,

  otpExpired,

  otpLocked,

  notificationsNotDetermined,

  notificationsDenied,

  verificationServerError,

  offline,

  slowDevice,

  historyEmpty,

  historyNetworkError,

  historyServerError,

  noCameras,

  cameraNoResponse,

  cameraAuthFailed,

  cameraNotOnCompanyWifi,

  cameraVendorBlocked,

  cameraReconnectFails,

  alertsOnlyRole,
}

final class FakeScenario {
  const FakeScenario({
    this.cases = const {},
    this.timeScale = 1,
    this.freezeClock = false,
    this.startAt,
  });

  const FakeScenario.test({this.cases = const {}})
    : timeScale = 0,
      freezeClock = true,
      startAt = null;

  final Set<FakeCase> cases;

  final double timeScale;

  final bool freezeClock;

  final DateTime? startAt;

  bool has(FakeCase c) => cases.contains(c);

  DateTime get origin => startAt ?? FakeData.demoNow;

  Duration scaled(Duration base) => base * timeScale;

  FakeScenario copyWith({Set<FakeCase>? cases}) => FakeScenario(
    cases: cases ?? this.cases,
    timeScale: timeScale,
    freezeClock: freezeClock,
    startAt: startAt,
  );
}
