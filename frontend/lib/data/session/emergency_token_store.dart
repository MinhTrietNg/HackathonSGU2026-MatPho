/// Emergency Token Store for Zero-Friction Emergency Access (ADR 0011 & Plan B).
///
/// Stores HMAC-SHA256 emergency bypass tokens received from FCM push payloads or deep links,
/// allowing any permitted recipient to view live fire incidents, photos, and camera feeds
/// immediately without requiring login credentials.
final class EmergencyTokenStore {
  EmergencyTokenStore._();
  static final EmergencyTokenStore instance = EmergencyTokenStore._();

  final Map<String, String> _tokens = <String, String>{};

  void save(String alertId, String token) {
    if (alertId.isNotEmpty && token.isNotEmpty) {
      _tokens[alertId] = token;
    }
  }

  String? get(String alertId) => _tokens[alertId];

  void remove(String alertId) {
    _tokens.remove(alertId);
  }

  void clear() {
    _tokens.clear();
  }
}
