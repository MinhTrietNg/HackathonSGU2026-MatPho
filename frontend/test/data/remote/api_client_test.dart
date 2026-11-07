import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/remote/core/api_client.dart';
import 'package:mat_pho/data/remote/core/api_config.dart';

import '../../fakes/remote_doubles.dart';

http.Response jsonResponse(Object? json, [int status = 200]) => http.Response(
  jsonEncode(json),
  status,
  headers: {'content-type': 'application/json'},
);

void main() {
  late FakeAuthTokenSource tokens;
  late List<http.Request> requests;

  ApiClient client(
    FutureOr<http.Response> Function(http.Request request) handler, {
    Duration timeout = const Duration(seconds: 15),
  }) => ApiClient(
    config: testApiConfig,
    tokens: tokens,
    timeout: timeout,
    httpClient: MockClient((request) async {
      requests.add(request);
      return handler(request);
    }),
  );

  setUp(() {
    tokens = FakeAuthTokenSource(token: 'tok-1');
    requests = [];
  });

  group('requests', () {
    test('GET resolves the path and query under API_BASE_URL', () async {
      final api = client((_) => jsonResponse({'ok': true}));
      final json = await api.get(
        '/groups/grp_1/cameras',
        query: {'subgroup_id': 'sub_1', 'missing': null},
      );
      expect(json, {'ok': true});
      expect(
        requests.single.url.toString(),
        'https://api.test/api/v1/groups/grp_1/cameras?subgroup_id=sub_1',
      );
      expect(requests.single.method, 'GET');
    });

    test('POST sends a JSON body and decodes UTF-8 replies', () async {
      final api = client(
        (_) => http.Response.bytes(
          utf8.encode(jsonEncode({'full_name': 'Nguyễn Minh Anh'})),
          200,
        ),
      );
      final json = await api.post(
        '/auth/check-phone',
        body: {'phone_number': '0912345678'},
      );
      expect(json, {'full_name': 'Nguyễn Minh Anh'});
      final request = requests.single;
      expect(jsonDecode(request.body), {'phone_number': '0912345678'});
      expect(request.headers['Content-Type'], startsWith('application/json'));
    });

    test('PUT, PATCH, DELETE use their method; 204 → null', () async {
      final api = client((_) => http.Response('', 204));
      expect(await api.put('/a', body: {'x': 1}), isNull);
      expect(await api.patch('/b', body: {'x': 1}), isNull);
      expect(await api.delete('/c'), isNull);
      expect(requests.map((r) => r.method), ['PUT', 'PATCH', 'DELETE']);
    });

    test('Authorization header when signed in, never the URL', () async {
      final api = client((_) => jsonResponse({}));
      await api.get('/users/me');
      final request = requests.single;
      expect(request.headers['Authorization'], 'Bearer tok-1');
      expect(request.url.toString(), isNot(contains('tok-1')));
    });

    test('authenticated: false sends no Authorization header', () async {
      final api = client((_) => jsonResponse({}));
      await api.post('/auth/login', body: {}, authenticated: false);
      expect(requests.single.headers.containsKey('Authorization'), isFalse);
    });

    test('a reply that is not JSON → ServerException', () async {
      final api = client((_) => http.Response('<html>', 200));
      await expectLater(api.get('/x'), throwsA(isA<ServerException>()));
    });

    test('missing API_BASE_URL fails with a clear error', () async {
      final api = ApiClient(
        config: const ApiConfig(),
        tokens: tokens,
        httpClient: MockClient((_) async => jsonResponse({})),
      );
      await expectLater(
        api.get('/x'),
        throwsA(
          isA<StateError>().having(
            (e) => e.message,
            'message',
            contains('API_BASE_URL'),
          ),
        ),
      );
    });
  });

  group('401', () {
    test('refreshes the token once and retries → success', () async {
      tokens.refreshedToken = 'tok-2';
      final api = client(
        (r) => r.headers['Authorization'] == 'Bearer tok-2'
            ? jsonResponse({'ok': true})
            : jsonResponse({
                'error': {
                  'code': 'TOKEN_EXPIRED',
                  'message': '',
                  'details': {},
                },
              }, 401),
      );
      var expired = 0;
      api.sessionExpired.listen((_) => expired++);

      expect(await api.get('/users/me'), {'ok': true});
      expect(tokens.refreshCount, 1);
      expect(requests.map((r) => r.headers['Authorization']), [
        'Bearer tok-1',
        'Bearer tok-2',
      ]);
      await pumpEventQueue();
      expect(expired, 0);
    });

    test('twice → sessionExpired emitted + SessionExpiredException', () async {
      final api = client((_) => http.Response('', 401));
      final expired = expectLater(api.sessionExpired, emits(null));

      await expectLater(
        api.get('/users/me'),
        throwsA(isA<SessionExpiredException>()),
      );
      await expired;
      expect(requests, hasLength(2));
      expect(tokens.refreshCount, 1);
    });

    test('no token at all → session expired without a request', () async {
      tokens.token = null;
      final api = client((_) => jsonResponse({}));
      final expired = expectLater(api.sessionExpired, emits(null));
      await expectLater(
        api.get('/users/me'),
        throwsA(isA<SessionExpiredException>()),
      );
      await expired;
      expect(requests, isEmpty);
    });

    test('on an unauthenticated call: no refresh, ServerException', () async {
      final api = client((_) => http.Response('', 401));
      await expectLater(
        api.post('/auth/login', authenticated: false),
        throwsA(isA<ServerException>()),
      );
      expect(tokens.refreshCount, 0);
      expect(requests, hasLength(1));
    });
  });

  group('failures', () {
    test('timeout → ServerException', () async {
      final api = client(
        (_) => Completer<http.Response>().future,
        timeout: const Duration(milliseconds: 10),
      );
      await expectLater(api.get('/x'), throwsA(isA<ServerException>()));
    });

    test('SocketException → NetworkException', () async {
      final api = client((_) => throw const SocketException('down'));
      await expectLater(api.get('/x'), throwsA(isA<NetworkException>()));
    });

    test('ClientException → NetworkException', () async {
      final api = client((_) => throw http.ClientException('down'));
      await expectLater(api.get('/x'), throwsA(isA<NetworkException>()));
    });

    test('5xx → ServerException', () async {
      final api = client(
        (_) => jsonResponse({
          'error': {
            'code': 'INTERNAL_SERVER_ERROR',
            'message': '',
            'details': {},
          },
        }, 500),
      );
      await expectLater(
        api.get('/x'),
        throwsA(
          isA<ServerException>().having(
            (e) => e.code,
            'code',
            'INTERNAL_SERVER_ERROR',
          ),
        ),
      );
    });

    test('a contract error code becomes its MpException', () async {
      final api = client(
        (_) => jsonResponse({
          'error': {
            'code': 'WRONG_PASSWORD',
            'message': 'Số điện thoại hoặc mật khẩu không chính xác.',
            'details': {'attempts_left': 3},
          },
        }, 422),
      );
      await expectLater(
        api.post('/auth/login', authenticated: false),
        throwsA(
          isA<WrongPasswordException>().having(
            (e) => e.attemptsLeft,
            'attemptsLeft',
            3,
          ),
        ),
      );
    });
  });
}
