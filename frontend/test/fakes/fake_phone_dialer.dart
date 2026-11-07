import 'package:mat_pho/data/services/phone_dialer.dart';

final class FakePhoneDialer implements PhoneDialer {
  FakePhoneDialer({this.available = true});

  final bool available;

  final List<String> dialed = [];

  @override
  Future<bool> dial(String number) async {
    if (!available) return false;
    dialed.add(number);
    return true;
  }
}
