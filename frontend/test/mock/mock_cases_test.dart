import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/providers.dart';
import 'package:mat_pho/data/services/phone_dialer.dart';

import '../fakes/fake_notification_service.dart';
import '../fakes/fake_overrides.dart';
import '../fakes/fake_scenario.dart';
import 'main.dart';

void main() {
  test('mặc định mở app ở trạng thái chưa đăng nhập', () {
    expect(mockCases(), {FakeCase.signedOut});
  });

  test('đọc danh sách FakeCase cách nhau bằng dấu phẩy', () {
    expect(mockCases(' noCameras, historyEmpty ,'), {
      FakeCase.noCameras,
      FakeCase.historyEmpty,
    });
    expect(mockCases(''), isEmpty);
  });

  test('tên FakeCase sai thì báo lỗi ngay', () {
    expect(() => mockCases('noCamera'), throwsArgumentError);
  });

  group('deviceOverrides', () {
    final real = FakeNotificationService(const FakeScenario());
    var initialized = false;

    Future<ProviderContainer> containerFor(Set<FakeCase> cases) async {
      initialized = false;
      final devices = await deviceOverrides(
        cases,
        notifications: () async {
          initialized = true;
          return real;
        },
      );
      return ProviderContainer.test(
        overrides: fakeOverrides([
          fakeScenarioProvider.overrideWithValue(FakeScenario(cases: cases)),
          ...devices,
        ]),
      );
    }

    test('mặc định dùng trình gọi điện và thông báo thật của máy', () async {
      final c = await containerFor({FakeCase.signedOut});

      expect(initialized, isTrue);
      expect(c.read(phoneDialerProvider), isA<SystemPhoneDialer>());
      expect(c.read(notificationServiceProvider), same(real));
    });

    for (final permission in [
      FakeCase.notificationsDenied,
      FakeCase.notificationsNotDetermined,
    ]) {
      test('${permission.name} giữ thông báo giả, gọi điện vẫn thật', () async {
        final c = await containerFor({permission});

        expect(initialized, isFalse);
        expect(c.read(phoneDialerProvider), isA<SystemPhoneDialer>());
        final notifications = c.read(notificationServiceProvider);
        expect(notifications, isA<FakeNotificationService>());
        expect(notifications, isNot(same(real)));
      });
    }
  });
}
