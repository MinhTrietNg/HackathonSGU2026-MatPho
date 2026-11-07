library;

import 'dart:io';
import 'package:flutter/foundation.dart';

final class ApiConfig {
  const ApiConfig({this.baseUrl = '', this.wsUrl = ''});

  const ApiConfig.fromEnvironment()
    : baseUrl = const bool.hasEnvironment('API_BASE_URL')
          ? const String.fromEnvironment('API_BASE_URL')
          : const String.fromEnvironment('ENV') == 'local'
          ? const String.fromEnvironment(
              'LOCAL_BASE_URL',
              defaultValue: 'http://10.0.2.2:8000/api/v1',
            )
          : const String.fromEnvironment(
              'PROD_BASE_URL',
              defaultValue: 'https://api.matpho.vn/api/v1',
            ),
      wsUrl = const bool.hasEnvironment('WS_URL')
          ? const String.fromEnvironment('WS_URL')
          : const String.fromEnvironment('ENV') == 'local'
          ? const String.fromEnvironment(
              'LOCAL_WS_URL',
              defaultValue: 'ws://10.0.2.2:8000/api/v1/ws',
            )
          : const String.fromEnvironment(
              'PROD_WS_URL',
              defaultValue: 'wss://api.matpho.vn/api/v1/ws',
            );

  static Future<ApiConfig> resolveActive() async {
    const explicitBase = String.fromEnvironment('API_BASE_URL');
    const explicitWs = String.fromEnvironment('WS_URL');
    if (explicitBase.isNotEmpty) {
      debugPrint('[ApiConfig] Using explicit override: $explicitBase');
      return const ApiConfig(baseUrl: explicitBase, wsUrl: explicitWs);
    }

    const localBase = String.fromEnvironment(
      'LOCAL_BASE_URL',
      defaultValue: 'http://10.0.2.2:8000/api/v1',
    );
    const localWs = String.fromEnvironment(
      'LOCAL_WS_URL',
      defaultValue: 'ws://10.0.2.2:8000/api/v1/ws',
    );
    const prodBase = String.fromEnvironment(
      'PROD_BASE_URL',
      defaultValue: 'https://api.matpho.vn/api/v1',
    );
    const prodWs = String.fromEnvironment(
      'PROD_WS_URL',
      defaultValue: 'wss://api.matpho.vn/api/v1/ws',
    );

    const envMode = String.fromEnvironment('ENV', defaultValue: 'auto');

    if (envMode == 'local') {
      debugPrint('[ApiConfig] Forced local mode: $localBase');
      return const ApiConfig(baseUrl: localBase, wsUrl: localWs);
    }
    if (envMode == 'prod' || envMode == 'production') {
      debugPrint('[ApiConfig] Forced prod mode: $prodBase');
      return const ApiConfig(baseUrl: prodBase, wsUrl: prodWs);
    }

    try {
      final baseUri = Uri.parse(localBase);
      final healthUri = baseUri.replace(path: '/api/v1/health');
      final client = HttpClient()
        ..connectionTimeout = const Duration(milliseconds: 1500);
      final request = await client.getUrl(healthUri);
      final response = await request.close().timeout(
        const Duration(milliseconds: 1500),
      );
      client.close();
      if (response.statusCode >= 200 && response.statusCode < 300) {
        debugPrint(
          '[ApiConfig] Auto-detected reachable local server: $localBase',
        );
        return const ApiConfig(baseUrl: localBase, wsUrl: localWs);
      }
    } catch (e) {
      debugPrint(
        '[ApiConfig] Local server probe failed ($e) -> fallback to production: $prodBase',
      );
    }

    return const ApiConfig(baseUrl: prodBase, wsUrl: prodWs);
  }

  final String baseUrl;

  final String wsUrl;

  Uri resolve(String path, [Map<String, Object?>? query]) {
    final base = _require(baseUrl, 'API_BASE_URL', 'https://host/api/v1');
    final trimmed = base.endsWith('/')
        ? base.substring(0, base.length - 1)
        : base;
    final uri = Uri.parse('$trimmed${path.startsWith('/') ? '' : '/'}$path');
    final params = _queryParameters(query);
    return params.isEmpty ? uri : uri.replace(queryParameters: params);
  }

  Uri get wsUri => Uri.parse(_require(wsUrl, 'WS_URL', 'wss://host/api/v1/ws'));

  static String _require(String value, String name, String example) {
    if (value.isEmpty) {
      throw StateError(
        '$name is not set. Build with --dart-define=$name=$example',
      );
    }
    return value;
  }

  static Map<String, Object> _queryParameters(Map<String, Object?>? query) => {
    for (final MapEntry(:key, :value) in (query ?? const {}).entries)
      if (value != null)
        key: value is Iterable
            ? [for (final v in value) v.toString()]
            : value.toString(),
  };
}
