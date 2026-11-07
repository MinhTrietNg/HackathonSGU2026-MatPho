library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../../errors.dart';
import '../../session/auth_token_source.dart';
import 'api_config.dart';
import 'api_errors.dart';
import 'json.dart' show badResponse;

final class ApiClient {
  ApiClient({
    required this._config,
    required this._tokens,
    http.Client? httpClient,
    this.timeout = const Duration(seconds: 15),
  }) : _http = httpClient ?? http.Client();

  final ApiConfig _config;
  final AuthTokenSource _tokens;
  final http.Client _http;

  final Duration timeout;

  final _expired = StreamController<void>.broadcast();

  Stream<void> get sessionExpired => _expired.stream;

  Future<Object?> get(
    String path, {
    Map<String, Object?>? query,
    bool authenticated = true,
  }) => _send('GET', path, query: query, authenticated: authenticated);

  Future<Object?> post(
    String path, {
    Object? body,
    Map<String, Object?>? query,
    bool authenticated = true,
  }) => _send(
    'POST',
    path,
    body: body,
    query: query,
    authenticated: authenticated,
  );

  Future<Object?> put(
    String path, {
    Object? body,
    Map<String, Object?>? query,
    bool authenticated = true,
  }) => _send(
    'PUT',
    path,
    body: body,
    query: query,
    authenticated: authenticated,
  );

  Future<Object?> patch(
    String path, {
    Object? body,
    Map<String, Object?>? query,
    bool authenticated = true,
  }) => _send(
    'PATCH',
    path,
    body: body,
    query: query,
    authenticated: authenticated,
  );

  Future<Object?> delete(
    String path, {
    Object? body,
    Map<String, Object?>? query,
    bool authenticated = true,
  }) => _send(
    'DELETE',
    path,
    body: body,
    query: query,
    authenticated: authenticated,
  );

  void close() {
    _http.close();
    _expired.close();
  }

  Future<Object?> _send(
    String method,
    String path, {
    Object? body,
    Map<String, Object?>? query,
    required bool authenticated,
  }) async {
    final uri = _config.resolve(path, query);
    final encoded = body == null ? null : jsonEncode(body);

    var response = await _attempt(method, uri, encoded, authenticated, false);
    // 401: refresh the Firebase ID token and retry once; still 401 ends the session.
    if (authenticated && response.statusCode == HttpStatus.unauthorized) {
      response = await _attempt(method, uri, encoded, authenticated, true);
      if (response.statusCode == HttpStatus.unauthorized) _sessionGone();
    }

    final text = _bodyText(response);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw decodeApiError(response.statusCode, text);
    }
    if (text.trim().isEmpty) return null;
    try {
      return jsonDecode(text);
    } on FormatException {
      throw ServerException(
        code: badResponse,
        message: '$method $path: reply is not JSON',
      );
    }
  }

  Future<http.Response> _attempt(
    String method,
    Uri uri,
    String? body,
    bool authenticated,
    bool forceRefresh,
  ) async {
    final request = http.Request(method, uri)
      ..headers['Accept'] = 'application/json';
    if (body != null) {
      request.headers['Content-Type'] = 'application/json; charset=utf-8';
      request.body = body;
    }
    if (authenticated) {
      final token = await _tokens.idToken(forceRefresh: forceRefresh);
      if (token == null) _sessionGone();
      request.headers['Authorization'] = 'Bearer $token';
    }

    try {
      return await _http
          .send(request)
          .then(http.Response.fromStream)
          .timeout(timeout);
    } on TimeoutException {
      throw ServerException(code: 'TIMEOUT', message: '$method ${uri.path}');
    } on IOException {
      throw const NetworkException();
    } on http.ClientException {
      throw const NetworkException();
    }
  }

  Never _sessionGone() {
    if (!_expired.isClosed) _expired.add(null);
    throw const SessionExpiredException();
  }

  static String _bodyText(http.Response response) =>
      utf8.decode(response.bodyBytes, allowMalformed: true);
}
