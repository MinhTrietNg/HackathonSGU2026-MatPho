library;

import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class SessionStore {
  Future<void> save(Map<String, Object?> user);

  Future<Map<String, Object?>?> read();

  Future<void> clear();
}

final class SecureSessionStore implements SessionStore {
  SecureSessionStore([FlutterSecureStorage? storage])
    : _storage =
          storage ??
          const FlutterSecureStorage(
            iOptions: IOSOptions(
              accessibility: KeychainAccessibility.first_unlock,
            ),
          );

  final FlutterSecureStorage _storage;

  static const _key = 'mp.session.user';

  @override
  Future<void> save(Map<String, Object?> user) =>
      _storage.write(key: _key, value: jsonEncode(user));

  @override
  Future<Map<String, Object?>?> read() async {
    try {
      final raw = await _storage.read(key: _key);
      if (raw == null) return null;
      final decoded = jsonDecode(raw);
      return decoded is Map<String, Object?> ? decoded : null;
    } on Object {
      return null;
    }
  }

  @override
  Future<void> clear() => _storage.delete(key: _key);
}
