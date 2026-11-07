library;

abstract interface class PushTokenSource {
  Future<String?> token();

  Stream<String> get onTokenRefresh;
}

final class NoPushTokenSource implements PushTokenSource {
  const NoPushTokenSource();

  @override
  Future<String?> token() async => null;

  @override
  Stream<String> get onTokenRefresh => const Stream.empty();
}
