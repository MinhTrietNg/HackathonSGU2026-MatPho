import 'package:flutter_test/flutter_test.dart';

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
}
