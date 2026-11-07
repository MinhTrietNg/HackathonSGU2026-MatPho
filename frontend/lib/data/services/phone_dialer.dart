import 'package:url_launcher/url_launcher.dart';

const emergencyNumber = '114';

abstract interface class PhoneDialer {
  Future<bool> dial(String number);
}

final class SystemPhoneDialer implements PhoneDialer {
  const SystemPhoneDialer();

  @override
  Future<bool> dial(String number) async {
    try {
      return await launchUrl(Uri(scheme: 'tel', path: number));
    } on Exception {
      return false;
    }
  }
}
