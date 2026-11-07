library;

import 'dart:async';

import 'package:flutter/services.dart' show PlatformException;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../errors.dart';
import '../models/user.dart';
import '../providers.dart' show clockProvider;
import '../repositories/auth_repository.dart';
import '../session/auth_token_source.dart';
import '../session/push_token_source.dart';
import '../session/session_store.dart';
import 'core/api_client.dart';
import 'core/json.dart';
import 'core/remote_providers.dart';
import 'core/ws_client.dart';

User parseUser(Map<String, Object?> json) => User(
  id: readString(json, 'user_id'),
  fullName: readString(json, 'full_name'),
  phone: displayPhone(readString(json, 'phone_number')),
  loudWhenSilent: readBoolOrNull(json, 'loud_when_silent') ?? true,
  personalGroupId: readStringOrNull(json, 'personal_group_id'),
);

final class RemoteSession {
  RemoteSession({
    required this._tokens,
    required this._store,
    required this._ws,
  });

  final AuthTokenSource _tokens;
  final SessionStore _store;
  final WsClient _ws;

  Future<Map<String, Object?>?> saved() async {
    final user = await _store.read();
    await _tokens.idToken();
    if (user != null && _tokens.isSignedIn) return user;
    if (user != null) await _clearStore();
    if (_tokens.isSignedIn) await _tokens.signOut();
    return null;
  }

  Future<void> start(String customToken, Map<String, Object?> user) async {
    await _tokens.signInWithCustomToken(customToken);
    await resume(user);
  }

  Future<void> resume(Map<String, Object?> user) async {
    await _saveStore(user);
    _ws.connect();
  }

  Future<void> end([Future<void> Function()? tellServer]) async {
    await _clearStore();
    await _ws.disconnect();
    try {
      await tellServer?.call();
    } finally {
      await _tokens.signOut();
    }
  }

  Future<void> _saveStore(Map<String, Object?> user) async {
    try {
      await _store.save(user);
    } on PlatformException {
      // Next start without a cache: A5.
    }
  }

  Future<void> _clearStore() async {
    try {
      await _store.clear();
    } on PlatformException {
      // Unreadable anyway.
    }
  }
}

final class RemoteAuthRepository implements AuthRepository {
  RemoteAuthRepository({
    required this._api,
    required this._session,
    required this._push,
    required this._now,
    this.restoreWait = const Duration(milliseconds: 1000),
  });

  final ApiClient _api;
  final RemoteSession _session;
  final PushTokenSource _push;
  final DateTime Function() _now;

  final Duration restoreWait;

  static const defaultResendCooldown = Duration(seconds: 60);

  @override
  Future<User?> restoreSession() async {
    final saved = await _session.saved();
    if (saved == null) return null;
    final fresh = _api.get('/users/me').then((json) => asJsonMap(json));
    try {
      final json = await fresh.timeout(restoreWait);
      final user = parseUser(json);
      await _session.resume(json);
      return user;
    } on SessionExpiredException {
      await _session.end();
      return null;
    } on TimeoutException {
      fresh.ignore();
      return _resumeCached(saved);
    } on MpException {
      return _resumeCached(saved);
    }
  }

  Future<User?> _resumeCached(Map<String, Object?> saved) async {
    final User user;
    try {
      user = parseUser(saved);
    } on ServerException {
      await _session.end();
      return null;
    }
    await _session.resume(saved);
    return user;
  }

  @override
  Future<User> login({required String phone, required String password}) async {
    final json = asJsonMap(
      await _api.post(
        '/auth/login',
        body: {
          'phone_number': _digits(phone),
          'password': password,
          ...await _pushToken(),
        },
        authenticated: false,
      ),
    );
    return _signIn(json);
  }

  @override
  Future<void> checkPhoneAvailable(String phone) async {
    final json = asJsonMap(
      await _api.post(
        '/auth/check-phone',
        body: {'phone_number': _digits(phone)},
        authenticated: false,
      ),
    );
    if (!readBool(json, 'is_available')) {
      throw const PhoneAlreadyRegisteredException();
    }
  }

