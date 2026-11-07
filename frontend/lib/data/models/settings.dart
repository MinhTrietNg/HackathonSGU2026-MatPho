enum NotificationPermission { notDetermined, granted, denied }

final class TestAlertResult {
  const TestAlertResult({
    required this.receivedAfter,
    required this.loudWhenSilent,
  });

  final Duration receivedAfter;

  final bool loudWhenSilent;
}
