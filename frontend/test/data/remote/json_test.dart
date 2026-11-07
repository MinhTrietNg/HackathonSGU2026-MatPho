import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/errors.dart';
import 'package:mat_pho/data/remote/core/api_config.dart';
import 'package:mat_pho/data/remote/core/json.dart';

Matcher badField(String field) => throwsA(
  isA<ServerException>()
      .having((e) => e.code, 'code', badResponse)
      .having((e) => e.message, 'message', contains(field)),
);

void main() {
  group('server times', () {
    test('ISO-8601 UTC → the same moment in local time', () {
      final t = parseServerTime('2026-11-04T12:00:00.000Z');
      expect(t.isUtc, isFalse);
      expect(t.toUtc(), DateTime.utc(2026, 11, 4, 12));
    });

    test('offsets and Python isoformat', () {
      expect(
        parseServerTime('2026-11-04T19:00:00+07:00').toUtc(),
        DateTime.utc(2026, 11, 4, 12),
      );
      expect(
        parseServerTime('2026-11-04 12:00:00.5+00:00').toUtc(),
        DateTime.utc(2026, 11, 4, 12, 0, 0, 500),
      );
    });

    test('a time without a zone is UTC, not local', () {
      expect(
        parseServerTime('2026-11-04T12:00:00').toUtc(),
        DateTime.utc(2026, 11, 4, 12),
      );
    });

    test('null-safe and invalid', () {
      expect(tryParseServerTime(null), isNull);
      expect(tryParseServerTime('yesterday'), isNull);
      expect(
        () => parseServerTime('yesterday'),
        throwsA(isA<ServerException>()),
      );
    });
  });

  group('displayPhone', () {
    test('+84 → 0 for display', () {
      expect(displayPhone('+84912345678'), '0912345678');
    });

    test('anything else unchanged', () {
      expect(displayPhone('0912345678'), '0912345678');
      expect(displayPhone('+12025550123'), '+12025550123');
    });
  });

  group('typed readers', () {
    const json = <String, Object?>{
      'name': 'Hầm B1',
      'count': 2,
      'whole': 3.0,
      'confidence': 0.93,
      'fps': 5,
      'on': true,
      'at': '2026-11-04T12:00:00.000Z',
      'names': ['Cổng chính', 'Hầm B1'],
      'items': [
        {'id': 'cam_1'},
        {'id': 'cam_2'},
      ],
      'nested': {'id': 'grp_1'},
      'nothing': null,
    };

    test('read the right shapes', () {
      expect(readString(json, 'name'), 'Hầm B1');
      expect(readInt(json, 'count'), 2);
      expect(readInt(json, 'whole'), 3);
      expect(readDouble(json, 'confidence'), 0.93);
      expect(readDouble(json, 'fps'), 5.0);
      expect(readBool(json, 'on'), isTrue);
      expect(readDateTime(json, 'at').toUtc(), DateTime.utc(2026, 11, 4, 12));
      expect(readStringList(json, 'names'), ['Cổng chính', 'Hầm B1']);
      expect(readObjectList(json, 'items', (m) => readString(m, 'id')), [
        'cam_1',
        'cam_2',
      ]);
      expect(readMap(json, 'nested'), {'id': 'grp_1'});
      expect(readList(json, 'names'), hasLength(2));
    });

    test('OrNull readers: missing or null → null', () {
      expect(readStringOrNull(json, 'nothing'), isNull);
      expect(readStringOrNull(json, 'absent'), isNull);
      expect(readIntOrNull(json, 'absent'), isNull);
      expect(readDoubleOrNull(json, 'absent'), isNull);
      expect(readBoolOrNull(json, 'absent'), isNull);
      expect(readDateTimeOrNull(json, 'nothing'), isNull);
      expect(readMapOrNull(json, 'absent'), isNull);
    });

    test('wrong shape → ServerException naming the field', () {
      expect(() => readString(json, 'count'), badField('count'));
      expect(() => readString(json, 'absent'), badField('absent'));
      expect(() => readInt(json, 'confidence'), badField('confidence'));
      expect(() => readBool(json, 'name'), badField('name'));
      expect(() => readDateTime(json, 'name'), badField('name'));
      expect(() => readStringOrNull(json, 'count'), badField('count'));
      expect(
        () => readObjectList(json, 'names', (m) => m),
        badField('names[0]'),
      );
      expect(
        () => readStringList(const {
          'ids': ['a', 1],
        }, 'ids'),
        badField('ids[1]'),
      );
      expect(() => asJsonMap([1]), badField('response'));
      expect(() => asJsonList({}), badField('response'));
    });
  });

  group('ApiConfig', () {
    const config = ApiConfig(
      baseUrl: 'https://x.test/api/v1/',
      wsUrl: 'wss://x.test/api/v1/ws',
    );

    test('joins paths with or without slashes', () {
      expect(
        config.resolve('/auth/login').toString(),
        'https://x.test/api/v1/auth/login',
      );
      expect(
        config.resolve('cameras/cam_1').toString(),
        'https://x.test/api/v1/cameras/cam_1',
      );
    });

    test('query: nulls dropped, values stringified, lists repeated', () {
      final uri = config.resolve('/alerts', {
        'limit': 20,
        'cursor': null,
        'status': ['NEW', 'CONFIRMED'],
      });
      expect(uri.queryParametersAll, {
        'limit': ['20'],
        'status': ['NEW', 'CONFIRMED'],
      });
    });

    test('missing values fail at first use with the define name', () {
      const empty = ApiConfig();
      expect(
        () => empty.resolve('/x'),
        throwsA(
          isA<StateError>().having(
            (e) => e.message,
            'message',
            contains('API_BASE_URL'),
          ),
        ),
      );
      expect(
        () => empty.wsUri,
        throwsA(
          isA<StateError>().having(
            (e) => e.message,
            'message',
            contains('WS_URL'),
          ),
        ),
      );
      expect(config.wsUri.toString(), 'wss://x.test/api/v1/ws');
    });
  });
}