  @override
  Future<OtpChallenge> register({
    required String fullName,
    required String phone,
    required String password,
  }) async {
    final json = await _api.post(
      '/auth/register/request-otp',
      body: {
        'phone_number': _digits(phone),
        'full_name': fullName,
        'password': password,
      },
      authenticated: false,
    );
    return _challenge(
      json,
      phone: _digits(phone),
      purpose: OtpPurpose.register,
    );
  }

  @override
  Future<OtpChallenge> requestPasswordReset(String phone) async {
    final json = await _api.post(
      '/auth/forgot-password/request-otp',
      body: {'phone_number': _digits(phone)},
      authenticated: false,
    );
    return _challenge(
      json,
      phone: _digits(phone),
      purpose: OtpPurpose.passwordReset,
    );
  }

  @override
  Future<OtpVerified> verifyOtp({
    required OtpChallenge challenge,
    required String code,
  }) async {
    final json = asJsonMap(
      await _api.post(
        '/auth/verify-otp',
        body: {
          'challenge_id': challenge.id,
          'code': code,
          ...await _pushToken(),
        },
        authenticated: false,
      ),
    );
    return switch (readString(json, 'type')) {
      'REGISTER_SUCCESS' => RegistrationCompleted(await _signIn(json)),
      'RESET_PASSWORD_VERIFIED' => PasswordResetAuthorized(
        readString(json, 'reset_token'),
      ),
      final other => throw ServerException(
        code: badResponse,
        message: 'verify-otp: unknown type "$other"',
      ),
    };
  }

  @override
  Future<OtpChallenge> resendOtp(OtpChallenge challenge) async {
    final json = await _api.post(
      '/auth/resend-otp',
      body: {'challenge_id': challenge.id},
      authenticated: false,
    );
    return _challenge(json, phone: challenge.phone, purpose: challenge.purpose);
  }

  @override
  Future<void> setNewPassword({
    required String resetToken,
    required String newPassword,
  }) async {
    await _api.post(
      '/auth/reset-password',
      body: {'reset_token': resetToken, 'new_password': newPassword},
      authenticated: false,
    );
  }

  // Sign-in flow: the backend's custom_token becomes a Firebase session, whose
  // ID token is the bearer for REST and the WebSocket.
  Future<User> _signIn(Map<String, Object?> json) async {
    final customToken = readString(json, 'custom_token');
    final userJson = readMap(json, 'user');
    final user = parseUser(userJson);
    await _session.start(customToken, userJson);
    return user;
  }

  OtpChallenge _challenge(
    Object? reply, {
    required String phone,
    required OtpPurpose purpose,
  }) {
    final json = asJsonMap(reply);
    final cooldown = readIntOrNull(json, 'resend_cooldown');
    return OtpChallenge(
      id: readString(json, 'challenge_id'),
      phone: phone,
      purpose: purpose,
      resendAvailableAt: _now().add(
        cooldown == null ? defaultResendCooldown : Duration(seconds: cooldown),
      ),
    );
  }

  Future<Map<String, Object?>> _pushToken() async {
    final token = await _push.token();
    return {'fcm_token': ?token};
  }

  static String _digits(String phone) => phone.replaceAll(' ', '');
}

final remoteSessionProvider = Provider<RemoteSession>(
  (ref) => RemoteSession(
    tokens: ref.watch(authTokenSourceProvider),
    store: ref.watch(sessionStoreProvider),
    ws: ref.watch(wsClientProvider),
  ),
);

final remoteAuthRepositoryProvider = Provider<AuthRepository>(
  (ref) => RemoteAuthRepository(
    api: ref.watch(apiClientProvider),
    session: ref.watch(remoteSessionProvider),
    push: ref.watch(pushTokenSourceProvider),
    now: ref.watch(clockProvider),
  ),
);
