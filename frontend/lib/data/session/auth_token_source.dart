library;

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../errors.dart';

abstract interface class AuthTokenSource {
  Future<void> signInWithCustomToken(String customToken);

  Future<String?> idToken({bool forceRefresh = false});

  Future<void> signOut();

  bool get isSignedIn;
}

final class FirebaseAuthTokenSource implements AuthTokenSource {
  FirebaseAuthTokenSource([FirebaseAuth? auth, FlutterSecureStorage? storage])
    : _injected = auth,
      _storage = storage ?? const FlutterSecureStorage();

  final FirebaseAuth? _injected;
  final FlutterSecureStorage _storage;
  static const _tokenKey = 'mp.session.dev_token';
  String? _fallbackCustomToken;

  FirebaseAuth get _auth => _injected ?? FirebaseAuth.instance;

  static const _sessionGone = {
    'user-token-expired',
    'invalid-user-token',
    'user-disabled',
    'user-not-found',
    'no-current-user',
  };

  @override
  Future<void> signInWithCustomToken(String customToken) async {
    try {
      await _auth.signInWithCustomToken(customToken);
      _fallbackCustomToken = null;
      await _storage.delete(key: _tokenKey);
    } catch (e) {
      if (e is FirebaseAuthException && e.code == 'network-request-failed') {
        throw const NetworkException();
      }
      debugPrint(
        '[AuthTokenSource] FirebaseAuth sign-in fallback (reason: $e); using backend JWT token directly.',
      );
      _fallbackCustomToken = customToken;
      await _storage.write(key: _tokenKey, value: customToken);
    }
  }

  @override
  Future<String?> idToken({bool forceRefresh = false}) async {
    final user = _auth.currentUser;
    if (user != null) {
      try {
        return await user.getIdToken(forceRefresh);
      } on FirebaseAuthException catch (e) {
        if (_sessionGone.contains(e.code)) return null;
        throw _map(e);
      }
    }
    _fallbackCustomToken ??= await _storage.read(key: _tokenKey);
    return _fallbackCustomToken;
  }

  @override
  Future<void> signOut() async {
    _fallbackCustomToken = null;
    await _storage.delete(key: _tokenKey);
    try {
      await _auth.signOut();
    } on Object {
      // Signing out locally must not fail the logout flow.
    }
  }

  @override
  bool get isSignedIn =>
      _auth.currentUser != null || _fallbackCustomToken != null;

  static MpException _map(FirebaseAuthException e) =>
      e.code == 'network-request-failed'
      ? const NetworkException()
      : ServerException(code: 'FIREBASE_${e.code}');
}
